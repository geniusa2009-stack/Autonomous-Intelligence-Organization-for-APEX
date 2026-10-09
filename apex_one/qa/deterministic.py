"""Deterministic QA orchestration. Critical deterministic failure = reject."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from apex_one.core.schemas.common import Metric, MetricStatus
from apex_one.core.schemas.design import DesignGenome
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.quality import QAIssue, QAReport
from apex_one.qa.accessibility import check_accessibility
from apex_one.qa.brand import check_brand
from apex_one.qa.facts_dom import check_dom_facts
from apex_one.qa.geometry import check_geometry
from apex_one.qa.hierarchy import check_hierarchy
from apex_one.qa.print import check_pdf
from apex_one.qa.rtl import check_rtl
from apex_one.qa.typography import check_typography

LAYOUT_CRITICAL = {"qa.overflow", "qa.clipping", "qa.collision", "qa.margins", "qa.page_bounds", "qa.long_urls",
                   "qa.rtl_direction"}


@dataclass
class PageQA:
    page_id: str
    issues: list[QAIssue] = field(default_factory=list)
    metrics: dict[str, Metric] = field(default_factory=dict)
    predicted_first: str | None = None

    @property
    def critical(self) -> list[QAIssue]:
        return [i for i in self.issues if i.severity == "critical"]


def page_qa(page: dict, genome: DesignGenome, locks: list[FactLock], *, allowed_years: set[int],
            fonts_loaded: list[str], html_dir: str = "rtl") -> PageQA:
    inv = genome.invariants
    out = PageQA(page_id=page["pageId"])
    limits = {**inv["typography"]}
    for fn in (lambda: check_geometry(page, float(inv["page"]["min_margin_mm"]), limits),
               lambda: check_typography(page, inv["typography"], list(inv["fonts"].values())),
               lambda: check_rtl(page, html_dir),
               lambda: check_accessibility(page),
               lambda: check_brand(page, inv, fonts_loaded),
               lambda: check_dom_facts([page], locks, allowed_years)):
        issues, metrics = fn()
        out.issues += issues
        out.metrics.update(metrics)
    out.predicted_first, out.metrics["design.hierarchy"] = check_hierarchy(page)
    return out


def _mean(metrics: list[Metric], name: str, method: str) -> Metric:
    vals = [m.value for m in metrics if m.status == MetricStatus.MEASURED and m.value is not None]
    if not vals:
        return Metric.not_measured(name, "no measured page values")
    return Metric.measured(name, sum(vals) / len(vals), f"mean over pages: {method}",
                           evidence=[f"min={min(vals):.1f}", f"n={len(vals)}"])


def mobile_qa(mobile: dict | None) -> tuple[list[QAIssue], Metric]:
    if not mobile:
        return [], Metric.not_measured("mobile.readability", "no mobile render")
    issues = []
    penalty = 0.0
    vw = mobile["viewport"]["w"]
    for p in mobile["pages"]:
        if p["scrollW"] > vw + 1:
            issues.append(QAIssue(check="mobile.horizontal_scroll", severity="major", page=p["pageId"],
                                  message=f"document {p['scrollW']}px wide on a {vw}px screen"))
            penalty += 20
            break
    small = [i for p in mobile["pages"] for i in p["items"]
             if i["role"] in ("paragraph", "list_item", "lead", "warning") and i["fontPx"] < 15]
    if small:
        issues.append(QAIssue(check="mobile.font_size", severity="major", message=f"{len(small)} body blocks < 15px on mobile"))
        penalty += min(40, 2 * len(small))
    over = [i for p in mobile["pages"] for i in p["items"] if i["overflowX"] > 1]
    if over:
        issues.append(QAIssue(check="mobile.overflow", severity="major", message=f"{len(over)} blocks overflow on mobile"))
        penalty += min(40, 5 * len(over))
    return issues, Metric.measured("mobile.readability", max(0.0, 100 - penalty),
                                   "responsive reflow at 390px: horizontal scroll, font size, overflow")


def document_qa(metrics: dict, genome: DesignGenome, locks: list[FactLock], *, allowed_years: set[int],
                pdf_path: Path | None = None, mobile: dict | None = None) -> tuple[QAReport, list[PageQA]]:
    pages = [page_qa(p, genome, locks, allowed_years=allowed_years, fonts_loaded=metrics.get("fonts", []),
                     html_dir=metrics.get("htmlDir", "rtl")) for p in metrics["pages"]]
    report = QAReport(scope="document")
    for pq in pages:
        report.issues += pq.issues
    for name, method in (("design.typography", "typography rules"), ("rtl.quality", "bidi rules"),
                         ("design.brand_fit", "brand invariants"), ("design.hierarchy", "DOM saliency"),
                         ("accessibility.contrast", "WCAG contrast"), ("geometry.alignment", "edge alignment")):
        report.metrics[name] = _mean([pq.metrics[name] for pq in pages if name in pq.metrics], name, method)
    fact_issues, fact_metrics = check_dom_facts(metrics["pages"], locks, allowed_years)
    report.metrics.update(fact_metrics)
    layout_crit = [i for i in report.issues if i.severity == "critical" and i.check in LAYOUT_CRITICAL]
    report.metrics["qa.critical_layout_failures"] = Metric.measured(
        "qa.critical_layout_failures", len(layout_crit), "count of critical geometry/RTL failures", unit="count")
    if pdf_path is not None:
        pi, pm = check_pdf(pdf_path, len(metrics["pages"]), locks)
        report.issues += pi
        report.metrics.update(pm)
    else:
        report.metrics["print.fidelity"] = Metric.not_measured("print.fidelity", "no PDF produced")
    mi, mm = mobile_qa(mobile)
    report.issues += mi
    report.metrics["mobile.readability"] = mm
    return report, pages
