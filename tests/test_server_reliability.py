"""Model-server supervision: every failure is classified ERROR with its own kind — never a score of 0."""

from __future__ import annotations

import pytest

from apex_one.compute.local.supervisor import (
    FailureKind,
    ServerSupervisor,
    SupervisorError,
    SupervisorPolicy,
    classify,
    failure_kind_for,
)


def test_classification_dead_process_outranks_transport_symptom():
    assert classify("disconnected", alive=False, exit_code=-9) == FailureKind.OOM
    assert classify("disconnected", alive=False, exit_code=1, log_tail="... failed to allocate buffer") == FailureKind.OOM
    assert classify("disconnected", alive=False, exit_code=1) == FailureKind.MODEL_SERVER_CRASH
    assert classify("timeout", alive=True) == FailureKind.MODEL_TIMEOUT
    assert classify("empty_output", alive=True) == FailureKind.EMPTY_OUTPUT
    assert classify("malformed_response", alive=True) == FailureKind.MALFORMED_OUTPUT
    assert classify("disconnected", alive=True) == FailureKind.STREAM_INTERRUPTED
    assert classify("http", alive=True) == FailureKind.UNKNOWN_FAILURE


def test_routing_errors_are_not_server_failures():
    for kind in ("rate_limited", "quota_exhausted", "auth", "payment_required", "config"):
        assert failure_kind_for(kind) is None
        assert classify(kind, alive=False) is None


class _Dead:
    """A server that never comes back."""
    def __init__(self):
        self.starts = 0

    def start(self, wait_s=0):
        self.starts += 1
        raise RuntimeError("exited (-4)")

    def stop(self): pass
    def healthy(self, timeout=0): return False
    def alive(self): return False
    def exit_code(self): return -4
    def log_tail(self, chars=0): return ""
    def warm_up(self, timeout=0): return False


def test_restart_budget_is_bounded_with_backoff_and_logged(tmp_path):
    waits = []
    srv = _Dead()
    sup = ServerSupervisor("dead", srv, policy=SupervisorPolicy(max_restarts=3, backoff_s=(1, 2, 4)),
                           events_path=tmp_path / "ev.jsonl", sleep=waits.append)
    with pytest.raises(SupervisorError) as e:
        sup.before_call()
    assert e.value.kind == FailureKind.MODEL_SERVER_CRASH     # the original reason survives the spent budget
    assert srv.starts == 3 and waits == [1, 2, 4]
    events = [x["event"] for x in sup.events]
    assert events[0] == "unhealthy_before_call" and events[-1] == "restart_budget_exhausted"
    assert (tmp_path / "ev.jsonl").read_text().count("\n") == len(events)


def test_fault_injection_drill_classifies_every_fault_without_false_zeros(tmp_path):
    """Fake server: empty, hang, crash, OOM, malformed JSON, mid-response disconnect, unhealthy, and one-shot faults
    that must RECOVER through restart + safe retry. Runs the real broker + council path."""
    from apex_one.lab.benchmarks.server_fault_drill import EXPECTED, run_drill

    rep = run_drill(tmp_path)
    bad = [r for r in rep["rows"] if not r["pass"]]
    assert not bad, bad
    by = {r["mode"]: r for r in rep["rows"]}
    for mode, (state, kind, _) in EXPECTED.items():
        if state == "ERROR":
            assert by[mode]["score"] is None and not by[mode]["in_score_table"], mode   # never a 0
            assert by[mode]["failure_kind"] == kind
    assert by["crash_once"]["server_starts"] == 2      # one restart, then the same request succeeded


def test_gdb_provider_failure_carries_kind():
    from types import SimpleNamespace

    from apex_one.lab.benchmarks.gdb_provider import APEXBrokerModel

    rec = SimpleNamespace(outcome="error:timeout", failure_kind="MODEL_TIMEOUT")
    res = SimpleNamespace(executed=False, text=None, calls=[rec],
                          decision=SimpleNamespace(outcome=SimpleNamespace(value="DEGRADE"), reasons=["x"]))
    m = APEXBrokerModel.__new__(APEXBrokerModel)
    m.model_id, m.max_tokens, m.timeout = "x", 10, 1
    m.broker = SimpleNamespace(complete=lambda *a, **k: res)
    with pytest.raises(RuntimeError, match="ERROR MODEL_TIMEOUT"):
        m.predict(SimpleNamespace(images=[], text="hi"))


# ---------------------------------------------------------------- resource scheduler
# These tests never look at (or touch) real model-server processes: the process table is always mocked.

def _spec(tmp_path, key="m-q4", port=8199, approx=8.0, ctx=8192):
    from types import SimpleNamespace

    d = tmp_path / key
    d.mkdir(exist_ok=True)
    return SimpleNamespace(key=key, port=port, approx_gb=approx, ctx=ctx, dir=d, vision=True)


def test_scheduler_refuses_a_model_that_would_not_fit(tmp_path):
    from apex_one.compute.local.resources import admit

    spec = _spec(tmp_path)
    q = {"done": {"m-q4:ram": {"info": {"peak_rss_gb": 13.9}}}}         # measured peak wins over any estimate
    ok = admit(spec, "council", q, available=15.6, others=[])
    assert ok.admitted and ok.estimate_source.startswith("measured")
    # the same model in a stage that starts Chromium no longer fits: RESOURCE_BLOCKED, not an OOM
    blocked = admit(spec, "pages", q, available=15.6, others=[])
    assert not blocked.admitted and "renderer" in blocked.reserves and "available" in blocked.reason
    assert not admit(spec, "council", q, available=14.0, others=[]).admitted


def test_scheduler_never_loads_two_large_models(tmp_path):
    from apex_one.compute.local.resources import admit

    other = [{"pid": 1, "port": "8096", "rss_gb": 13.0}]
    d = admit(_spec(tmp_path), "council", {}, available=64.0, others=other)
    assert not d.admitted and "another model server is resident" in d.reason
    small = [{"pid": 1, "port": "8096", "rss_gb": 0.2}]                 # a stopped server's leftovers do not count
    assert admit(_spec(tmp_path, approx=2.0), "council", {}, available=64.0, others=small).admitted


def test_finished_model_still_holding_memory_is_a_scheduler_bug(monkeypatch):
    from apex_one.compute.local import resources

    monkeypatch.setattr(resources, "llama_servers", lambda: [{"pid": 7, "port": "8096", "rss_gb": 12.6}])
    with pytest.raises(resources.SchedulerViolation):
        resources.assert_unloaded(8096)
    monkeypatch.setattr(resources, "llama_servers", lambda: [])
    resources.assert_unloaded(8096)


def test_scheduled_load_and_unload_of_own_fake_server(tmp_path, monkeypatch):
    """Load the fake server under the scheduler, then unload: our process must exit and the cycle is recorded."""
    import json as _json

    from apex_one.compute.local import resources
    from apex_one.lab.fake_model_server import FakeServerProcess

    monkeypatch.setattr(resources, "llama_servers", lambda: [])          # never inspect real servers
    monkeypatch.setattr(resources, "wait_stable", lambda *a, **k: resources.available_gb())
    fake = FakeServerProcess(_free_port(), "ok", tmp_path)
    fake.spec = _spec(tmp_path, port=fake.port, approx=0.01, ctx=8)
    fake.pidfile = tmp_path / "fake.pid"
    orig_start = fake.start

    def start(wait_s=10.0):
        url = orig_start(wait_s)
        fake.pidfile.write_text(str(fake.proc.pid))
        return url
    fake.start = start
    s = resources.ScheduledServer(fake, qstate={}, log_path=tmp_path / "res.jsonl")
    dec = s.load("council", wait_s=5)
    assert dec.admitted and s.metrics["load_time_s"] >= 0 and "rss_before_load_gb" in s.metrics
    m = s.unload()
    assert fake.proc.poll() is not None                                   # process exit confirmed
    for k in ("rss_after_unload_gb", "unload_time_s", "swap_used_gb"):
        assert k in m
    events = [_json.loads(x)["event"] for x in (tmp_path / "res.jsonl").read_text().splitlines()]
    assert events == ["admission", "unload"]


def _free_port():
    import socket

    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


# ---------------------------------------------------------------- outcome classes / position bias / health cache

def test_quality_zero_infrastructure_error_and_not_measured_never_collapse():
    from apex_one.compute.local.supervisor import OutcomeClass, outcome_class

    assert outcome_class(0.0, None) == OutcomeClass.QUALITY_ZERO              # wrong answer
    assert outcome_class(None, "MODEL_SERVER_CRASH") == OutcomeClass.INFRASTRUCTURE_ERROR
    assert outcome_class(None, "RESOURCE_BLOCKED") == OutcomeClass.INFRASTRUCTURE_ERROR
    assert outcome_class(None, None) == OutcomeClass.NOT_MEASURED              # unsupported / skipped
    assert outcome_class(100.0, None) == OutcomeClass.MEASURED


def test_pairwise_position_bias_is_a_required_judge_criterion(tmp_path):
    """Gemma-3-12B-like judge: always picks the same SLOT -> 0/5, bias 1.0 -> fails A, B and D."""
    from apex_one.lab.benchmarks.vision_robustness import qualification, summarize_width
    from apex_one.vision.pairwise import PairwiseResult, calibrate_pairwise

    class SlotFollower:
        models = ["j"]

        def compare(self, first, second, intent):
            # always answers "A": with the good page as A the first argument wins, as B the second wins
            return PairwiseResult(winner=None, raw={"j": [("first", "A"), ("second", "A")]})

    cases = {k: tmp_path / f"{k}.png" for k in ("a", "b", "c", "d", "e")}
    out = calibrate_pairwise(SlotFollower(), tmp_path / "g.png", cases, "x")["models"]["j"]
    assert out["position_bias_rate"] == 1.0 and out["correct"] == 0 and not out["reliable"]
    s = summarize_width({"width": 640, "inputs": "test", "reps": [out, out, out], "legibility": {"legible": True}})
    q = qualification(s)
    assert not q["A_defect_discrimination"]["pass"] and not q["B_pair_order_stability"]["pass"]
    assert q["C_factual_legibility"]["pass"]


def test_blocked_provider_is_not_reprobed_every_task(monkeypatch):
    import httpx

    from apex_one.compute import live

    calls = []

    def deny(*a, **k):
        calls.append(1)
        raise httpx.ProxyError("403 Forbidden")
    monkeypatch.setattr(live.httpx, "get", deny)
    assert not live.network_check("https://integrate.api.nvidia.com/v1")[0]
    ok, why = live.network_check("https://integrate.api.nvidia.com/v1")
    assert not ok and why.endswith("(cached)") and len(calls) == 1
    live.network_check("https://integrate.api.nvidia.com/v1", force=True)
    assert len(calls) == 2
