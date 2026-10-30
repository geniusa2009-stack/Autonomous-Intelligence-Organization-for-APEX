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
    assert classify("malformed_response", alive=True) == FailureKind.MALFORMED_RESPONSE
    assert classify("disconnected", alive=True) == FailureKind.CONNECTION_DROPPED
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
    assert e.value.kind == FailureKind.HEALTHCHECK_FAILED
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
