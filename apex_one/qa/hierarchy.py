"""Visual hierarchy: a deterministic DOM saliency model (where will the eye land first?).

This is a measurable proxy, not eye-tracking. Saliency grows with type size, contrast and area,
and with proximity to the top/right reading start of an RTL page.
"""

from __future__ import annotations

from apex_one.core.schemas.common import Metric
from apex_one.qa.colors import contrast


def saliency(i: dict, page_h: float, page_w: float) -> float:
    c = contrast(i["color"], i["bg"]) or 4.5
    area = max(1.0, i["w"] * i["h"])
    pos = 1.2 - 0.35 * (i["y"] / page_h) + 0.1 * ((i["x"] + i["w"]) / page_w)   # RTL: right/top start
    weight = 1.15 if str(i["fontWeight"]) in ("600", "700") else 1.0
    return (i.get("maxFontPx", i["fontPx"]) ** 1.7) * (c ** 0.5) * (area ** 0.12) * pos * weight


def check_hierarchy(page: dict) -> tuple[str | None, Metric]:
    items = [i for i in page["items"] if i["w"] > 0 and i["role"] not in ("notice",)]
    if not items:
        return None, Metric.not_measured("design.hierarchy", "no blocks")
    sal = sorted(((saliency(i, page["h"], page["w"]), i) for i in items), key=lambda x: -x[0])
    top_s, top = sal[0]
    second = sal[1][0] if len(sal) > 1 else 0.0
    intended = page.get("firstFixation")
    intended_s = next((s for s, i in sal if i["id"] == intended), None)
    if intended_s is None:
        score = 60.0 if top["role"] in ("heading", "hero", "stat") else 40.0
    else:
        score = 100.0 * intended_s / top_s
    dominance = top_s / second if second else 2.0
    if dominance < 1.15:
        score -= 10   # no clear entry point
    return top["id"], Metric.measured("design.hierarchy", max(0.0, min(100.0, score)),
                                      "DOM saliency model: intended first fixation vs predicted (not eye-tracking)",
                                      evidence=[f"predicted={top['role']}:{top['id']}", f"intended={intended}",
                                                f"dominance={dominance:.2f}"])
