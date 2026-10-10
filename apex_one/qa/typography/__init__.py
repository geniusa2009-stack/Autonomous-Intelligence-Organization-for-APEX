"""Typography QA: sizes, hierarchy, leading, widows/orphans, font usage."""

from __future__ import annotations

import re

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
    heads = [i.get("maxFontPx", i["fontPx"]) for i in items if i["role"] in ("heading", "hero")]
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


ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_PUNCT_IN_ARABIC = re.compile(r"[\u0600-\u06FF]\s?[,;?](?=\s|$)")
# Stretching = tatweel between two Arabic letters or repeated. «الـ» before a Latin term (الـ deadline) is the
# accepted Egyptian convention for the definite article and is NOT flagged.
TATWEEL_STRETCH = re.compile(r"[\u0621-\u064A]\u0640+[\u0621-\u064A]|\u0640{2,}")


def check_arabic_typography(page: dict, min_arabic_leading: float = 1.6) -> tuple[list[QAIssue], dict[str, Metric]]:
    """Arabic-specific rules the generic checks miss. Each one breaks shaping or reading in a way a reader sees:
    letter-spacing splits cursive joins; synthetic italics slant a script with no italic; tight leading collides
    marks and descenders; Latin punctuation and tatweel stretching read as careless."""
    pid = page["pageId"]
    issues: list[QAIssue] = []
    penalty = 0.0
    arabic_items = [i for i in page["items"] if ARABIC.search(i.get("text", ""))]
    for i in arabic_items:
        ls = str(i.get("letterSpacing", "normal"))
        if ls not in ("normal", "0px", "0", ""):
            try:
                px = float(ls.replace("px", ""))
            except ValueError:
                px = 1.0
            if abs(px) > 0.05:
                issues.append(QAIssue(check="qa.arabic_letter_spacing", severity="critical", page=pid, selector=i["id"],
                                      message=f"letter-spacing {ls} on Arabic text breaks cursive joining"))
                penalty += 25
        if i.get("fontStyle") in ("italic", "oblique"):
            issues.append(QAIssue(check="qa.arabic_italic", severity="major", page=pid, selector=i["id"],
                                  message="synthetic italic/oblique on Arabic text"))
            penalty += 10
        if i["role"] in BODY and i["fontPx"] > 0 and i["lines"] >= 2 and i["lineHeightPx"] / i["fontPx"] < min_arabic_leading:
            issues.append(QAIssue(check="qa.arabic_leading", severity="major", page=pid, selector=i["id"],
                                  message=f"Arabic multi-line leading {i['lineHeightPx'] / i['fontPx']:.2f} < {min_arabic_leading}"))
            penalty += 6
        txt = i.get("text", "")
        if LATIN_PUNCT_IN_ARABIC.search(txt):
            issues.append(QAIssue(check="qa.arabic_punctuation", severity="minor", page=pid, selector=i["id"],
                                  message="Latin , ; ? after Arabic text (use \u060c \u061b \u061f)"))
            penalty += 2
        if TATWEEL_STRETCH.search(txt):
            issues.append(QAIssue(check="qa.arabic_tatweel", severity="minor", page=pid, selector=i["id"],
                                  message="tatweel used to stretch text"))
            penalty += 2
    if not arabic_items:
        return issues, {"typography.arabic": Metric.not_measured("typography.arabic", "no Arabic text on page")}
    return issues, {"typography.arabic": Metric.measured(
        "typography.arabic", max(0.0, 100 - penalty),
        "Arabic typography rules over DOM (letter-spacing, italics, leading, punctuation, tatweel)",
        evidence=[f"arabic_blocks={len(arabic_items)}"])}
