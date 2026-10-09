"""Typography QA: sizes, hierarchy, leading, widows/orphans, font usage."""

from __future__ import annotations

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.quality import QAIssue

BODY = ("paragraph", "lead", "list_item", "warning", "note", "quote", "aside", "cta")
CAPTION = ("kicker", "label", "notice")


def check_typography(page: dict, typo: dict, brand_fonts: list[str]) -> tuple[list[QAIssue], dict[str, Metric]]:
    pid = page["pageId"]
    issues: list[QAIssue] = []
    items = page["items"]
    penalty = 0.0
    body_sizes = [i["fontPx"] for i in items if i["role"] in BODY]
    heads = [i["fontPx"] for i in items if i["role"] == "heading"]
    for i in items:
        if i["role"] in BODY and i["fontPx"] < typo["min_body_px"]:
            sev = "critical" if i["fontPx"] < 9 else "major"
            issues.append(QAIssue(check="qa.font_hierarchy", severity=sev, page=pid, selector=i["id"],
                                  message=f"body text {i['fontPx']:.1f}px < {typo['min_body_px']}px"))
            penalty += 12
        if i["role"] in CAPTION and i["fontPx"] < typo["min_caption_px"]:
            issues.append(QAIssue(check="qa.font_hierarchy", severity="major", page=pid, selector=i["id"],
                                  message=f"caption {i['fontPx']:.1f}px < {typo['min_caption_px']}px"))
            penalty += 6
        if i["role"] in BODY and i["fontPx"] > 0 and i["lineHeightPx"] / i["fontPx"] < typo["min_line_height"]:
            issues.append(QAIssue(check="qa.line_height", severity="major", page=pid, selector=i["id"],
                                  message=f"line-height {i['lineHeightPx'] / i['fontPx']:.2f} < {typo['min_line_height']}"))
            penalty += 6
        if i["role"] in ("paragraph", "lead", "warning", "list_item") and i["lines"] >= 2 and i["lineWidths"]:
            last, widest = i["lineWidths"][-1], max(i["lineWidths"])
            if widest > 0 and last / widest < 0.12:
                issues.append(QAIssue(check="qa.widows_orphans", severity="minor", page=pid, selector=i["id"],
                                      message="widow: last line is a single short fragment"))
                penalty += 2
        fam = i["fontFamily"].split(",")[0].strip().strip("'\"")
        if fam not in brand_fonts:
            issues.append(QAIssue(check="qa.fonts", severity="major", page=pid, selector=i["id"],
                                  message=f"non-brand font {fam}"))
            penalty += 5
    if heads and body_sizes and max(heads) < 1.4 * max(body_sizes):
        issues.append(QAIssue(check="qa.font_hierarchy", severity="major", page=pid,
                              message=f"heading {max(heads):.0f}px not clearly above body {max(body_sizes):.0f}px"))
        penalty += 15
    # orphaned heading: a heading/subheading that is the last block of the page flow
    flow = sorted([i for i in items if i["role"] not in ("notice",)], key=lambda i: (i["y"] + i["h"]))
    if flow and flow[-1]["role"] in ("heading", "subheading"):
        issues.append(QAIssue(check="qa.widows_orphans", severity="major", page=pid,
                              message="orphaned heading at the end of the page"))
        penalty += 10
    score = max(0.0, 100 - penalty)
    return issues, {"design.typography": Metric.measured("design.typography", score,
                                                         "deterministic typography rules over DOM (sizes, leading, "
                                                         "hierarchy, widows, fonts)")}
