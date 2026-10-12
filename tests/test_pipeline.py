"""End-to-end job pipeline (draft mode for speed) incl. human gate, resume and blocking behaviour."""

import json

import pytest

from apex_one.core.governor.runner import JobRunner
from apex_one.core.governor.mission import MissionAnalyzer
from apex_one.core.schemas.mission import JobStatus, OpportunityType
from tests.conftest import requires_browser

MISSION = "Create an APEX guide for Example Labor College Fall 2027"


def test_mission_analyzer():
    m, risk, privacy = MissionAnalyzer().analyze("Create an APEX guide for Berea College Fall 2027.")
    assert m.institution == "Berea College" and m.cycle == "Fall 2027" and m.cycle_year == 2027
    assert m.opportunity_type == OpportunityType.UNIVERSITY_ADMISSION and "deadline" in risk.critical_predicates
    assert privacy.value == "public"
    _, _, priv = MissionAnalyzer().analyze("Guide for Berea College Fall 2027 for me, phone 01012345678")
    assert priv.value == "private-student-data"


def test_budget_must_be_zero():
    with pytest.raises(ValueError):
        JobRunner.create(MISSION, budget=1.0, offline_fixture="synthetic_berea_style")


def test_live_job_without_research_route_blocks_cleanly():
    r = JobRunner.create("Create an APEX guide for Berea College Fall 2027", quality="draft")
    job = r.run()
    assert job.status == JobStatus.BLOCKED and job.state == "SOURCE_DISCOVERY"
    assert any("SEARXNG_URL" in b for b in job.blockers)
    # no fabricated facts were produced
    assert not r.rd.state.locks


def test_missing_cycle_blocks():
    r = JobRunner.create("Create an APEX guide for Berea College", quality="draft",
                         offline_fixture="synthetic_berea_style")
    job = r.run()
    assert job.status == JobStatus.BLOCKED and job.state == "MISSION_ANALYSIS"


@requires_browser
def test_golden_pipeline_reaches_release_candidate_and_needs_human():
    from apex_one.lab.benchmarks.golden import run_golden

    res = run_golden(quality="draft")
    assert res["all_passed"], res["checks"]
    r = JobRunner.load(res["job_id"])
    ws = r.ws
    for a in ("final.html", "final.pdf", "sources.json", "evidence.json", "claims.json", "contradictions.json",
              "document_ast.json", "design_decisions.json", "model_routing.json", "quality_report.json",
              "license_report.json", "contact_sheet.png", "job.json", "execution_plan.json", "opportunity_model.json",
              "design_intent.json", "reproducibility.json", "routing_decisions.jsonl", "checks.jsonl"):
        assert ws.exists(a), a
    assert list((ws.root / "screenshots").glob("page-*.png"))
    lic = json.loads((ws.root / "license_report.json").read_text())
    assert lic["prohibited_in_output"] == []
    checks = [json.loads(x) for x in (ws.root / "checks.jsonl").read_text().splitlines()]
    assert len(checks) >= 150
    # resume is idempotent at the human gate
    job = JobRunner.load(res["job_id"]).run()
    assert job.status == JobStatus.RELEASE_CANDIDATE and job.state == "HUMAN_APPROVAL"
    # only a human moves it to FINAL
    from apex_one.core.auth import create_approver, verify_ledger

    token = create_approver("Test Approver")
    job = JobRunner.load(res["job_id"]).approve(token, "golden benchmark approval")
    assert json.loads((ws.root / "human_approval.json").read_text())["approver"] == "Test Approver"
    assert verify_ledger()[0]
    assert job.status == JobStatus.FINAL
    assert (ws.root / "human_approval.json").exists()
    from apex_one.memory import ApprovalMemory, DesignMemory

    assert ApprovalMemory().by_key(res["job_id"])
    assert DesignMemory().signature_verdicts()


@requires_browser
def test_fact_conflict_requires_human_then_resumes(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.html").write_text("<h1>International Fall 2027</h1><p>The application deadline is January 5, 2027.</p>"
                              "<p>Tuition is fully covered: the scholarship covers 100% of tuition.</p>"
                              "<p>Admission is open to international students from all countries.</p>")
    (d / "b.html").write_text("<h1>Fall 2027 Guide</h1><p>The application deadline is January 9, 2027.</p>"
                              "<p>The scholarship covers 100% of tuition.</p>"
                              "<p>Admission is open to international students from all countries.</p>")
    (d / "sources.yaml").write_text(
        "sources:\n  - {url: 'https://www.uni.edu/a', file: a.html, kind: official, cycle_year: 2027}\n"
        "  - {url: 'https://www.uni.edu/b', file: b.html, kind: official, cycle_year: 2027}\n")
    r = JobRunner.create("Create an APEX guide for Uni College Fall 2027", quality="draft", sources=str(d))
    job = r.run()
    assert job.status == JobStatus.AWAITING_HUMAN and job.state == "FACT_RESOLUTION"
    claim = next(c for c in r.rd.state.claims if c.slot == "deadline.application" and c.value.canonical == "2027-01-05")
    r2 = JobRunner.load(job.job_id)
    r2.confirm_fact("deadline.application", claim.claim_id, "Registrar Check")
    job = JobRunner.load(job.job_id).run()
    assert job.state != "FACT_RESOLUTION"
    lk = next(x for x in JobRunner.load(job.job_id).rd.state.locks if x.slot == "deadline.application")
    assert lk.value.canonical == "2027-01-05" and lk.verified_by == "human:Registrar Check"
