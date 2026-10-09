"""DOM-level fact integrity: what the reader SEES must equal the FactLocks."""

from __future__ import annotations

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.quality import QAIssue
from apex_one.editorial.fact_guard.semantic_diff import semantic_diff

CATEGORY = {"deadline": "fact.deadline_integrity", "decision_date": "fact.deadline_integrity",
            "eligibility": "fact.eligibility_integrity", "country_eligibility": "fact.eligibility_integrity",
            "age": "fact.eligibility_integrity", "grade": "fact.eligibility_integrity",
            "funding": "fact.funding_integrity", "scholarship_coverage": "fact.funding_integrity",
            "fee": "fact.funding_integrity", "deposit": "fact.funding_integrity"}


def check_dom_facts(pages: list[dict], locks: list[FactLock], allowed_years: set[int]) -> tuple[list[QAIssue], dict[str, Metric]]:
    by_slot = {lk.slot: lk for lk in locks}
    issues: list[QAIssue] = []
    totals: dict[str, list[int]] = {}
    for page in pages:
        for f in page["facts"]:
            lk = by_slot.get(f["slot"])
            if lk is not None and f["display"] == "cond" and f.get("cond"):
                yes, _, no = f["cond"].partition("|")
                expected = yes if lk.value.canonical == "true" else no
            else:
                expected = (lk.display_ar if f["display"] == "ar" else lk.display_en) if lk else None
            ok = lk is not None and f["hash"] == lk.lock_hash and f["text"] == expected and lk.verify_integrity()
            cat = CATEGORY.get(lk.predicate if lk else "", "fact.other_integrity")
            t = totals.setdefault(cat, [0, 0])
            t[0] += 1
            t[1] += int(ok)
            t2 = totals.setdefault("fact.critical_accuracy", [0, 0])
            if lk is None or lk.criticality.value == "critical":
                t2[0] += 1
                t2[1] += int(ok)
            if not ok:
                issues.append(QAIssue(check="qa.dom_fact_integrity", severity="critical", page=page["pageId"],
                                      message=f"rendered fact {f['slot']}='{f['text']}' does not match its lock"))
            if not f["visible"]:
                issues.append(QAIssue(check="qa.dom_fact_integrity", severity="critical", page=page["pageId"],
                                      message=f"fact {f['slot']} is not visible (clipped/hidden)"))
        for i in page["items"]:
            for v in semantic_diff(i.get("diffText", i["text"]), locks, allowed_years=allowed_years):
                issues.append(QAIssue(check="qa.dom_fact_integrity", severity="critical", page=page["pageId"],
                                      selector=i["id"], message=f"visible text: {v.message}"))
                totals.setdefault("fact.critical_accuracy", [0, 0])[0] += 1
    metrics = {}
    for name in ("fact.critical_accuracy", "fact.deadline_integrity", "fact.eligibility_integrity",
                 "fact.funding_integrity"):
        n, ok = totals.get(name, [0, 0])
        metrics[name] = (Metric.measured(name, 100.0 * ok / n, "rendered DOM facts vs FactLocks (hash + display + "
                                                              "semantic diff of all visible text)", evidence=[f"{ok}/{n}"])
                         if n else Metric.not_measured(name, "no rendered facts in this category"))
    return issues, metrics
