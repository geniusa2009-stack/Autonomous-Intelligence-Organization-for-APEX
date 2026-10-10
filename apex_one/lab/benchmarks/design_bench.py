"""APEX Design Bench — targeted, rendered, measured tests of APEX-specific design risks.

Two kinds of cases:
* PASS cases: correct content must render with no critical issue and no issue of the probed check.
* DETECT cases: deliberately broken content must be caught by the probed check (a QA that misses it fails).
Cases that need an unavailable specialist (e.g. screenshot-to-code) report NOT_MEASURED — never a guess.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apex_one.core.schemas.design import Genes
from apex_one.core.schemas.document import Block, DocNode, NodeType, ReadingMode, TextRun
from apex_one.core.schemas.evidence import FactLock, NormalizedValue, ValueType
from apex_one.design.genome import load_genome
from apex_one.document.ast.runs import parse_runs
from apex_one.document.compiler import compile_document, compile_page
from apex_one.qa.deterministic import page_qa
from apex_one.research.evidence.normalize import display
from apex_one.vision.render import Renderer, ensure_fonts

YEARS = {2026, 2027, 2028}


def _lock(slot: str, vtype: ValueType, canonical: str, raw: str, **kw: Any) -> FactLock:
    v = NormalizedValue(type=vtype, raw=raw, canonical=canonical, **kw)
    en, ar = display(v)
    pred, _, qual = slot.partition(".")
    return FactLock(claim_id=f"C-bench-{slot}", slot=slot, predicate=pred, qualifier=qual.replace("_", " "), value=v,
                    display_en=en, display_ar=ar, source_ids=["S-bench"])


BENCH_LOCKS = [
    _lock("deadline.application", ValueType.DATE, "2026-11-01", "November 1, 2026"),
    _lock("fee.application", ValueType.MONEY, "USD 50", "$50", currency="USD", amount=50.0),
    _lock("scholarship_coverage.tuition", ValueType.PERCENT, "100%", "100%", amount=100.0),
    _lock("funding.student_contribution_per_year", ValueType.MONEY, "USD 1000", "$1,000", currency="USD", amount=1000.0),
]
LOCKS = {lk.slot: lk for lk in BENCH_LOCKS}


def _node(ntype: NodeType, blocks: list[tuple[str, str, dict]], *, density: float = 0.5,
          reading: ReadingMode = ReadingMode.READ) -> DocNode:
    content = []
    for role, tpl, data in blocks:
        lang = data.pop("_lang", "ar")
        content.append(Block(role=role, runs=parse_runs(tpl, LOCKS, base_lang=lang), data=data))
    n = DocNode(semantic_type=ntype, content=content, visual_density=density, reading_mode=reading)
    n.first_fixation = next((b.block_id for b in content if b.role in ("hero", "stat")),
                            next((b.block_id for b in content if b.role == "heading"), content[0].block_id))
    return n


@dataclass
class Case:
    name: str
    expectation: str            # "pass:<check>" or "detect:<check>" or "not_measured:<reason>"
    build: Callable[[], tuple[DocNode, Genes, Callable[[str], str] | None]]


def _g(**kw: Any) -> Genes:
    base = dict(archetype="editorial-column", column_structure="12", base_font_px=16.0, type_scale_ratio=1.333,
                density=0.5, whitespace=0.5, margin_mm=18.0, tone="light", visual_metaphor="none",
                section_division="space")
    base.update(kw)
    return Genes(**base)


def _paragraphs(n: int) -> list[tuple[str, str, dict]]:
    txt = ("الفرصة دي محتاجة تحضير بدري عشان الورق بياخد وقت، وخصوصاً امتحان الإنجليزي والجوابات. "
           "خلّي عندك جدول واضح وراجع كل حاجة مرتين قبل ما تبعت.")
    return [("paragraph", txt, {}) for _ in range(n)]


def cases() -> list[Case]:
    H = ("heading", "عنوان الصفحة", {})
    return [
        Case("arabic_rtl", "pass:qa.rtl_direction",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(2)), _g(), None)),
        Case("arabic_english_mix", "pass:qa.ltr_isolation",
             lambda: (_node(NodeType.OPENING, [H, ("paragraph", "قدّم الـ [[essay]] والـ [[transcripts]] قبل الـ [[deadline]].", {})]),
                      _g(), None)),
        Case("arabic_dollar", "pass:qa.currency",
             lambda: (_node(NodeType.FUNDING_CHAPTER, [H, ("paragraph", "رسوم التقديم {{fee.application|en}} بس.", {})]), _g(), None)),
        Case("arabic_percent", "pass:qa.percent",
             lambda: (_node(NodeType.HERO_FACT, [("hero", "{{scholarship_coverage.tuition}}", {}),
                                                 ("paragraph", "تغطية {{scholarship_coverage.tuition}} من المصاريف.", {})],
                            density=0.15, reading=ReadingMode.GLANCE), _g(archetype="hero-number"), None)),
        Case("arabic_date", "pass:qa.dom_fact_integrity",
             lambda: (_node(NodeType.TIMELINE, [H, ("step", "{{deadline.application}}", {"label": "آخر ميعاد"})]),
                      _g(archetype="timeline-rail"), None)),
        Case("very_long_arabic_title", "pass:qa.overflow",
             lambda: (_node(NodeType.OPENING, [("heading", "دليل كامل ومفصّل جداً للتقديم في الكلية للطلاب المصريين اللي "
                                                           "عايزين يفهموا كل حاجة عن المنحة والمصاريف والمواعيد والشروط", {})]
                            + _paragraphs(1)), _g(type_scale_ratio=1.5), None)),
        Case("dense_funding_page", "pass:qa.page_bounds",
             lambda: (_node(NodeType.FUNDING_CHAPTER, [H] + [("list_item", "بند مصاريف مهم لازم تحسبه كويس قبل ما تقرر", {})
                                                             for _ in range(10)] + _paragraphs(2), density=0.8),
                      _g(density=0.8, whitespace=0.25, base_font_px=15.0), None)),
        Case("deadline_visibility", "pass:design.hierarchy>=80",
             lambda: (_node(NodeType.OPPORTUNITY_SNAPSHOT, [H, ("stat", "{{deadline.application}}", {"label": "آخر ميعاد"}),
                                                            ("stat", "{{fee.application}}", {"label": "الرسوم"})],
                            reading=ReadingMode.SCAN), _g(archetype="ledger"), None)),
        Case("brand_consistency", "pass:brand.palette",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(tone="dark"), None)),
        Case("card_overuse", "detect:vision.card_overuse",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(4)), _g(),
                      lambda html: html.replace("</style>", ".blk-paragraph{border:1px solid #A9B3C1;background:#ECEFF3;"
                                                            "border-radius:4px;padding:8px}</style>"))),
        Case("gradient_forbidden", "detect:brand.gradients",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(),
                      lambda html: html.replace("</style>", ".blk-heading{background-image:linear-gradient(#0A1A33,#24426E)}</style>"))),
        Case("mixed_direction_punctuation", "detect:qa.mixed_runs",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(),
                      lambda html: html.replace('<bdi class="pno" dir="ltr">', '<span class="pno">').replace(
                          "</bdi><bdi class=\"syn\"", "</span><bdi class=\"syn\"")
                      .replace('<bdi class="pno" dir="ltr">', ""))),
        Case("unisolated_latin", "detect:qa.ltr_isolation",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(),
                      lambda html: html.replace("عنوان الصفحة", "عنوان الصفحة deadline here"))),
        Case("long_url", "pass:qa.overflow",
             lambda: (_node(NodeType.CLOSING, [H, ("paragraph", "المصدر: https://admissions.example-labor-college.invalid/"
                                                                "international/fall-2027/requirements/documents/checklist-and-"
                                                                "financial-statement-instructions-for-applicants", {})]), _g(), None)),
        Case("beautiful_but_misleading", "detect:qa.dom_fact_integrity",
             lambda: (_node(NodeType.HERO_FACT, [("hero", "{{scholarship_coverage.tuition}}", {})], density=0.15),
                      _g(archetype="hero-number", tone="dark"),
                      lambda html: html.replace(">100%<", ">100% + السكن<", 1))),
        Case("boring_but_correct", "pass:qa.dom_fact_integrity",
             lambda: (_node(NodeType.FUNDING_CHAPTER, [H, ("paragraph", "رسوم التقديم {{fee.application}}.", {})]),
                      _g(type_scale_ratio=1.2, base_font_px=14.5), None)),
        Case("low_contrast_detect", "detect:qa.contrast",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(),
                      lambda html: html.replace("</style>", ".blk-paragraph{color:#D5DBE3}</style>"))),
        Case("overflow_detect", "detect:qa.overflow",
             lambda: (_node(NodeType.FUNDING_CHAPTER, [H] + _paragraphs(40)), _g(base_font_px=18.0), None)),
        Case("arabic_letter_spacing_detect", "detect:qa.arabic_letter_spacing",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(),
                      lambda html: html.replace("</style>", ".blk-heading{letter-spacing:.12em}</style>"))),
        Case("arabic_italic_detect", "detect:qa.arabic_italic",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(),
                      lambda html: html.replace("</style>", ".blk-paragraph{font-style:italic}</style>"))),
        Case("arabic_tight_leading_detect", "detect:qa.arabic_leading",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(2)), _g(),
                      lambda html: html.replace("</style>", ".blk-paragraph{line-height:1.45 !important}</style>"))),
        Case("arabic_typography_clean", "pass:qa.arabic_letter_spacing",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(2)), _g(), None)),
        Case("print_fidelity", "pass:print",
             lambda: (_node(NodeType.OPENING, [H] + _paragraphs(1)), _g(), None)),
        Case("screenshot_to_code_regression", "not_measured:requires ScreenCoder/DCGen (not available on a $0 "
                                              "licence-verified route)", lambda: (None, None, None)),  # type: ignore[arg-type]
        Case("graphic_design_bench_gdb", "not_measured:GDB runs separately (apex-one bench gdb): lica-gdb is installed, "
                                         "but the full dataset host (Hugging Face) is unreachable from this container",
             lambda: (None, None, None)),  # type: ignore[arg-type]
    ]


def run_design_bench(out_dir: Path) -> dict:
    genome = load_genome()
    out_dir.mkdir(parents=True, exist_ok=True)
    ensure_fonts(out_dir)
    results = []
    rng = random.Random(7)
    with Renderer() as r:
        for case in cases():
            kind, _, probe = case.expectation.partition(":")
            if kind == "not_measured":
                results.append({"case": case.name, "status": "NOT_MEASURED", "expectation": case.expectation,
                                "detail": probe})
                continue
            node, genes, mutate_html = case.build()
            page = compile_page(node, genes, genome, LOCKS, page_no=2, total_pages=3, synthetic=True,
                                seed=rng.randrange(1000))
            html = compile_document([page], genome, title=case.name, synthetic=True)
            if mutate_html:
                html = mutate_html(html)
            path = out_dir / f"{case.name}.html"
            path.write_text(html, encoding="utf-8")
            if probe == "print":
                pdf = out_dir / f"{case.name}.pdf"
                res = r.render_full(path, out_dir / case.name, pdf_path=pdf)
                from apex_one.qa.print import check_pdf

                issues, metrics = check_pdf(pdf, 1, [])
                ok = not [i for i in issues if i.severity in ("critical", "major")]
                results.append({"case": case.name, "status": "PASS" if ok else "FAIL", "expectation": case.expectation,
                                "detail": f"print.fidelity={metrics['print.fidelity'].value}"})
                continue
            res = r.measure(path, float(genome.invariants["page"]["min_margin_mm"]))
            pq = page_qa(res.metrics["pages"][0], genome, BENCH_LOCKS, allowed_years=YEARS,
                         fonts_loaded=res.metrics.get("fonts", []), html_dir=res.metrics.get("htmlDir", "rtl"))
            checks = {i.check for i in pq.issues if i.severity in ("critical", "major")}
            if ">=" in probe:
                metric, _, thr = probe.partition(">=")
                val = pq.metrics[metric].value or 0
                ok = val >= float(thr)
                detail = f"{metric}={val:.1f}"
            elif kind == "pass":
                ok = probe not in checks and not pq.critical
                detail = "issues: " + ", ".join(sorted(checks)) if checks else "clean"
            else:
                ok = probe in checks
                detail = "detected" if ok else f"MISSED; got {sorted(checks)}"
            results.append({"case": case.name, "status": "PASS" if ok else "FAIL", "expectation": case.expectation,
                            "detail": detail})
    measured = [x for x in results if x["status"] != "NOT_MEASURED"]
    summary = {"cases": results, "measured": len(measured), "passed": sum(1 for x in measured if x["status"] == "PASS"),
               "not_measured": len(results) - len(measured)}
    (out_dir / "design_bench.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
