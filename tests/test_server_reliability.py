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


def test_scheduler_modes_and_decisions(tmp_path):
    """Gemma-3-12B-like numbers (measured peak 13.9 GB, 16.16 GB available idle, 16.9 GB total)."""
    from apex_one.compute.local.resources import EVALUATION_MODE, PRODUCTION_MODE, admit

    spec = _spec(tmp_path)
    q = {"done": {"m-q4:ram": {"info": {"peak_rss_gb": 13.9}}}}         # measured peak wins over any estimate
    kw = {"others": [], "capacity": 16.16, "total": 16.9}
    ev = admit(spec, "council", q, available=16.16, mode=EVALUATION_MODE, **kw)
    assert ev.decision == "ADMIT" and ev.estimate_source.startswith("measured") and ev.headroom_gb < 1.0
    # the same stage is NOT production-safe: < 2 GB / 12 % headroom on an idle machine -> RESOURCE_BLOCKED
    pr = admit(spec, "council", q, available=16.16, mode=PRODUCTION_MODE, **kw)
    assert pr.decision == "RESOURCE_BLOCKED" and pr.required_headroom_gb >= 2.0
    # model + Chromium: blocked even for evaluation (never launch Chromium and hope)
    pages = admit(spec, "pages", q, available=16.16, mode=EVALUATION_MODE, **kw)
    assert pages.decision == "RESOURCE_BLOCKED" and pages.profile == "MODEL_PLUS_CHROMIUM" and "renderer" in pages.reserves
    # memory still held by something else, but the stage fits an idle machine -> DEFER, not BLOCKED
    assert admit(spec, "council", q, available=15.0, mode=EVALUATION_MODE, **kw).decision == "DEFER"
    # render phase alone (model unloaded): no model peak in the need
    r = admit(spec, "pages:render", q, available=16.16, mode=PRODUCTION_MODE, **kw)
    assert r.decision == "ADMIT" and r.expected_peak_gb == 0.0


def test_scheduler_never_loads_two_large_models_or_after_a_leak(tmp_path):
    from apex_one.compute.local.resources import admit

    other = [{"pid": 1, "port": "8096", "rss_gb": 13.0}]
    d = admit(_spec(tmp_path, approx=2.0), "council", {}, available=64.0, others=other, capacity=64.0, total=64.0)
    assert d.decision == "DEFER" and "another model server is resident" in d.reason
    small = [{"pid": 1, "port": "8096", "rss_gb": 0.2}]                 # a stopped server's leftovers do not count
    assert admit(_spec(tmp_path, approx=2.0), "council", {}, available=64.0, others=small, capacity=64.0,
                 total=64.0).decision == "ADMIT"
    leak = admit(_spec(tmp_path, approx=2.0), "council", {}, available=64.0, others=[], capacity=64.0, total=64.0,
                 recovery_ok=False)
    assert leak.decision == "DEFER" and "MEMORY_LEAK_OR_RESIDUAL" in leak.reason


def test_unmeasured_models_use_a_conservative_or_same_family_multiplier(tmp_path, monkeypatch):
    from apex_one.compute.local import resources

    monkeypatch.setattr(resources, "load_estimates", lambda: {
        "gemma3-12b-q4km": {"family": "gemma", "ratio": 1.157},
        "qwen3-vl-8b-q4kxl": {"family": "qwen3-vl", "ratio": 1.02}})
    from types import SimpleNamespace

    q8 = SimpleNamespace(key="qwen3-vl-8b-q8kxl", registry_model="qwen3-vl-8b-q8", dir=tmp_path, approx_gb=12.0,
                         ctx=8192, port=1)
    unknown = SimpleNamespace(key="x", registry_model="newfam", dir=tmp_path, approx_gb=12.0, ctx=8192, port=1)
    assert resources.safety_multiplier(q8)[0] == 1.02                   # measured sibling of the same family
    assert resources.safety_multiplier(unknown)[0] == 1.25              # no sibling: conservative default
    peak, src = resources.expected_peak(unknown, {})
    assert peak > 12.0 * 1.25 and "x 1.25" in src


def test_finished_model_still_holding_memory_is_a_scheduler_bug(monkeypatch):
    from apex_one.compute.local import resources

    monkeypatch.setattr(resources, "llama_servers", lambda: [{"pid": 7, "port": "8096", "rss_gb": 12.6}])
    with pytest.raises(resources.SchedulerViolation):
        resources.assert_unloaded(8096)
    monkeypatch.setattr(resources, "llama_servers", lambda: [])
    resources.assert_unloaded(8096)


def test_measured_memory_lifecycle_of_own_fake_server(tmp_path, monkeypatch):
    """Load the fake server under the scheduler, then unload: our own process must exit, memory must recover, and the
    lifecycle (before / after load / after warm-up / peak / before unload / after exit / after stabilisation,
    recovery ratio, swap, faults, latency probe) is recorded."""
    import json as _json

    from apex_one.compute.local import resources
    from apex_one.lab.fake_model_server import FakeServerProcess

    monkeypatch.setattr(resources, "llama_servers", lambda: [])          # never inspect real servers
    monkeypatch.setattr(resources, "wait_stable", lambda *a, **k: resources.available_gb())
    monkeypatch.setattr(resources, "estimates_path", lambda: tmp_path / "estimates.json")
    monkeypatch.setattr(resources, "baseline_capacity_gb", lambda: resources.available_gb())
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
    assert dec.decision == "ADMIT"
    m = s.unload()
    assert fake.proc.poll() is not None                                   # process exit confirmed
    for k in ("available_before_load_gb", "available_after_load_gb", "available_after_warmup_gb", "peak_rss_gb",
              "available_before_unload_gb", "available_after_exit_gb", "available_after_unload_gb",
              "memory_recovery_ratio", "swap_total_gb", "swap_used_peak_gb", "load_time_s", "warmup_time_s",
              "unload_time_s", "latency_degradation_ratio"):
        assert k in m, k
    assert m["memory_recovery_ratio"] >= resources.RECOVERY_MIN_RATIO and "MEMORY_LEAK_OR_RESIDUAL" not in m["flags"]
    est = _json.loads((tmp_path / "estimates.json").read_text())[fake.spec.key]
    assert {"estimated_peak_gb", "measured_peak_gb", "prediction_error_gb", "ratio"} <= set(est)
    events = [_json.loads(x)["event"] for x in (tmp_path / "res.jsonl").read_text().splitlines()]
    assert events == ["admission", "unload"]


def test_memory_that_does_not_come_back_is_flagged(tmp_path, monkeypatch):
    from apex_one.compute.local import resources
    from apex_one.lab.fake_model_server import FakeServerProcess

    monkeypatch.setattr(resources, "llama_servers", lambda: [])
    monkeypatch.setattr(resources, "estimates_path", lambda: tmp_path / "estimates.json")
    monkeypatch.setattr(resources, "baseline_capacity_gb", lambda: resources.available_gb())
    monkeypatch.setattr(resources, "wait_stable", lambda *a, **k: resources.available_gb() * 0.5)  # half never returns
    fake = FakeServerProcess(_free_port(), "ok", tmp_path)
    fake.spec = _spec(tmp_path, port=fake.port, approx=0.01, ctx=8)
    fake.pidfile = tmp_path / "fake.pid"
    s = resources.ScheduledServer(fake, qstate={})
    s.load("council", wait_s=5)
    m = s.unload()
    assert "MEMORY_LEAK_OR_RESIDUAL" in m["flags"] and m["memory_recovery_ratio"] < 0.95
    ok, why = resources.last_recovery_ok({"done": {"k:ram": {"info": {"cycles": [{**m, "available_before_load_gb": 1e9}]}}}})
    assert not ok                                                         # the next large model must not load


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


def test_slot_following_is_remembered_and_rejected_automatically():
    from apex_one.persistence import init_db
    from apex_one.vision.judge_failures import known_failure, position_bias_severity, remember

    init_db()
    rec = {"correct": 0, "position_bias_rate": 1.0,
           "detail": {k: {"position_bias": True, "reasons": ["Page A ...", "Page A ..."]} for k in "abcde"}}
    assert position_bias_severity(1.0) == "severe" and position_bias_severity(0.2) is None
    assert remember("judge-x", rec, "sha256:1") == "severe"
    assert remember("judge-x", rec, "sha256:1") == "severe"              # stored once per build
    assert known_failure("judge-x", "sha256:1").startswith("FailureMemory: PAIRWISE_POSITION_BIAS severe")
    assert known_failure("judge-x", "sha256:2") is None                  # a new build must earn its own calibration
    from apex_one.memory import FailureMemory

    assert len(FailureMemory().by_key("vision_judge:judge-x")) == 1


def test_provider_retry_interval_is_bounded_exponential(monkeypatch):
    from apex_one.compute import health_cache as hc

    t = 1_000_000.0
    r1 = hc.put("provider:x", False, "403", failure_type="EGRESS_DENIED", now=t)
    r2 = hc.put("provider:x", False, "403", failure_type="EGRESS_DENIED", now=t)
    assert r2["next_probe_after"] - t == 2 * (r1["next_probe_after"] - t)          # exponential
    for _ in range(20):
        r = hc.put("provider:x", False, "403", now=t)
    assert r["next_probe_after"] - t == hc.FAIL_MAX_S                            # bounded: never permanent
    assert hc.get("provider:x", now=t + 10) is not None and hc.get("provider:x", now=t + hc.FAIL_MAX_S + 1) is None
    ok = hc.put("provider:x", True, "200", now=t)
    assert ok["consecutive_failures"] == 0 and ok["next_probe_after"] - t == hc.OK_INTERVAL_S
    for k in ("provider", "last_probe", "status", "failure_type", "next_probe_after", "latency_ms", "auth_state"):
        assert k in r
