from fastapi.testclient import TestClient
from typer.testing import CliRunner

from apex_one.apps.api.main import app
from apex_one.apps.cli.main import app as cli


def test_api_health_ready_providers_models():
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/ready").json()["ready"] is True
    provs = c.get("/providers").json()
    assert any(p["id"] == "groq" and p["availability"] == "CONFIGURATION_REQUIRED" for p in provs)
    assert not any("key" in k.lower() and "env" not in k.lower() for p in provs for k in p)
    models = c.get("/models", params={"category": "design"}).json()
    assert any(m["id"] == "PosterReward" for m in models)
    assert all(not m["production_allowed"] for m in models if not m["id"].startswith("apex-native"))


def test_api_job_lifecycle_without_running():
    c = TestClient(app)
    r = c.post("/jobs", json={"opportunity": "Example Labor College Fall 2027", "quality": "draft",
                              "offline_fixture": "synthetic_berea_style", "run": False})
    assert r.status_code == 201
    jid = r.json()["job_id"]
    assert c.get(f"/jobs/{jid}").json()["state"] == "NEW"
    assert "job.json" in c.get(f"/jobs/{jid}/artifacts").json()["artifacts"]
    assert c.get(f"/jobs/{jid}/artifacts/../../etc/passwd").status_code == 404
    assert c.post(f"/jobs/{jid}/approve", json={"approver": "x"}).status_code == 409
    assert c.post("/jobs", json={"opportunity": "x", "budget": 5}).status_code == 422
    assert "APEX ONE" in c.get("/studio").text


def test_cli_models_providers_doctor():
    runner = CliRunner()
    r = runner.invoke(cli, ["models", "--json"])
    assert r.exit_code == 0 and "OmniDocLayout-LLM" in r.stdout
    r = runner.invoke(cli, ["providers", "--json"])
    assert r.exit_code == 0 and "nvidia_nim" in r.stdout
    r = runner.invoke(cli, ["doctor"])
    assert r.exit_code == 0 and "Cost policy" in r.stdout
    r = runner.invoke(cli, ["create-guide", "--opportunity", "X Fall 2027", "--budget", "3"])
    assert r.exit_code == 2


def test_cli_attest_and_license_verify():
    runner = CliRunner()
    r = runner.invoke(cli, ["providers", "attest", "groq", "--by", "Tester"])
    assert r.exit_code == 0, r.stdout
    from apex_one.compute.registry import load_registry

    reg = load_registry()
    assert reg.has_attestation("groq", "free_tier_no_billing")
    r = runner.invoke(cli, ["license", "verify", "lic-gpt-oss", "--license", "Apache-2.0", "--state",
                            "PRODUCTION_ALLOWED", "--source", "https://example.org/license", "--by", "Tester"])
    assert r.exit_code == 0, r.stdout
    reg = load_registry()
    assert reg.production_allowed("gpt-oss-20b")
