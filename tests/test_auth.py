"""Release-control authentication: identity comes from a token, never from a typed name; decisions are ledgered."""

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from apex_one.core.auth import (AuthError, append_ledger, auth_dir, authenticate, check_claimed_name, create_approver,
                                revoke_approver, verify_ledger)


def test_token_identity_and_storage():
    tok = create_approver("Ahmed")
    ident = authenticate(tok)
    assert ident.name == "Ahmed" and ident.role == "release_approver"
    stored = (auth_dir() / "approvers.json").read_text()
    assert tok not in stored                       # only the hash is kept
    with pytest.raises(AuthError):
        authenticate(None)
    with pytest.raises(AuthError):
        authenticate("apx_guessed")
    with pytest.raises(AuthError, match="forged"):
        check_claimed_name(ident, "Someone Else")
    check_claimed_name(ident, "Ahmed")
    revoke_approver("Ahmed")
    with pytest.raises(AuthError, match="revoked"):
        authenticate(tok)


def test_ledger_detects_tampering():
    create_approver("A")
    append_ledger({"event": "release_decision", "decision": "APPROVED", "job_id": "J-1", "approver": "A"})
    append_ledger({"event": "release_decision", "decision": "REJECTED", "job_id": "J-2", "approver": "A"})
    assert verify_ledger() == (True, [])
    path = auth_dir() / "approval_ledger.jsonl"
    lines = path.read_text().splitlines()
    edited = json.loads(lines[1])
    edited["approver"] = "Mallory"
    path.write_text("\n".join([lines[0], json.dumps(edited), *lines[2:]]) + "\n")
    ok, problems = verify_ledger()
    assert not ok and any("altered" in p for p in problems)
    path.write_text("\n".join([lines[0], *lines[2:]]) + "\n")          # deletion
    ok, problems = verify_ledger()
    assert not ok and any("deleted" in p or "chain" in p for p in problems)


def _candidate_job():
    """A job object parked at the human gate without running the full pipeline."""
    from apex_one.core.governor.runner import JobRunner
    from apex_one.core.schemas.mission import JobStatus
    from apex_one.core.state_machine.definition import S

    r = JobRunner.create("Create an APEX guide for Example Labor College", quality="draft",
                         offline_fixture="synthetic_berea_style")
    r.sm.state = S.HUMAN_APPROVAL
    r.job.state, r.job.status = S.HUMAN_APPROVAL.value, JobStatus.RELEASE_CANDIDATE
    r.save()
    return r


def test_api_rejects_anonymous_and_forged_and_accepts_authorised(monkeypatch):
    from apex_one.apps.api.main import app
    from apex_one.core.governor.runner import JobRunner

    r = _candidate_job()
    jid = r.job.job_id
    monkeypatch.setattr(JobRunner, "run", lambda self: self.job)        # stop after the gate decision
    c = TestClient(app)
    tok = create_approver("Director")
    assert c.post(f"/jobs/{jid}/approve", json={"notes": "x"}).status_code == 401
    assert c.post(f"/jobs/{jid}/approve", json={}, headers={"Authorization": "Bearer apx_nope"}).status_code == 401
    h = {"Authorization": f"Bearer {tok}"}
    forged = c.post(f"/jobs/{jid}/approve", json={"approver": "Someone Else"}, headers=h)
    assert forged.status_code == 403 and "forged" in forged.text
    assert JobRunner.load(jid).job.state == "HUMAN_APPROVAL"         # nothing happened
    ok = c.post(f"/jobs/{jid}/approve", json={"notes": "looks right"}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "FINAL"
    rec = json.loads((JobRunner.load(jid).ws.root / "human_approval.json").read_text())
    assert rec["approver"] == "Director" and rec["authenticated"] and rec["ledger_hash"]
    entries = [json.loads(x) for x in (auth_dir() / "approval_ledger.jsonl").read_text().splitlines()]
    assert entries[-1]["decision"] == "APPROVED" and entries[-1]["job_id"] == jid
    assert verify_ledger()[0]


def test_runner_approve_needs_a_token():
    r = _candidate_job()
    with pytest.raises(AuthError):
        r.approve(None, "x")
    with pytest.raises(AuthError):
        r.approve("Director", "names are not tokens")


def test_cli_approve_requires_token(monkeypatch):
    from apex_one.apps.cli.main import app as cli
    from apex_one.core.governor.runner import JobRunner

    r = _candidate_job()
    monkeypatch.setattr(JobRunner, "run", lambda self: self.job)
    monkeypatch.delenv("APEX_APPROVER_TOKEN", raising=False)
    runner = CliRunner()
    res = runner.invoke(cli, ["approve", r.job.job_id, "--by", "Director"])
    assert res.exit_code == 3 and "Not authorised" in res.stdout
    tok = create_approver("Director")
    res = runner.invoke(cli, ["approve", r.job.job_id], env={"APEX_APPROVER_TOKEN": tok})
    assert res.exit_code == 0, res.stdout
    assert JobRunner.load(r.job.job_id).job.status.value == "FINAL"
