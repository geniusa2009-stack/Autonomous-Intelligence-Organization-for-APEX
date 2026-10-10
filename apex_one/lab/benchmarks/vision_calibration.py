"""Judge-reliability calibration for the Vision Council (known-good page vs deliberately broken variants)."""

from __future__ import annotations

import json
from pathlib import Path

from apex_one.vision.render import Renderer

BREAKAGES = {
    "low_contrast": ".page .blk{color:#C9D0DA !important}",
    "card_overuse": (".page .blk{border:1px solid #A9B3C1;background:#ECEFF3;border-radius:14px;padding:10px;"
                     "box-shadow:0 6px 18px rgba(0,0,0,.25)}"),
    "gradient": ".page{background-image:linear-gradient(135deg,#ff7a18,#af002d 40%,#319197) !important}",
    "cramped": (".page .page-body{inset:3mm !important;row-gap:0 !important}.page .zone{gap:0 !important}"
                ".page .blk{line-height:1.05 !important;font-size:11px !important}"),
    "no_hierarchy": ".page .blk,.page .blk *{font-size:14px !important;font-weight:400 !important}",
}


def build_calibration_pages(final_html: Path, page_index: int, out_dir: Path) -> tuple[Path, dict[str, Path]]:
    """Render page `page_index` (1-based) of a guide as-is and with each breakage applied."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html = final_html.read_text(encoding="utf-8")
    only = f"section.page:not(:nth-of-type({page_index})){{display:none !important}}"
    variants = {"good": only, **{k: only + v for k, v in BREAKAGES.items()}}
    shots: dict[str, Path] = {}
    with Renderer(device_scale=1.0) as r:
        for name, css in variants.items():
            p = out_dir / f"{name}.html"
            p.write_text(html.replace("</style>", css + "</style>", 1), encoding="utf-8")
            res = r.measure(p, screenshot_dir=out_dir, screenshot_prefix=name)
            shots[name] = res.page_screenshots[0]
    good = shots.pop("good")
    (out_dir / "calibration_pages.json").write_text(json.dumps({"good": str(good), **{k: str(v) for k, v in shots.items()}}),
                                                     encoding="utf-8")
    return good, shots


def run_calibration(model_ids: list[str], out_dir: Path, intent: str = "one-page snapshot of decision-critical facts; "
                    "deadline must dominate") -> dict:
    from apex_one.compute.broker import ComputeBroker
    from apex_one.vision.council import VisionCouncil, calibrate

    pages = json.loads((out_dir / "calibration_pages.json").read_text(encoding="utf-8"))
    good = Path(pages.pop("good"))
    council = VisionCouncil(ComputeBroker(), model_ids)
    res = calibrate(council, good, {k: Path(v) for k, v in pages.items()}, intent)
    from datetime import UTC, datetime

    from apex_one.core.schemas.common import stable_hash
    from apex_one.vision.council import model_digest

    pages_hash = stable_hash((out_dir / "calibration_pages.json").read_text(encoding="utf-8"))
    for mid, r in res["models"].items():   # identity stamp: a result only counts for this model build + page set
        r.update({"at": datetime.now(UTC).isoformat(), "model_digest": model_digest(mid), "pages_hash": pages_hash})
    prev = json.loads((out_dir / "calibration_results.json").read_text()) if (out_dir / "calibration_results.json").exists() else {"models": {}}
    prev["models"].update(res["models"])
    (out_dir / "calibration_results.json").write_text(json.dumps(prev, indent=2), encoding="utf-8")
    return res
