"""Real Chromium rendering + deterministic QA (skipped only if Chromium is unavailable)."""

import random

import pytest

from apex_one.design.genome import load_genome, sample_genes
from apex_one.design.intent import derive_intent
from apex_one.document.compiler import compile_document, compile_page
from apex_one.qa.deterministic import document_qa
from apex_one.vision.contact_sheet import contact_sheet, rhythm_analysis
from apex_one.vision.page import derive_images
from apex_one.vision.render import Renderer, ensure_fonts
from tests.conftest import requires_browser
from tests.helpers import editorial

pytestmark = [requires_browser, pytest.mark.browser]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    out = tmp_path_factory.mktemp("render")
    e = editorial()
    g = load_genome()
    locks = {lk.slot: lk for lk in e["locks"]}
    pages = e["ast"].pages()
    rng = random.Random(11)
    compiled = []
    for i, n in enumerate(pages, 1):
        genes = sample_genes(g, derive_intent(n), rng)
        compiled.append(compile_page(n, genes, g, locks, page_no=i, total_pages=len(pages), synthetic=True))
    ensure_fonts(out)
    (out / "doc.html").write_text(compile_document(compiled, g, title="t", synthetic=True), encoding="utf-8")
    with Renderer() as r:
        res = r.render_full(out / "doc.html", out, pdf_path=out / "doc.pdf")
    return e, g, res, out, compiled


def test_render_produces_pages_pdf_mobile(rendered):
    e, g, res, out, compiled = rendered
    assert len(res.page_screenshots) == len(e["ast"].pages())
    assert res.pdf_path.exists() and res.mobile_screenshot.exists()
    assert {"IBM Plex Sans Arabic", "Readex Pro"} <= {f.split(":")[0] for f in res.metrics["fonts"]}
    assert res.metrics["htmlDir"] == "rtl"


def test_document_qa_fact_integrity_and_print(rendered):
    e, g, res, out, compiled = rendered
    report, pages = document_qa(res.metrics, g, e["locks"], allowed_years={2026, 2027, 2028},
                                pdf_path=res.pdf_path, mobile=res.mobile_metrics)
    assert report.metrics["fact.critical_accuracy"].value == 100.0
    assert report.metrics["print.fidelity"].value >= 90
    assert not [i for i in report.issues if i.check == "qa.dom_fact_integrity"]
    assert not [i for i in report.issues if i.check in ("qa.rtl_direction", "qa.mixed_runs")]
    assert report.metrics["mobile.readability"].status.value == "MEASURED"
    assert all(p.metrics["design.hierarchy"].status.value == "MEASURED" for p in pages)


def test_tampered_dom_fact_is_critical(rendered, tmp_path):
    e, g, res, out, compiled = rendered
    html = (out / "doc.html").read_text(encoding="utf-8")
    lk = next(x for x in e["locks"] if x.slot == "deadline.application")
    tampered = html.replace(f">{lk.display_ar}<", ">2 نوفمبر 2026<", 1)
    assert tampered != html
    p = out / "tampered.html"
    p.write_text(tampered, encoding="utf-8")
    with Renderer() as r:
        m = r.measure(p).metrics
    report, _ = document_qa(m, g, e["locks"], allowed_years={2026, 2027})
    assert any(i.check == "qa.dom_fact_integrity" and i.severity == "critical" for i in report.issues)
    assert report.metrics["fact.critical_accuracy"].value < 100


def test_contact_sheet_and_rhythm(rendered, tmp_path):
    e, g, res, out, compiled = rendered
    sheet = contact_sheet(res.page_screenshots, tmp_path / "sheet.png")
    assert sheet.exists()
    issues, metrics, data = rhythm_analysis(res.page_screenshots, [c.archetype for c in compiled],
                                            [n.rhythm_role for n in e["ast"].pages()], [c.signature for c in compiled])
    assert metrics["document.rhythm"].status.value == "MEASURED"
    assert len(data["luminance"]) == len(res.page_screenshots)
    imgs = derive_images(res.page_screenshots[0], tmp_path / "derived")
    assert {"thumbnail", "grayscale", "blur", "zoom-top"} <= set(imgs)


def test_layout_tournament_evolves_and_rejects_critical(tmp_path):
    from apex_one.design.tournament import LayoutTournament

    e = editorial()
    g = load_genome()
    node = next(n for n in e["ast"].pages() if n.semantic_type.value == "FundingChapter")
    with Renderer() as r:
        t = LayoutTournament(g, e["locks"], r, tmp_path / "c", population=4, generations=2, elite=1, epsilon=0.0,
                             seed=3, synthetic=True, allowed_years={2026, 2027})
        out = t.run_page(node, 5, 13, [], initial=6)
    assert out.evaluated >= 6 and out.best.fitness is not None
    assert not out.best.critical_failures
    assert out.best.metrics["specialist_reward"].status.value == "NOT_MEASURED"   # never imputed
    assert len(out.top) >= 1


def test_design_bench_all_measured_cases_pass(tmp_path):
    from apex_one.lab.benchmarks.design_bench import run_design_bench

    res = run_design_bench(tmp_path)
    failed = [c for c in res["cases"] if c["status"] == "FAIL"]
    assert not failed, failed
    assert res["not_measured"] == 2 and res["measured"] >= 19


def test_weasyprint_fallback_renders_pdf(rendered, tmp_path):
    pytest.importorskip("weasyprint")
    from apex_one.qa.print import check_pdf
    from apex_one.vision.render.renderer import pdf_with_weasyprint

    e, g, res, out, compiled = rendered
    pdf = pdf_with_weasyprint(out / "doc.html", tmp_path / "fallback.pdf")
    issues, metrics = check_pdf(pdf, len(compiled), [])
    assert pdf.exists() and metrics["print.fidelity"].status.value == "MEASURED"
