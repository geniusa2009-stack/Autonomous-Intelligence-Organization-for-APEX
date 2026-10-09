"""Print QA on the real PDF (PyMuPDF): page size, page count, embedded fonts, extractable locked values."""

from __future__ import annotations

from pathlib import Path

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.quality import QAIssue
from apex_one.research.evidence.normalize import to_ascii_digits

A4_PT = (595.28, 841.89)


def check_pdf(pdf_path: Path, expected_pages: int, locks: list[FactLock]) -> tuple[list[QAIssue], dict[str, Metric]]:
    import pymupdf

    issues: list[QAIssue] = []
    if not pdf_path.exists():
        return [QAIssue(check="print.pdf_exists", severity="critical", message="PDF missing")], \
            {"print.fidelity": Metric.not_measured("print.fidelity", "no PDF")}
    doc = pymupdf.open(str(pdf_path))
    penalty = 0.0
    if doc.page_count != expected_pages:
        issues.append(QAIssue(check="print.page_count", severity="critical",
                              message=f"PDF has {doc.page_count} pages, expected {expected_pages}"))
        penalty += 40
    bad_size = [i + 1 for i, p in enumerate(doc) if abs(p.rect.width - A4_PT[0]) > 2 or abs(p.rect.height - A4_PT[1]) > 2]
    if bad_size:
        issues.append(QAIssue(check="print.page_dimensions", severity="critical", message=f"non-A4 pages {bad_size[:5]}"))
        penalty += 30
    not_embedded = set()
    for p in doc:
        for f in p.get_fonts(full=True):
            if f[1] in ("n/a", "") and f[2] not in ("Type3",):
                not_embedded.add(f[3])
    if not_embedded:
        issues.append(QAIssue(check="print.fonts_embedded", severity="major", message=f"fonts not embedded {sorted(not_embedded)[:4]}"))
        penalty += 15
    text = to_ascii_digits(" ".join(p.get_text() for p in doc))
    missing = [lk.slot for lk in locks if lk.value.type.value in ("date", "money", "percent")
               and to_ascii_digits(lk.display_ar).split()[0] not in text]
    if missing:
        issues.append(QAIssue(check="print.text_extractable", severity="major",
                              message=f"locked values not extractable from PDF text: {missing[:4]}"))
        penalty += 5 * min(4, len(missing))
    doc.close()
    return issues, {"print.fidelity": Metric.measured("print.fidelity", max(0.0, 100 - penalty),
                                                      "PDF structure checks (A4 size, page count, embedded fonts, "
                                                      "extractable locked values)")}
