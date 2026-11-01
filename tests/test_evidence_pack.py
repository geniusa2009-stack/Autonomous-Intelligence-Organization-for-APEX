"""Evidence packs: a real opportunity can be validated from saved official evidence without live network access."""

import json
import shutil
from pathlib import Path

import yaml

from apex_one.settings import REPO_ROOT
from tests.conftest import requires_browser

FIXTURE = REPO_ROOT / "apex_one" / "research" / "fixtures" / "synthetic_berea_style"


def _test_pack(d: Path) -> Path:
    """The synthetic corpus converted into an evidence pack (saved HTML + a real PDF, reserved .invalid domains)."""
    from apex_one.research.browser.fetchers import text_to_pdf
    from apex_one.research.evidence_pack import init

    init(d)
    corpus = yaml.safe_load((FIXTURE / "corpus.yaml").read_text())
    out = []
    for doc in corpus["documents"]:
        f = doc["file"]
        if doc.get("render_pdf_from_text"):
            f = f.replace(".txt", ".pdf")
            (d / f).write_bytes(text_to_pdf((FIXTURE / doc["file"]).read_text()))
        else:
            shutil.copy(FIXTURE / f, d / f)
        out.append({"url": doc["url"], "file": f, "cycle_year": doc.get("cycle_year")})
    (d / "sources.yaml").write_text(yaml.safe_dump({"sources": out}))
    (d / "pack.yaml").write_text('opportunity: "Example Labor College Fall 2027"\nprepared_by: test\n'
                                 'prepared_at: "2026-11-01"\n')
    (d / "confirmations.yaml").write_text(yaml.safe_dump({"confirmations": [
        {"slot": "deadline.application", "value": "1 November 2026", "by": "Tester", "at": "2026-11-01"}]}))
    return d


def test_check_reports_problems_and_flags_test_domains(tmp_path):
    from apex_one.research.evidence_pack import check, init

    empty = tmp_path / "empty"
    assert init(empty) == ["pack.yaml", "sources.yaml", "confirmations.yaml"]
    rep = check(empty)
    assert not rep["ready"] and any("opportunity" in p for p in rep["problems"])
    assert any("no sources" in p for p in rep["problems"])
    pack = _test_pack(tmp_path / "pack")
    rep = check(pack)
    assert rep["ready"] and rep["test_pack"] and rep["warnings"] and len(rep["pack_sha256"]) == 64
    assert {s["kind"] for s in rep["sources"]} == {"html", "pdf"} and all(s["sha256"] for s in rep["sources"])
    (pack / "official_financial_aid.html").unlink()
    (pack / "notes.docx").write_bytes(b"x" * 300)
    man = yaml.safe_load((pack / "sources.yaml").read_text())
    man["sources"].append({"url": "https://ok.edu/notes", "file": "notes.docx"})
    (pack / "sources.yaml").write_text(yaml.safe_dump(man))
    rep = check(pack)
    assert not rep["ready"] and any("file missing" in p for p in rep["problems"])
    assert any("only .html/.htm/.pdf" in p for p in rep["problems"])


@requires_browser
def test_offline_pack_runs_the_whole_pipeline_and_never_counts_as_real(tmp_path):
    from apex_one.lab.blockers import probe_real_job_release_candidate
    from apex_one.research.evidence_pack import run

    rep = run(_test_pack(tmp_path / "pack"), quality="draft")
    st = rep["stages"]
    assert rep["state"] == "RELEASE_CANDIDATE" and st["guide_built"] and st["qa_report"] and st["citations_mapped"]
    assert st["fact_locks"] > 10 and st["deadline_validation"] != "NO LOCK"
    assert st["eligibility_validation"] != "NO LOCK" and st["funding_validation"] != "NO LOCK"
    # the only thing between this pack and a release candidate is the (missing) official brand package
    assert rep["blockers"] and all("brand_production_assets" in b for b in rep["blockers"])
    assert rep["counts_as_real_opportunity"] is False
    assert all(not a["applied"] for a in rep["confirmations_applied"])      # nothing was awaiting a human
    assert probe_real_job_release_candidate()[0] is False                  # a test pack never validates REAL


def test_probe_counts_only_real_domain_jobs_at_release_candidate(tmp_path, monkeypatch):
    from apex_one.lab.blockers import probe_real_job_release_candidate
    from apex_one.settings import get_settings

    def job(jid, url, status):
        pack = tmp_path / jid
        pack.mkdir()
        (pack / "sources.yaml").write_text(yaml.safe_dump({"sources": [{"url": url, "file": "a.html"}]}))
        d = get_settings().jobs_dir / jid
        d.mkdir(parents=True)
        (d / "job.json").write_text(json.dumps({"job_id": jid, "status": status, "source_inputs": [str(pack)],
                                                "offline_fixture": None, "mission": {}}))
    job("J-test", "https://admissions.example-labor-college.invalid/x", "RELEASE_CANDIDATE")
    assert probe_real_job_release_candidate()[0] is False
    job("J-real", "https://www.berea.edu/admissions", "RELEASE_CANDIDATE")
    ok, ev = probe_real_job_release_candidate()
    assert ok and "J-real" in ev and "J-test" not in ev


def test_confirmations_lock_only_values_an_extracted_claim_carries(tmp_path):
    from types import SimpleNamespace

    from apex_one.research.evidence_pack import apply_confirmations

    def claim(cid, slot, raw, canonical):
        return SimpleNamespace(claim_id=cid, slot=slot, status=SimpleNamespace(value="NEEDS_HUMAN"),
                               value=SimpleNamespace(raw=raw, canonical=canonical))
    locked = []
    runner = SimpleNamespace(rd=SimpleNamespace(state=SimpleNamespace(claims=[
        claim("c1", "deadline.application", "16 February 2027", "2027-02-16")])),
        confirm_fact=lambda slot, cid, by: locked.append((slot, cid, by)))
    (tmp_path / "confirmations.yaml").write_text(yaml.safe_dump({"confirmations": [
        {"slot": "deadline.application", "value": "16 February 2027", "by": "Ahmed", "at": "2026-11-01"},
        {"slot": "deadline.application", "value": "20 February 2027", "by": "Ahmed", "at": "2026-11-01"},
        {"slot": "funding.stipend", "value": "$3,000", "by": "Ahmed", "at": "2026-11-01"}]}))
    out = apply_confirmations(runner, tmp_path)
    assert locked == [("deadline.application", "c1", "Ahmed (2026-11-01)")]
    assert [a["applied"] for a in out] == [True, False, False]
    assert "no extracted claim carries this value" in out[1]["why"] and "not awaiting" in out[2]["why"]
