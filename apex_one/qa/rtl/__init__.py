"""RTL / bidi QA: direction, LTR isolation, currency, percent, dates, parentheses, mixed runs, URLs."""

from __future__ import annotations

import re

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.quality import QAIssue

ARABIC = re.compile(r"[؀-ۿ]")
LTRISH = re.compile(r"[A-Za-z$€£%]")


def check_rtl(page: dict, html_dir: str) -> tuple[list[QAIssue], dict[str, Metric]]:
    pid = page["pageId"]
    issues: list[QAIssue] = []
    penalty = 0.0
    if html_dir != "rtl":
        issues.append(QAIssue(check="qa.rtl_direction", severity="critical", page=pid, message="document is not dir=rtl"))
        penalty += 40
    for i in page["items"]:
        if ARABIC.search(i["text"]) and i["dir"] != "rtl":
            issues.append(QAIssue(check="qa.rtl_direction", severity="critical", page=pid, selector=i["id"],
                                  message=f"Arabic text laid out LTR in {i['role']}: {i['text'][:40]}"))
            penalty += 15
        if i["unisolatedLatin"]:
            issues.append(QAIssue(check="qa.ltr_isolation", severity="major", page=pid, selector=i["id"],
                                  message=f"Latin text not bidi-isolated: {i['unisolatedLatin'][:2]}"))
            penalty += 5
        if i["text"].count("(") != i["text"].count(")"):
            issues.append(QAIssue(check="qa.parentheses", severity="major", page=pid, selector=i["id"],
                                  message="unbalanced parentheses"))
            penalty += 5
        if i["role"] in ("url",) and i["overflowX"] > 0:
            issues.append(QAIssue(check="qa.long_urls", severity="critical", page=pid, selector=i["id"],
                                  message="URL overflows its block"))
    for f in page["facts"]:
        if LTRISH.search(f["text"]) and not f["isolated"]:
            check = "qa.currency" if "$" in f["text"] else "qa.percent" if "%" in f["text"] else "qa.mixed_runs"
            issues.append(QAIssue(check=check, severity="major", page=pid,
                                  message=f"fact '{f['text']}' with LTR symbols is not isolated"))
            penalty += 6
    if page.get("unisolatedMixedDigits"):
        issues.append(QAIssue(check="qa.mixed_runs", severity="major", page=pid,
                              message=f"digit/slash sequences in RTL context will reorder: {page['unisolatedMixedDigits'][:2]}"))
        penalty += 8
    texts = " ".join(i["text"] for i in page["items"])
    if "%" in texts and "٪" in texts:
        issues.append(QAIssue(check="qa.percent", severity="minor", page=pid, message="mixed % and ٪ signs"))
        penalty += 2
    return issues, {"rtl.quality": Metric.measured("rtl.quality", max(0.0, 100 - penalty),
                                                   "deterministic bidi/RTL rules over DOM (proxy for visual RTL quality)")}
