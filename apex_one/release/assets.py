"""Phase 27 — APEX asset contract validation and the Brand Production Gate."""

from __future__ import annotations

import hashlib
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
