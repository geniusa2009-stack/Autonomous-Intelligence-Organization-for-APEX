"""APEX brand QA: palette, forbidden effects, card overuse, logo/footer rules, fonts."""

from __future__ import annotations

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.quality import QAIssue
from apex_one.qa.colors import nearest_palette_distance


def check_brand(page: dict, inv: dict, fonts_loaded: list[str]) -> tuple[list[QAIssue], dict[str, Metric]]:
    pid = page["pageId"]
    issues: list[QAIssue] = []
    penalty = 0.0
    palette = list(inv["palette"].values()) + list(inv.get("allowed_extra_colors", []))
    off = [c for c in page["colors"] if nearest_palette_distance(c, palette) > 8]
    if off:
        issues.append(QAIssue(check="brand.palette", severity="major", page=pid, message=f"off-palette colours {off[:4]}"))
        penalty += 10 * min(3, len(off))
    forb = inv["forbidden"]
    for i in page["items"]:
        if forb.get("gradients") and "gradient" in (i.get("bgImage") or ""):
            issues.append(QAIssue(check="brand.gradients", severity="critical", page=pid, selector=i["id"],
                                  message="gradient background"))
            penalty += 25
        try:
            radius = float(str(i.get("radius", "0")).replace("px", "") or 0)
        except ValueError:
            radius = 0.0
        if radius > forb.get("max_border_radius_px", 4):
            issues.append(QAIssue(check="brand.radius", severity="major", page=pid, selector=i["id"],
                                  message=f"border-radius {radius}px"))
            penalty += 6
        if i.get("shadow") not in (None, "none") and forb.get("max_box_shadows_per_page", 0) == 0:
            issues.append(QAIssue(check="brand.shadow", severity="major", page=pid, selector=i["id"], message="box-shadow"))
            penalty += 6
    if "gradient" in (page.get("bgImage") or ""):
        issues.append(QAIssue(check="brand.gradients", severity="critical", page=pid, message="page gradient"))
        penalty += 25
    cards = len(page["cardLike"])
    if cards > forb.get("max_card_like_boxes_per_page", 2):
        issues.append(QAIssue(check="vision.card_overuse", severity="major", page=pid,
                              message=f"{cards} card-like boxes (max {forb.get('max_card_like_boxes_per_page', 2)})"))
        penalty += 8 * (cards - forb.get("max_card_like_boxes_per_page", 2))
    if page["nodeType"] == "Cover" and not page["hasLogo"]:
        issues.append(QAIssue(check="brand.logo", severity="major", page=pid, message="cover without APEX logo"))
        penalty += 15
    if page["nodeType"] == "Cover" and inv["logo"].get("is_placeholder"):
        issues.append(QAIssue(check="brand.logo_placeholder", severity="info", page=pid,
                              message="placeholder wordmark in use: supply the original APEX logo file"))
    if page["nodeType"] != "Cover" and not page["hasFooter"]:
        issues.append(QAIssue(check="brand.footer", severity="major", page=pid, message="missing APEX footer/robot signature"))
        penalty += 10
    fams = {f.split(":")[0] for f in fonts_loaded}
    used = {i["fontFamily"].split(",")[0].strip().strip("'\"") for i in page["items"]}
    for f in sorted(used & set(inv["fonts"].values())):
        if f not in fams:
            issues.append(QAIssue(check="brand.fonts", severity="major", page=pid,
                                  message=f"brand font used but not loaded (fallback rendering): {f}"))
            penalty += 10
    return issues, {"design.brand_fit": Metric.measured("design.brand_fit", max(0.0, 100 - penalty),
                                                        "deterministic brand invariants (palette, effects, cards, "
                                                        "logo/footer, fonts); aesthetic brand judgement is separate")}
