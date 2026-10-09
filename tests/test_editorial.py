import pytest

from apex_one.core.schemas.document import Block, NodeType, TextRun
from apex_one.document.ast import MissingFact, parse_runs, runs_text
from apex_one.document.ast.builder import ast_problems
from apex_one.editorial.architect import NarrativeArchitect
from apex_one.editorial.language import review_document
from apex_one.reader_lab import ReaderSimulator, load_personas
from apex_one.reader_lab.simulator import ReadItem
from tests.helpers import editorial

YEARS = {2026, 2027}


def test_rhythm_plan():
    e = editorial()
    plan = e["plan"]
    assert plan[0].node_type == NodeType.COVER and plan[-1].node_type == NodeType.CLOSING
    assert NarrativeArchitect.rhythm_violations(plan) == []
    assert sum(1 for p in plan if p.rhythm_role == "loud") <= 2


def test_writer_output_is_fact_bound_and_clean():
    e = editorial()
    ast, locks = e["ast"], e["locks"]
    assert ast_problems(ast, locks) == []
    rv = review_document(ast, e["voice"], locks, allowed_years=YEARS)
    assert not [i for i in rv.issues if i.severity == "critical"], [i.message for i in rv.issues]
    assert rv.metrics["fact.text_alignment"].value == 100.0
    assert rv.metrics["editorial.human_or_model_judgement"].status.value == "NOT_MEASURED"
    text = " ".join(runs_text(b.runs) for n in ast.pages() for b in n.content)
    assert text.count("يا جيك") <= 3
    assert "حوالي" in text   # the hedged contribution is presented as an estimate


def test_opinions_are_labelled_and_facts_separate():
    ast = editorial()["ast"]
    take = next(n for n in ast.pages() if n.semantic_type == NodeType.APEX_TAKE)
    assert any(b.role == "label" and b.data.get("opinion") for b in take.content)
    for n in ast.pages():
        if n.semantic_type in (NodeType.WARNING, NodeType.ELIGIBILITY_CHAPTER, NodeType.FUNDING_CHAPTER):
            assert not any(b.data.get("humor") for b in n.content)


def test_missing_lock_drops_sentence_instead_of_guessing():
    e = editorial(drop_slots=("funding.student_contribution_per_year",))
    text = " ".join(runs_text(b.runs) for n in e["ast"].pages() for b in n.content)
    assert "1,000" not in text
    assert e["writer"].dropped or not any(n.semantic_type == NodeType.WARNING and
                                          "1,000" in runs_text(n.content[-1].runs) for n in e["ast"].pages())


def test_parse_runs_isolates_latin_and_requires_locks():
    e = editorial()
    locks = {lk.slot: lk for lk in e["locks"]}
    runs = parse_runs("آخر ميعاد للـ deadline هو {{deadline.application}} في Example College", locks)
    assert [r.kind for r in runs].count("term") == 2
    assert next(r for r in runs if r.kind == "fact").text == locks["deadline.application"].display_ar
    with pytest.raises(MissingFact):
        parse_runs("{{nonexistent.slot}}", locks)


@pytest.mark.parametrize("injection,check", [
    ("يرجى العلم بأن الموعد قريب", "voice.no_bureaucratic_msa"),
    ("دي فرصة ذهبية لا تعوض", "voice.no_ai_cliches"),
    ("آخر ميعاد 3 ديسمبر 2026", "alignment.semantic_diff_clean"),
    ("المنحة مضمون تاخدها", "claim_language.certainty"),
])
def test_critics_catch_violations(injection, check):
    e = editorial()
    ast = e["ast"].model_copy(deep=True)
    node = next(n for n in ast.pages() if n.semantic_type == NodeType.OPENING)
    node.content.append(Block(role="paragraph", runs=[TextRun(kind="text", text=injection, lang="ar")]))
    rv = review_document(ast, e["voice"], e["locks"], allowed_years=YEARS)
    assert any(i.check == check for i in rv.issues)


def test_humor_in_warning_is_critical():
    e = editorial()
    ast = e["ast"].model_copy(deep=True)
    node = next(n for n in ast.pages() if n.semantic_type == NodeType.WARNING)
    node.content.append(Block(role="aside", runs=[TextRun(kind="text", text="هههه", lang="ar")], data={"humor": True}))
    rv = review_document(ast, e["voice"], e["locks"], allowed_years=YEARS)
    assert any(i.check == "voice.humor_placement" and i.severity == "critical" for i in rv.issues)


def test_hedge_missing_is_critical():
    e = editorial()
    ast = e["ast"].model_copy(deep=True)
    lk = next(x for x in e["locks"] if x.hedge)
    node = next(n for n in ast.pages() if n.semantic_type == NodeType.OPENING)
    node.content.append(Block(role="paragraph", runs=[TextRun(kind="text", text="هتدفع ", lang="ar"),
                                                      TextRun(kind="fact", slot=lk.slot, claim_id=lk.claim_id,
                                                              text=lk.display_ar)]))
    rv = review_document(ast, e["voice"], e["locks"], allowed_years=YEARS)
    assert any(i.check == "claim_language.hedge_missing" for i in rv.issues)


def test_tampered_lock_detected_in_ast():
    e = editorial()
    locks = [lk.model_copy(update={"lock_hash": "0" * 64}) if lk.slot == "deadline.application" else lk
             for lk in e["locks"]]
    assert any("changed after AST" in p for p in ast_problems(e["ast"], locks))


def test_opportunity_model_understands_not_summarises():
    opp = editorial()["opp"]
    assert opp.likely_misunderstanding and opp.financial_risk and opp.hidden_value
    assert all(i.claim_refs for i in opp.core_value)
    assert any(i.kind == "apex_opinion" for i in opp.best_fit_student)
    assert opp.open_questions


def test_reader_simulator_detects_misunderstanding():
    e = editorial()
    locks = e["locks"]
    by = {lk.slot: lk for lk in locks}
    items = [ReadItem(f"تغطية {by['scholarship_coverage.tuition'].display_ar}", 1, 40, role="stat",
                      slots=["scholarship_coverage.tuition"]),
             ReadItem(f"آخر ميعاد {by['deadline.application'].display_ar}", 1, 30, role="stat",
                      slots=["deadline.application"]),
             ReadItem("x " * 400, 2, 12),
             ReadItem(f"حوالي {by['funding.student_contribution_per_year'].display_ar}", 3, 13,
                      slots=["funding.student_contribution_per_year"])]
    sim = ReaderSimulator(locks, ["deadline.application", "scholarship_coverage.tuition",
                                  "funding.student_contribution_per_year"])
    personas = {p.persona_id: p for p in load_personas()}
    rushed = sim.simulate(personas["last-minute"], items)
    assert any("costs nothing" in m for m in rushed.misunderstandings)
    careful = sim.simulate(personas["first-time"], items)
    assert not careful.misunderstandings
    _, metric = sim.run([personas["first-time"]], items)
    assert metric.status.value == "MEASURED" and "not a human study" in metric.method
