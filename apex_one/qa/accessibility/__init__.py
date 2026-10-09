"""Accessibility QA: WCAG contrast, language attributes."""

from __future__ import annotations

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.quality import QAIssue
from apex_one.qa.colors import contrast


def check_accessibility(page: dict) -> tuple[list[QAIssue], dict[str, Metric]]:
    pid = page["pageId"]
    issues: list[QAIssue] = []
    worst = 21.0
    fails = 0
    for i in page["items"]:
        c = contrast(i["color"], i["bg"])
        if c is None:
            continue
        large = i["fontPx"] >= 24 or (i["fontPx"] >= 18.66 and str(i["fontWeight"]) in ("600", "700", "bold"))
        need = 3.0 if large else 4.5
        worst = min(worst, c)
        if c < need:
            fails += 1
            issues.append(QAIssue(check="qa.contrast", severity="major" if c >= 3 else "critical", page=pid,
                                  selector=i["id"], message=f"contrast {c:.2f} < {need} for {i['role']}"))
        if not i.get("lang"):
            issues.append(QAIssue(check="qa.lang", severity="minor", page=pid, selector=i["id"], message="missing lang"))
    n = max(1, len(page["items"]))
    return issues, {"accessibility.contrast": Metric.measured("accessibility.contrast", 100 * (1 - fails / n),
                                                              "WCAG 2.x contrast per text block",
                                                              evidence=[f"worst={worst:.2f}"])}
