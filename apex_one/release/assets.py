"""Phase 27 — APEX asset contract validation and the Brand Production Gate."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from apex_one.core.schemas.common import Metric
from apex_one.qa.colors import nearest_palette_distance
from apex_one.settings import get_settings

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate_svg(path: Path, palette: list[str], placeholder_hashes: set[str]) -> list[str]:
    problems = []
    data = path.read_bytes()
    if _sha(path) in placeholder_hashes:
        return ["is the bundled PLACEHOLDER, not the original APEX asset"]
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as e:
        return [f"invalid SVG XML: {e}"]
    if not root.tag.endswith("svg"):
        problems.append("root element is not <svg>")
    if root.get("viewBox") is None:
        problems.append("missing viewBox (not scalable)")
    if root.xpath("//*[local-name()='image']") or b"data:image/png" in data or b"data:image/jpeg" in data:
        problems.append("embeds raster images (logo must be vector)")
    if root.xpath("//*[local-name()='script']"):
        problems.append("contains <script>")
    off = [c for c in set(HEX.findall(data.decode("utf-8", "ignore"))) if nearest_palette_distance(
        f"rgb({int(c[1:3], 16)}, {int(c[3:5], 16)}, {int(c[5:7], 16)})", palette) > 8]
    if off:
        problems.append(f"colours outside the APEX palette: {sorted(off)[:5]}")
    return problems


def validate_assets(palette: list[str] | None = None) -> dict[str, Any]:
    s = get_settings()
    contract = yaml.safe_load((s.config_dir / "asset_contract.yaml").read_text(encoding="utf-8"))
    if palette is None:
        brand = yaml.safe_load((s.config_dir / "apex_brand.yaml").read_text(encoding="utf-8"))
        palette = list(brand["invariants"]["palette"].values())
    adir = s.home / contract["asset_dir"]
    ph = {_sha(s.home / p) for p in contract["placeholders"] if (s.home / p).exists()}
    report: dict[str, Any] = {"asset_dir": str(adir), "assets": {}}
    for name, spec in contract["required"].items():
        p = adir / spec["file"]
        if not p.exists():
            report["assets"][name] = {"status": "MISSING", "problems": [f"{spec['file']} not found"]}
            continue
        if spec["kind"] == "svg":
            probs = validate_svg(p, palette, ph)
        else:
            m = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            probs = [f"brand.yaml missing key {k}" for k in spec.get("required_keys", []) if k not in m]
            if not probs:
                probs = manifest_problems(m, installed_paths(m, adir))
        report["assets"][name] = {"status": "VALID" if not probs else
                                  ("PLACEHOLDER" if any("PLACEHOLDER" in x for x in probs) else "INVALID"),
                                  "problems": probs, "sha256": _sha(p)}
    failures = [n for n, r in report["assets"].items() if r["status"] != "VALID"]
    if not failures:   # every file is valid: it must also be the exact set that was imported and approved
        fp = fingerprint_problems(adir)
        report["fingerprint_problems"] = fp
        failures += ["brand_fingerprint"] if fp else []
    report["failures"] = failures
    report["production_ready"] = not failures
    return report


def brand_production_metric(report: dict[str, Any]) -> Metric:
    return Metric.measured("brand.production_asset_failures", len(report["failures"]),
                           "asset contract validation (config/asset_contract.yaml)", unit="count",
                           evidence=[f"{k}:{v['status']}" for k, v in report["assets"].items()])


# ---------------------------------------------------------------- what the compiler embeds

_CACHE: dict[tuple, dict[str, Any]] = {}
FALLBACK = {"logo": "brand/apex_wordmark_placeholder.svg", "logo_on_dark": "brand/apex_wordmark_placeholder.svg",
            "robot": "brand/apex_robot_signature.svg"}


def _report_cached() -> dict[str, Any]:
    s = get_settings()
    adir = s.home / "assets" / "apex"
    key = (str(adir), tuple(sorted((p.name, p.stat().st_mtime_ns) for p in adir.glob("*"))) if adir.exists() else ())
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = validate_assets()
    return _CACHE[key]


def brand_svg(name: str) -> tuple[str, str]:
    """(svg markup, sha256) of the asset the compiler must embed: the contract file when it validates, otherwise the
    bundled placeholder. The sha is written into the page so the release gate checks what actually SHIPS."""
    from apex_one.design.assets.svg import ASSETS

    rep = _report_cached()
    r = rep["assets"].get(name, {})
    if r.get("status") == "VALID":
        contract = yaml.safe_load((get_settings().config_dir / "asset_contract.yaml").read_text(encoding="utf-8"))
        p = Path(rep["asset_dir"]) / contract["required"][name]["file"]
    else:
        p = ASSETS / FALLBACK[name]
    svg = p.read_text(encoding="utf-8")
    return svg[svg.index("<svg"):], _sha(p)


def embedded_asset_failures(html_text: str, report: dict[str, Any]) -> list[str]:
    """Brand assets actually embedded in final.html that are not VALID contract assets (e.g. placeholders)."""
    valid = {r["sha256"] for r in report["assets"].values() if r.get("status") == "VALID"}
    shas = set(re.findall(r'data-asset-sha="([0-9a-f]{64})"', html_text))
    return sorted(f"embedded asset {s[:12]}… is not a validated APEX asset" for s in shas - valid)


# ---------------------------------------------------------------- Phase 8: brand import + fingerprint

SVG_ROLES = ("logo", "logo_on_dark", "robot")
FONT_EXT = (".woff2", ".woff", ".ttf", ".otf")
FONT_MAGIC = (b"wOF2", b"wOFF", b"\x00\x01\x00\x00", b"true", b"OTTO")
HEXCOL = re.compile(r"^#[0-9A-Fa-f]{6}$")
NOT_A_LICENCE = {"", "unknown", "none", "n/a", "tbd", "?", "proprietary"}
MANIFEST_NAMES = ("manifest.yaml", "brand.yaml")      # intake name first; brand.yaml = installed / legacy name
# where each role lives in an intake package (BRAND_PACKAGE_INTAKE.md) — flat legacy names are still accepted
PACKAGE_DEFAULTS = {"logo": ("logo/logo.svg", "logo.svg"), "logo_on_dark": ("logo/logo-on-dark.svg", "logo-on-dark.svg"),
                    "robot": ("mascot/robot.svg", "robot.svg"), "watermark": ("logo/watermark.svg", "watermark.svg")}
INSTALLED = {"logo": "logo.svg", "logo_on_dark": "logo-on-dark.svg", "robot": "robot.svg", "watermark": "watermark.svg"}
MIN_USAGE_RULES_CHARS, MIN_LICENCE_EVIDENCE_BYTES = 80, 200


def _svg_dims(path: Path) -> tuple[float, float] | None:
    root = etree.fromstring(path.read_bytes(), parser=etree.XMLParser(resolve_entities=False, no_network=True))
    vb = root.get("viewBox")
    if not vb:
        return None
    parts = [float(x) for x in re.split(r"[ ,]+", vb.strip())]
    return (parts[2], parts[3]) if len(parts) == 4 else None


def _licence(entry: Any) -> tuple[str, str | None]:
    """font_licences value: {licence: <SPDX or 'commercial'>, evidence: <path to the licence text / receipt>}."""
    if isinstance(entry, dict):
        return str(entry.get("licence") or "").strip(), entry.get("evidence")
    return str(entry or "").strip(), None


def package_paths(manifest: dict[str, Any], src: Path) -> dict[str, Path]:
    """role -> file inside an intake package (manifest `files` wins, then the intake layout, then flat names)."""
    files = manifest.get("files") or {}
    out = {}
    for role, cands in PACKAGE_DEFAULTS.items():
        rel = files.get(role) or next((c for c in cands if (src / c).exists()), None)
        if rel or role != "watermark":
            out[role] = src / (rel or cands[0])
    for fam, f in (manifest.get("font_files") or {}).items():
        out[f"font:{fam}"] = src / f
    for fam, entry in (manifest.get("font_licences") or {}).items():
        ev = _licence(entry)[1]
        if ev:
            out[f"licence:{fam}"] = src / ev
    out["usage_rules"] = src / "usage_rules.md"
    return out


def installed_paths(manifest: dict[str, Any], adir: Path) -> dict[str, Path]:
    """role -> file in assets/apex after import (same roles as package_paths)."""
    out = {role: adir / name for role, name in INSTALLED.items() if role != "watermark"}
    if (adir / INSTALLED["watermark"]).exists():
        out["watermark"] = adir / INSTALLED["watermark"]
    for fam, f in (manifest.get("font_files") or {}).items():
        out[f"font:{fam}"] = adir / "fonts" / Path(f).name
    for fam, entry in (manifest.get("font_licences") or {}).items():
        ev = _licence(entry)[1]
        if ev:
            out[f"licence:{fam}"] = adir / "fonts" / "licences" / Path(ev).name
    out["usage_rules"] = adir / "usage_rules.md"
    return out


def manifest_problems(manifest: dict[str, Any], files: dict[str, Path]) -> list[str]:
    """Fonts (files + licence + licence evidence), usage constraints, usage rules and checksums of the manifest."""
    probs = []
    fams = set((manifest.get("fonts") or {}).values())
    font_files = manifest.get("font_files") or {}
    lic = manifest.get("font_licences") or {}
    for fam in sorted(fams):
        name, evidence = _licence(lic.get(fam))
        if name.lower() in NOT_A_LICENCE:
            probs.append(f"font {fam!r}: unlicensed — font_licences needs a real licence (e.g. OFL-1.1)")
        ev = files.get(f"licence:{fam}")
        if not evidence or ev is None or not ev.is_file() or ev.stat().st_size < MIN_LICENCE_EVIDENCE_BYTES:
            probs.append(f"font {fam!r}: licence evidence missing (the licence text or purchase receipt file, "
                         f">= {MIN_LICENCE_EVIDENCE_BYTES} bytes)")
        if fam not in font_files:
            probs.append(f"font {fam!r}: no font file declared in font_files")
    for fam in font_files:
        fp = files.get(f"font:{fam}")
        if fp is None or not fp.is_file():
            probs.append(f"font {fam!r}: file missing")
        elif fp.suffix.lower() not in FONT_EXT or not fp.read_bytes()[:4].startswith(FONT_MAGIC):
            probs.append(f"font {fam!r}: {fp.name} is corrupted or not a font ({'/'.join(FONT_EXT)})")
    u = manifest.get("usage") or {}
    try:
        if not float(u.get("min_logo_width_px", 0)) > 0:
            probs.append("usage.min_logo_width_px must be > 0")
        if not 0 < float(u.get("clear_space_ratio", 0)) <= 1:
            probs.append("usage.clear_space_ratio must be in (0, 1]")
    except (TypeError, ValueError):
        probs.append("usage values must be numbers")
    if not u.get("allowed_backgrounds"):
        probs.append("usage.allowed_backgrounds must list at least one background")
    ur = files.get("usage_rules")
    if ur is None or not ur.is_file() or len(ur.read_text(encoding="utf-8", errors="replace").strip()) < MIN_USAGE_RULES_CHARS:
        probs.append(f"usage_rules.md missing or shorter than {MIN_USAGE_RULES_CHARS} characters")
    sums = manifest.get("checksums") or {}
    for role, path in files.items():
        if not path.exists():
            continue
        want = sums.get(role)
        if not want:
            probs.append(f"checksums: no sha256 for {role}")
        elif str(want).lower() != _sha(path):
            probs.append(f"checksum mismatch for {role} ({path.name}): file changed or corrupted")
    return probs


def brand_status(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """VALID (production-ready) / INCOMPLETE (nothing wrong, something missing) / INVALID (something present is
    wrong: placeholder, bad SVG, off-palette, bad manifest, unlicensed font, checksum or fingerprint mismatch)."""
    rep = report if report is not None else validate_assets()
    reasons = [f"{n}: {r['status']} — {'; '.join(r['problems'])[:240]}" for n, r in rep["assets"].items()
               if r["status"] != "VALID"] + list(rep.get("fingerprint_problems") or [])
    states = {r["status"] for r in rep["assets"].values()}
    if states & {"INVALID", "PLACEHOLDER"} or rep.get("fingerprint_problems"):
        status = "INVALID"
    elif "MISSING" in states:
        status = "INCOMPLETE"
    else:
        status = "VALID" if rep["production_ready"] else "INVALID"
    return {"status": status, "reasons": reasons, "report": rep}


def fingerprint(adir: Path) -> dict[str, Any]:
    """Brand fingerprint = hashes of every installed asset + the approved palette and fonts."""
    files = {str(p.relative_to(adir)): _sha(p) for p in sorted(adir.rglob("*")) if p.is_file()
             and p.name not in ("brand_fingerprint.json", "IMPORT_RECORD.json", "README.md")}
    manifest = yaml.safe_load((adir / "brand.yaml").read_text(encoding="utf-8")) if (adir / "brand.yaml").exists() else {}
    core = {"files": files, "palette": manifest.get("palette"), "fonts": manifest.get("fonts")}
    return {**core, "fingerprint": hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()}


def _safe(src: Path, path: Path) -> str | None:
    """A package file must be a regular file inside the package — no symlink, no path escaping the folder."""
    try:
        rel = path.resolve().relative_to(src.resolve())
    except ValueError:
        return f"{path} points outside the package"
    if any((src / Path(*rel.parts[:i + 1])).is_symlink() for i in range(len(rel.parts))) or path.is_symlink():
        return f"{rel} is a symbolic link (not accepted)"
    return None


def import_brand(src: Path, dry_run: bool = False) -> dict[str, Any]:
    """Validate an APEX brand package (BRAND_PACKAGE_INTAKE.md) and install it into assets/apex/ only if EVERY check
    passes. Rejects: missing required files, corrupted files (SVG that does not parse, fonts with no font header,
    checksum mismatch), placeholders, raster/script in SVG, off-palette colours, unlicensed fonts or missing licence
    evidence, files the manifest does not list, symlinks and paths outside the package. Installation is staged:
    copied, re-hashed, then swapped in; a failure leaves the previous assets untouched."""
    import shutil

    s = get_settings()
    contract = yaml.safe_load((s.config_dir / "asset_contract.yaml").read_text(encoding="utf-8"))
    adir = s.home / contract["asset_dir"]
    problems: list[str] = []
    report: dict[str, Any] = {"source": str(src), "checks": {}, "installed": False}
    man_path = next((src / n for n in MANIFEST_NAMES if (src / n).is_file()), None)
    if man_path is None:
        return {**report, "problems": ["manifest missing: put manifest.yaml at the top of the package"]}
    try:
        manifest = yaml.safe_load(man_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return {**report, "problems": [f"manifest is not valid YAML: {e}"]}
    for k in contract["required"]["brand_manifest"]["required_keys"]:
        if not manifest.get(k):
            problems.append(f"manifest: missing {k}")
    palette = manifest.get("palette") or {}
    bad_hex = [f"{k}={v}" for k, v in palette.items() if not HEXCOL.match(str(v))]
    if bad_hex:
        problems.append(f"palette values must be #RRGGBB: {bad_hex}")
    paths = package_paths(manifest, src)
    for role, p in list(paths.items()):
        why = _safe(src, p) if p.exists() or p.is_symlink() else None
        if why:                       # never read through an unsafe path: report it and drop it from every check
            problems.append(f"{role}: {why}")
            paths[role] = src / f".rejected-{role}"
    ph = {_sha(s.home / q) for q in contract["placeholders"] if (s.home / q).exists()}
    pal_values = [str(v) for v in palette.values() if HEXCOL.match(str(v))]
    for role in (*SVG_ROLES, "watermark"):
        p = paths.get(role)
        if p is None or not p.exists():
            if role != "watermark":
                problems.append(f"{role}: {p.relative_to(src) if p else role} missing (required)")
            continue
        if p.suffix.lower() != ".svg":
            problems.append(f"{role}: must be .svg (vector), got {p.suffix}")
            continue
        probs = validate_svg(p, pal_values or ["#000000"], ph)
        dims = None
        try:
            dims = _svg_dims(p)
        except (etree.XMLSyntaxError, ValueError):
            pass
        if dims and (dims[0] <= 0 or dims[1] <= 0 or max(dims) / min(dims) > 12):
            probs.append(f"implausible viewBox dimensions {dims}")
        report["checks"][role] = {"file": str(p.relative_to(src)), "sha256": _sha(p), "viewBox": dims,
                                  "problems": probs}
        problems += [f"{role}: {x}" for x in probs]
    problems += manifest_problems(manifest, paths)
    listed = {p.resolve() for p in paths.values()} | {man_path.resolve()}
    unlisted = sorted(str(p.relative_to(src)) for p in src.rglob("*")
                      if p.is_file() and not any(part.startswith(".") for part in p.relative_to(src).parts)
                      and p.resolve() not in listed and p.name.lower() not in ("readme.md", "readme.txt"))
    problems += [f"unlisted file {u}: every file must be named in the manifest (or removed)" for u in unlisted]
    genome = yaml.safe_load((s.config_dir / "apex_brand.yaml").read_text(encoding="utf-8"))["invariants"]
    fonts = manifest.get("fonts") or {}
    report["fonts"] = {"roles": fonts, "files": manifest.get("font_files") or {}}
    report["palette_vs_genome"] = {"only_in_package": sorted(set(map(str.upper, pal_values)) -
                                                             {v.upper() for v in genome["palette"].values()}),
                                   "fonts_differ": {k: v for k, v in fonts.items()
                                                    if k in genome["fonts"] and genome["fonts"][k] != v}}
    report["problems"] = problems
    if problems or dry_run:
        return report
    stage = adir.parent / f".{adir.name}.staging"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    try:
        if (adir / "README.md").exists():
            shutil.copy2(adir / "README.md", stage / "README.md")
        dest = installed_paths(manifest, stage)
        if "watermark" in paths and paths["watermark"].exists():
            dest["watermark"] = stage / INSTALLED["watermark"]
        for role, sp in paths.items():
            if sp.exists():
                dest[role].parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sp, dest[role])
        shutil.copy2(man_path, stage / "brand.yaml")
        copied = manifest_problems(manifest, installed_paths(manifest, stage))     # re-hash after the copy
        if copied:
            raise RuntimeError(f"copy verification failed: {copied}")
        fp = fingerprint(stage)
        (stage / "brand_fingerprint.json").write_text(json.dumps(fp, indent=2), encoding="utf-8")
        from datetime import UTC, datetime

        (stage / "IMPORT_RECORD.json").write_text(json.dumps({**report, "installed": True,
                                                              "at": datetime.now(UTC).isoformat(),
                                                              "fingerprint": fp["fingerprint"]}, indent=2),
                                                  encoding="utf-8")
        old = adir.parent / f".{adir.name}.previous"
        shutil.rmtree(old, ignore_errors=True)
        if adir.exists():
            adir.rename(old)
        stage.rename(adir)
        shutil.rmtree(old, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 — a failed install never leaves half a brand behind
        shutil.rmtree(stage, ignore_errors=True)
        return {**report, "problems": [f"install failed, previous assets kept: {e}"]}
    _CACHE.clear()
    return {**report, "installed": True, "fingerprint": fp["fingerprint"]}


def fingerprint_problems(adir: Path) -> list[str]:
    """Assets edited after import (without re-import) no longer match the recorded fingerprint."""
    rec = adir / "brand_fingerprint.json"
    if not rec.exists():
        return ["no brand fingerprint: install assets with `apex-one brand import <folder>`"]
    if json.loads(rec.read_text())["fingerprint"] != fingerprint(adir)["fingerprint"]:
        return ["installed assets differ from the imported brand fingerprint (re-run `apex-one brand import`)"]
    return []


def checksums_block(src: Path) -> str:
    """The `checksums:` block for a package's manifest, computed from the files the manifest names (paste it in)."""
    man_path = next((src / n for n in MANIFEST_NAMES if (src / n).is_file()), None)
    manifest = yaml.safe_load(man_path.read_text(encoding="utf-8")) or {} if man_path else {}
    lines = ["checksums:"]
    for role, p in package_paths(manifest, src).items():
        if p.is_file() and not _safe(src, p):
            lines.append(f"  {role!r}: {_sha(p)}" if ":" in role else f"  {role}: {_sha(p)}")
    return "\n".join(lines) + "\n"
