"""Fault-injection drill: every way a model server can fail must reach the benchmark as ERROR with its own
FailureKind — never as a score of 0 — and recoverable faults must recover through the supervisor.

Each mode starts the fake server (apex_one/lab/fake_model_server.py) behind a real ComputeBroker route and runs the
real council path (`run_council`, one structured task) through the ServerSupervisor.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

# mode -> (expected sample state, expected failure kind, expected restarts > 0)
EXPECTED: dict[str, tuple[str, str | None, bool]] = {
    "ok": ("MEASURED", None, False),
    "empty": ("ERROR", "EMPTY_OUTPUT", False),
    "hang": ("ERROR", "MODEL_TIMEOUT", True),
    "crash": ("ERROR", "MODEL_SERVER_CRASH", True),
    "oom": ("ERROR", "OOM", True),
    "malformed": ("ERROR", "MALFORMED_OUTPUT", False),
    "disconnect": ("ERROR", "STREAM_INTERRUPTED", False),
    "unhealthy": ("ERROR", "HEALTHCHECK_FAILED", True),
    "refused": ("ERROR", "CONNECTION_REFUSED", True),
    "resource_blocked": ("ERROR", "RESOURCE_BLOCKED", True),
    "crash_once": ("MEASURED", None, True),
    "hang_once": ("MEASURED", None, True),
    "oom_once": ("MEASURED", None, True),
    "disconnect_once": ("MEASURED", None, False),
}
DRILL_MODEL = "qwen-vl-current"     # any registry model; the drill gives it a route to the fake server
DRILL_TASK = "structured_json"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_mode(mode: str, workdir: Path, call_timeout: float = 2.0) -> dict[str, Any]:
    from apex_one.compute.benchmark.council import run_council
    from apex_one.compute.broker import ComputeBroker
    from apex_one.compute.local.supervisor import ServerSupervisor, SupervisorPolicy
    from apex_one.compute.registry import load_registry
    from apex_one.core.schemas.compute import Availability, Pricing, ProviderRoute
    from apex_one.lab.fake_model_server import FakeServerProcess

    mdir = workdir / mode
    mdir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    fake = FakeServerProcess(port, mode, mdir)
    try:
        fake.start(wait_s=3.0)
    except Exception:  # noqa: BLE001 — unhealthy / refused / resource_blocked: the call must classify it
        pass
    reg = load_registry(with_db_overlay=False)
    reg.models[DRILL_MODEL].routes = [ProviderRoute(
        provider="llamacpp_local", provider_model_id="fake", model_id_verified=True, base_url=fake.base_url,
        pricing=Pricing(free_tier=True, input_per_mtok_usd=0.0, output_per_mtok_usd=0.0, per_request_usd=0.0,
                        verified=True, note="fault-injection fake server"))]
    sup = ServerSupervisor(f"fake:{mode}", fake, events_path=mdir / "events.jsonl", sleep=lambda s: None,
                           policy=SupervisorPolicy(max_restarts=2, backoff_s=(0.0,), health_timeout_s=1.0,
                                                   start_wait_s=3.0, warmup_timeout_s=call_timeout))
    broker = ComputeBroker(reg, supervisors={DRILL_MODEL: sup})
    broker.health.set_probe("llamacpp_local", Availability.AVAILABLE, "drill")
    try:
        run_council(broker, [DRILL_MODEL], mdir, only=[DRILL_TASK], timeout=call_timeout)
    finally:
        fake.stop()
    row = [json.loads(x) for x in (mdir / "council_runs.jsonl").read_text().splitlines() if x.strip()][-1]
    scores = json.loads((mdir / "council_scores.json").read_text())["models"].get(DRILL_MODEL, {})
    state = row["state"] if row["state"] == "ERROR" else "MEASURED"
    exp_state, exp_kind, exp_restart = EXPECTED[mode]
    restarts = sum(1 for e in sup.events if e["event"] == "restart")
    ok = (row.get("outcome_class") == ("INFRASTRUCTURE_ERROR" if exp_state == "ERROR" else row.get("outcome_class"))
          and state == exp_state and row["failure_kind"] == exp_kind and (restarts > 0) == exp_restart
          and (DRILL_TASK in scores) == (exp_state == "MEASURED"))   # an ERROR never lands in the score table
    return {"mode": mode, "state": row["state"], "outcome_class": row.get("outcome_class"),
            "failure_kind": row["failure_kind"], "score": row["score"],
            "in_score_table": DRILL_TASK in scores, "restarts": restarts, "server_starts": fake.starts,
            "events": [e["event"] + (f":{e['kind']}" if "kind" in e else "") for e in sup.events],
            "expected": {"state": exp_state, "failure_kind": exp_kind, "restart": exp_restart}, "pass": ok}


def run_drill(out_dir: Path, modes: list[str] | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_mode(m, out_dir / "work") for m in (modes or list(EXPECTED))]
    rep = {"drill": "fake model server fault injection", "rows": rows, "all_pass": all(r["pass"] for r in rows)}
    (out_dir / "fault_drill.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return rep
