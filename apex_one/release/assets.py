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
HEXCOL = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _svg_dims(path: Path) -> tuple[float, float] | None:
    root = etree.fromstring(path.read_bytes(), parser=etree.XMLParser(resolve_entities=False, no_network=True))
    vb = root.get("viewBox")
    if not vb:
        return None
    parts = [float(x) for x in re.split(r"[ ,]+", vb.strip())]
    return (parts[2], parts[3]) if len(parts) == 4 else None


def fingerprint(adir: Path) -> dict[str, Any]:
    """Brand fingerprint = hashes of every installed asset + the approved palette and fonts."""
    files = {p.name: _sha(p) for p in sorted(adir.rglob("*")) if p.is_file()
             and p.name not in ("brand_fingerprint.json", "IMPORT_RECORD.json", "README.md")}
    manifest = yaml.safe_load((adir / "brand.yaml").read_text(encoding="utf-8")) if (adir / "brand.yaml").exists() else {}
    core = {"files": files, "palette": manifest.get("palette"), "fonts": manifest.get("fonts")}
    return {**core, "fingerprint": hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()}


def import_brand(src: Path, dry_run: bool = False) -> dict[str, Any]:
    """Validate an APEX brand package and install it into assets/apex/ only if EVERY check passes.

    Package layout (folder): brand.yaml (approved_by, approved_at, palette {name: #RRGGBB}, fonts {role: family},
    optional font_files {family: file}, optional files {logo, logo_on_dark, robot, watermark: filename}) plus the
    files it names (defaults: logo.svg, logo-on-dark.svg, robot.svg, watermark.svg). Checks: file types, SVG validity
    and viewBox dimensions (aspect sanity), no raster/script, colours within the package palette, not a known
    placeholder, palette hex format, font files present with a font extension, required variants present."""
    s = get_settings()
    contract = yaml.safe_load((s.config_dir / "asset_contract.yaml").read_text(encoding="utf-8"))
    adir = s.home / contract["asset_dir"]
    problems: list[str] = []
    report: dict[str, Any] = {"source": str(src), "checks": {}, "installed": False}
    man_path = src / "brand.yaml"
    if not man_path.exists():
        return {**report, "problems": ["brand.yaml missing from the package"]}
    manifest = yaml.safe_load(man_path.read_text(encoding="utf-8")) or {}
    for k in contract["required"]["brand_manifest"]["required_keys"]:
        if not manifest.get(k):
            problems.append(f"brand.yaml: missing {k}")
    palette = manifest.get("palette") or {}
    bad_hex = [f"{k}={v}" for k, v in palette.items() if not HEXCOL.match(str(v))]
    if bad_hex:
        problems.append(f"palette values must be #RRGGBB: {bad_hex}")
    names = {"logo": "logo.svg", "logo_on_dark": "logo-on-dark.svg", "robot": "robot.svg", "watermark": "watermark.svg",
             **(manifest.get("files") or {})}
    ph = {_sha(s.home / p) for p in contract["placeholders"] if (s.home / p).exists()}
    pal_values = [str(v) for v in palette.values() if HEXCOL.match(str(v))]
    for role in (*SVG_ROLES, "watermark"):
        p = src / names[role]
        if not p.exists():
            if role != "watermark":
                problems.append(f"{role}: {names[role]} missing (required variant)")
            continue
        if p.suffix.lower() != ".svg":
            problems.append(f"{role}: must be .svg (vector), got {p.suffix}")
            continue
        probs = validate_svg(p, pal_values or ["#000000"], ph)
        dims = None
        try:
            dims = _svg_dims(p)
        except etree.XMLSyntaxError:
            pass
        if dims and (dims[0] <= 0 or dims[1] <= 0 or max(dims) / min(dims) > 12):
            probs.append(f"implausible viewBox dimensions {dims}")
        report["checks"][role] = {"file": p.name, "sha256": _sha(p), "viewBox": dims, "problems": probs}
        problems += [f"{role}: {x}" for x in probs]
    fonts = manifest.get("fonts") or {}
    font_files = manifest.get("font_files") or {}
    for fam, fname in font_files.items():
        fp = src / fname
        if not fp.exists() or fp.suffix.lower() not in FONT_EXT:
            problems.append(f"font {fam}: file {fname} missing or not a font ({FONT_EXT})")
    report["fonts"] = {"roles": fonts, "files": font_files}
    genome = yaml.safe_load((s.config_dir / "apex_brand.yaml").read_text(encoding="utf-8"))["invariants"]
    report["palette_vs_genome"] = {"only_in_package": sorted(set(map(str.upper, pal_values)) -
                                                             {v.upper() for v in genome["palette"].values()}),
                                   "fonts_differ": {k: v for k, v in fonts.items()
                                                    if k in genome["fonts"] and genome["fonts"][k] != v}}
    report["problems"] = problems
    if problems or dry_run:
        return report
    adir.mkdir(parents=True, exist_ok=True)
    import shutil

    dest_names = {"logo": "logo.svg", "logo_on_dark": "logo-on-dark.svg", "robot": "robot.svg", "watermark": "watermark.svg"}
    for role, chk in report["checks"].items():
        shutil.copy2(src / chk["file"], adir / dest_names[role])
    for fname in font_files.values():
        (adir / "fonts").mkdir(exist_ok=True)
        shutil.copy2(src / fname, adir / "fonts" / Path(fname).name)
    shutil.copy2(man_path, adir / "brand.yaml")
    fp = fingerprint(adir)
    (adir / "brand_fingerprint.json").write_text(json.dumps(fp, indent=2), encoding="utf-8")
    from datetime import UTC, datetime

    (adir / "IMPORT_RECORD.json").write_text(json.dumps({**report, "installed": True,
                                                         "at": datetime.now(UTC).isoformat(),
                                                         "fingerprint": fp["fingerprint"]}, indent=2), encoding="utf-8")
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
