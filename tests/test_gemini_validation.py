"""The Gemini validation path runs end to end without code changes once a key exists — verified here offline."""

import json

import pytest
from typer.testing import CliRunner


@pytest.fixture
def gv(monkeypatch, tmp_path):
    from apex_one.vision import gemini_validation as G

    monkeypatch.setattr(G, "out_dir", lambda: tmp_path / "gv")
    return G


def _runners(calls, canonical_ok=True, fail_live=False):
    def list_models():
        if fail_live:
            from apex_one.compute.providers.base import ProviderError

            raise ProviderError("network", "proxy CONNECT 403")
        return [{"name": "models/gemini-2.5-flash", "version": "001", "displayName": "Gemini 2.5 Flash",
                 "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-flash-latest", "version": "latest"},
                {"name": "models/gemini-2.5-flash-lite", "version": "001"}]
    return {"list_models": list_models,
            "pin": lambda *a, **k: calls.append(("pin", a[2], a[3])),
            "absolute": lambda c: calls.append("absolute") or {"correct": 1, "reliable": False},
            "pairwise": lambda c: calls.append("pairwise") or {"correct": 4, "position_bias_rate": 0.0},
            "width": lambda c, w: calls.append(f"width:{w}"),
            "reports": lambda: calls.append("reports")}


def test_no_key_is_a_clean_human_block(gv, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code, rep = gv.validate_gemini(runners=_runners([]))
    assert code == gv.EXIT_BLOCKED and rep["status"] == "BLOCKED_NO_KEY"
    assert json.loads((gv.out_dir() / "report.json").read_text())["status"] == "BLOCKED_NO_KEY"


def test_key_without_billing_attestation_is_blocked(gv, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    code, rep = gv.validate_gemini(runners=_runners([]))
    assert code == gv.EXIT_BLOCKED and rep["status"] == "BLOCKED_NO_ATTESTATION" and "providers attest" in rep["next"]


def _attested(monkeypatch):
    from apex_one.compute.registry.loader import ArsenalRegistry

    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(ArsenalRegistry, "has_attestation", lambda self, p, k, now=None: True)


def test_full_sequence_and_no_width_sweep_when_canonical_fails(gv, monkeypatch):
    from apex_one.lab.benchmarks import vision_robustness as VR

    _attested(monkeypatch)
    monkeypatch.setattr(VR, "load", lambda mid, out_dir=None: {"widths": {}})
    monkeypatch.setattr(VR, "status", lambda d: ("UNQUALIFIED", "canonical 640 px: correct per repeat [2, 2, 2]"))
    calls = []
    code, rep = gv.validate_gemini(runners=_runners(calls))
    assert code == gv.EXIT_DONE and rep["status"] == "COMPLETED" and rep["verdict"] == "UNQUALIFIED"
    assert rep["model"]["model"] == "gemini-2.5-flash" and rep["model"]["version"] == "001"     # exact model pinned
    assert calls == [("pin", "gemini-2.5-flash", "001"), "absolute", "pairwise", "width:640", "reports"]
    assert rep["steps"]["widths"]["state"] == "SKIPPED"


def test_width_sweep_runs_only_after_canonical_qualifies_and_resumes(gv, monkeypatch):
    from apex_one.lab.benchmarks import vision_robustness as VR

    _attested(monkeypatch)
    monkeypatch.setattr(VR, "load", lambda mid, out_dir=None: {"widths": {}})
    monkeypatch.setattr(VR, "status", lambda d: ("CANONICAL_640_ONLY", "640 passes"))
    calls = []
    gv.validate_gemini(runners=_runners(calls))
    widths = [c for c in calls if str(c).startswith("width:")]
    assert widths == ["width:640"] + [f"width:{w}" for w in VR.WIDTHS if w != "640"]       # canonical first
    again = []
    gv.validate_gemini(runners=_runners(again))                       # resumes: nothing re-run but the reports
    assert again == ["reports"]


def test_infrastructure_error_is_never_a_score(gv, monkeypatch):
    _attested(monkeypatch)
    code, rep = gv.validate_gemini(runners=_runners([], fail_live=True))
    assert code == gv.EXIT_ERROR and rep["status"] == "ERROR" and "verdict" not in rep
    assert rep["steps"]["live"]["state"] == "ERROR" and rep["steps"]["live"]["failure_kind"] == "UNKNOWN_FAILURE"


def test_model_choice_is_deterministic_and_never_an_alias(gv):
    models = [{"name": "models/gemini-flash-latest"}, {"name": "models/gemini-2.0-flash"},
              {"name": "models/gemini-2.5-flash"}, {"name": "models/gemini-2.5-flash-preview-05"},
              {"name": "models/gemini-2.5-pro"}, {"name": "models/gemini-2.5-flash-lite"}]
    assert gv.choose_model(models)[0]["name"] == "models/gemini-2.5-flash"
    assert gv.choose_model(models, "gemini-2.0-flash")[0]["name"] == "models/gemini-2.0-flash"
    assert gv.choose_model([{"name": "models/gemini-flash-latest"}])[0] is None


def test_cli_reports_blocked_without_key(monkeypatch, gv):
    from apex_one.apps.cli.main import app

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res = CliRunner().invoke(app, ["vision", "validate-gemini"])
    assert res.exit_code == 2 and "BLOCKED_NO_KEY" in res.stdout


def test_pinned_remote_model_changes_its_calibration_identity(monkeypatch, tmp_path):
    from apex_one.compute.registry import load_registry
    from apex_one.compute.registry import loader as L
    from apex_one.vision.council import model_digest

    monkeypatch.setattr(L, "pins_path", lambda: tmp_path / "pins.json")
    L.write_pin("gemini-flash-free", "gemini", "gemini-2.5-flash", "001")
    route = next(r for r in load_registry().models["gemini-flash-free"].routes if r.provider == "gemini")
    assert route.provider_model_id == "gemini-2.5-flash"
    assert model_digest("gemini-flash-free") == "remote:gemini/gemini-2.5-flash@001"
    L.write_pin("gemini-flash-free", "gemini", "gemini-3-flash", "001")
    assert model_digest("gemini-flash-free") != "remote:gemini/gemini-2.5-flash@001"   # old calibration no longer applies
