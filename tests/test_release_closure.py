"""Production closure: acceptance rule, release check, brand intake rejections, FINAL export + release verification,
the validated baseline and the approval audit history."""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from apex_one.settings import REPO_ROOT, reset_settings_cache
from tests.test_ultra import _brand_pkg

REQUIRED = {"BRAND_ASSETS_VALIDATED", "AUTHORIZED_APPROVER_CONFIGURED", "REAL_OPPORTUNITY_VALIDATED",
            "PRODUCTION_LOAD_VALIDATED", "OFFLINE_PIPELINE_VALIDATED", "LOCAL_MODEL_ROUTING_VALIDATED"}


# ---------------------------------------------------------------- acceptance rule + release check

def test_acceptance_rule_is_exactly_the_six_release_dimensions():
    from apex_one.lab.blockers import CATEGORIES, acceptance, load_blockers, required_dimensions

    assert set(required_dimensions()) == REQUIRED
    assert {"VISION_GATE", "DESIGN_MODEL_VALIDATION", "REMOTE_FREE_COMPUTE_VALIDATED"} <= set(acceptance()["not_required"])
    for b in load_blockers():           # an experimental improvement can never hold a release dimension open
        assert b["category"] in CATEGORIES
        if b["category"] == "EXPERIMENTAL":
            assert b["maturity_dimension"] not in REQUIRED or b.get("blocks_dimension") is False, b["blocker_id"]
    exp = {b["blocker_id"] for b in load_blockers() if b["category"] == "EXPERIMENTAL"}
    assert {"GEMINI-KEY-MISSING", "GDB-DATASET-PARTIAL", "LARGE-MODELS-RESOURCE-BLOCKED",
            "REMOTE-PROVIDERS-EGRESS-DENIED", "NO-ROBUST-VISION-JUDGE"} <= exp


def _mat(**overrides):
    from apex_one.lab.blockers import _dimensions

    m = {d: {"status": "YES"} for d in _dimensions()}
    m.update({k: {"status": v} for k, v in overrides.items()})
    return m


def test_release_check_ready_only_when_every_required_dimension_is_yes():
    from apex_one.lab.blockers import release_check

    assert release_check(_mat(VISION_GATE="NO", REMOTE_FREE_COMPUTE_VALIDATED="NO", DESIGN_MODEL_VALIDATION="PARTIAL")) \
        == ("READY", [])                                                     # experimental gaps never block
    verdict, lines = release_check(_mat(BRAND_ASSETS_VALIDATED="NO", AUTHORIZED_APPROVER_CONFIGURED="NO"))
    assert verdict == "BLOCKED" and len(lines) == 2
    assert lines[0].startswith("BRAND_ASSETS_VALIDATED: NO — next: apex-one brand import")
    assert all("GEMINI" not in x and "VISION" not in x for x in lines)


def test_release_check_cli_prints_only_actionable_release_blockers():
    from apex_one.apps.cli.main import app

    res = CliRunner().invoke(app, ["release", "check"])
    assert res.exit_code == 1 and res.stdout.splitlines()[0] == "BLOCKED"
    listed = {line[2:].split(":")[0] for line in res.stdout.splitlines()[1:] if line.startswith("* ")}
    assert listed and listed <= REQUIRED and "VISION_GATE" not in res.stdout and "Gemini" not in res.stdout


# ---------------------------------------------------------------- brand intake

@pytest.fixture
def brand_home(tmp_path, monkeypatch):
    from apex_one.release import assets as A

    home = tmp_path / "home"
    shutil.copytree(REPO_ROOT / "config", home / "config")
    shutil.copytree(REPO_ROOT / "apex_one" / "assets", home / "apex_one" / "assets")
    (home / "assets" / "apex").mkdir(parents=True)
    (home / "assets" / "apex" / "README.md").write_text("intake notes")
    monkeypatch.setenv("APEX_HOME", str(home))
    reset_settings_cache()
    A._CACHE.clear()
    return home


def _rehash(pkg: Path) -> None:
    man = yaml.safe_load((pkg / "manifest.yaml").read_text())
    from apex_one.release.assets import package_paths

    man["checksums"] = {r: hashlib.sha256(p.read_bytes()).hexdigest() for r, p in package_paths(man, pkg).items()
                        if p.is_file()}
    (pkg / "manifest.yaml").write_text(yaml.safe_dump(man, allow_unicode=True))


def test_intake_layout_installs_and_validates(brand_home, tmp_path):
    from apex_one.release import assets as A

    rep = A.import_brand(_brand_pkg(tmp_path / "pkg"))
    assert rep["installed"], rep["problems"]
    adir = brand_home / "assets" / "apex"
    assert (adir / "robot.svg").exists() and (adir / "fonts" / "licences" / "OFL-ReadexPro.txt").exists()
    assert (adir / "README.md").read_text() == "intake notes"            # the staged swap keeps the README
    A._CACHE.clear()
    assert A.brand_status()["status"] == "VALID"


@pytest.mark.parametrize("breakage, expect", [
    ("unlicensed", "unlicensed"), ("no_evidence", "licence evidence missing"), ("bad_font", "not a font"),
    ("unlisted", "unlisted file"), ("traversal", "outside the package"), ("symlink", "symbolic link"),
    ("no_rules", "usage_rules.md")])
def test_intake_rejections(brand_home, tmp_path, breakage, expect):
    from apex_one.release import assets as A

    pkg = _brand_pkg(tmp_path / "pkg")
    man = yaml.safe_load((pkg / "manifest.yaml").read_text())
    if breakage == "unlicensed":
        man["font_licences"]["Readex Pro"]["licence"] = "unknown"
    elif breakage == "no_evidence":
        (pkg / "fonts" / "licences" / "OFL-ReadexPro.txt").unlink()
    elif breakage == "bad_font":
        (pkg / "fonts" / "readex.woff2").write_bytes(b"<html>not a font</html>")
    elif breakage == "unlisted":
        (pkg / "logo" / "old-draft.svg").write_text("<svg/>")
    elif breakage == "traversal":
        (tmp_path / "outside.svg").write_text((pkg / "logo" / "logo.svg").read_text())
        man["files"] = {"logo": "../outside.svg"}
    elif breakage == "symlink":
        (pkg / "mascot" / "robot.svg").unlink()
        os.symlink(pkg / "logo" / "logo.svg", pkg / "mascot" / "robot.svg")
    elif breakage == "no_rules":
        (pkg / "usage_rules.md").unlink()
    (pkg / "manifest.yaml").write_text(yaml.safe_dump(man, allow_unicode=True))
    if breakage in ("unlicensed", "bad_font", "traversal"):
        _rehash(pkg)                                       # checksums right: the content itself must be rejected
    rep = A.import_brand(pkg)
    assert not rep["installed"] and any(expect in p for p in rep["problems"]), rep["problems"]
    assert not (brand_home / "assets" / "apex" / "logo.svg").exists()       # nothing installed


def test_failed_reimport_keeps_the_previous_valid_brand(brand_home, tmp_path):
    from apex_one.release import assets as A

    assert A.import_brand(_brand_pkg(tmp_path / "good"))["installed"]
    before = (brand_home / "assets" / "apex" / "brand_fingerprint.json").read_text()
    bad = _brand_pkg(tmp_path / "bad", placeholder_logo=True)
    assert not A.import_brand(bad)["installed"]
    assert (brand_home / "assets" / "apex" / "brand_fingerprint.json").read_text() == before


# ---------------------------------------------------------------- FINAL export + release verification

def _final_job(monkeypatch):
    from apex_one.core.auth import create_approver
    from apex_one.core.governor.runner import JobRunner
    from tests.test_auth import _candidate_job

    r = _candidate_job()
    monkeypatch.setattr(JobRunner, "run", lambda self: self.job)
    (r.ws.root / "final.pdf").write_bytes(b"%PDF-1.7 the approved guide")
    (r.ws.root / "final.html").write_text("<html>approved</html>")
    sha = hashlib.sha256((r.ws.root / "final.pdf").read_bytes()).hexdigest()
    tok = create_approver("Release Owner")
    return JobRunner.load(r.job.job_id), tok, sha


def test_final_export_and_release_verification(monkeypatch, tmp_path):
    from apex_one.apps.cli.main import app
    from apex_one.release import export_final

    r, tok, sha = _final_job(monkeypatch)
    with pytest.raises(RuntimeError, match="not FINAL"):
        export_final(r.ws.root, tmp_path / "x.zip")
    r.approve(tok, "ship", artifact_sha256=sha)
    out = export_final(r.ws.root, tmp_path / "rel.zip")
    assert out["final_pdf_sha256"] == sha and out["approved_by"] == "Release Owner"
    assert Path(out["checksum_file"]).read_text().startswith(out["zip_sha256"])
    res = CliRunner().invoke(app, ["release", "verify", r.job.job_id])
    assert res.exit_code == 0 and '"verified": true' in res.stdout
    (r.ws.root / "final.pdf").write_bytes(b"%PDF-1.7 swapped")
    res = CliRunner().invoke(app, ["release", "verify", r.job.job_id])
    assert res.exit_code == 1 and "changed after approval" in res.stdout
    with pytest.raises(RuntimeError, match="binding broken"):
        export_final(r.ws.root, tmp_path / "again.zip")


def test_audit_history_shows_the_bound_decision(monkeypatch):
    from apex_one.apps.cli.main import app

    r, tok, sha = _final_job(monkeypatch)
    r.approve(tok, "ship", artifact_sha256=sha)
    res = CliRunner().invoke(app, ["auth", "history", "--job", r.job.job_id, "--json"])
    rows = json.loads(res.stdout)
    assert res.exit_code == 0 and rows[-1]["decision"] == "APPROVED" and rows[-1]["final_pdf_sha256"] == sha


# ---------------------------------------------------------------- baseline

def test_the_system_matches_the_validated_baseline():
    """Routing, memory policy, acceptance rule and the release contracts are frozen at the recorded baseline. A real
    change re-records it on purpose: `apex-one release baseline --write --reason ... --tests N`."""
    from apex_one.release import baseline as B

    rec = B.recorded()
    assert rec and rec["id"] == B.BASELINE_ID and rec["test_count"] > 0
    assert B.drift() == [], B.drift()


def test_baseline_detects_a_routing_change(monkeypatch, tmp_path):
    from apex_one.release import baseline as B

    monkeypatch.setattr(B, "baseline_path", lambda: tmp_path / "b.json")
    B.write("abc1234", 1, "test")
    assert B.drift() == []
    real = B.routing_policy_hash
    monkeypatch.setattr(B, "routing_policy_hash", lambda policy=None: "0" * 64 if policy is None else real(policy))
    assert any(d.startswith("routing_policy_sha256") for d in B.drift())


def test_checksums_helper_produces_a_block_the_importer_accepts(brand_home, tmp_path):
    from apex_one.apps.cli.main import app
    from apex_one.release import assets as A

    pkg = _brand_pkg(tmp_path / "pkg")
    man = yaml.safe_load((pkg / "manifest.yaml").read_text())
    del man["checksums"]
    (pkg / "manifest.yaml").write_text(yaml.safe_dump(man, allow_unicode=True))
    block = CliRunner().invoke(app, ["brand", "checksums", str(pkg)]).stdout
    (pkg / "manifest.yaml").write_text((pkg / "manifest.yaml").read_text() + block)
    assert A.import_brand(pkg)["installed"]


def test_local_serve_refuses_what_the_scheduler_would_not_admit(monkeypatch):
    from types import SimpleNamespace

    from apex_one.apps.cli.main import app
    from apex_one.compute.local import resources as R
    from apex_one.compute.local import server as S

    started = []
    monkeypatch.setattr(R, "admit", lambda spec, stage, mode=None, **k: SimpleNamespace(
        decision="DEFER", reason="another model server is resident"))
    monkeypatch.setattr(S.LocalServer, "start", lambda self, **k: started.append(1) or "http://x")
    res = CliRunner().invoke(app, ["local", "serve", "qwen3-vl-4b-q4kxl"])
    assert res.exit_code == 1 and "DEFER" in res.stdout and not started
