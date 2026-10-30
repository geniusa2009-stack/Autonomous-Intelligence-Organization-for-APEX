"""Model-server health supervision and the failure taxonomy.

A local model server can crash, hang, run out of memory, return nothing or return garbage. None of these is a WRONG
ANSWER: each is an infrastructure ERROR with a specific kind, and a benchmark must record it as ERROR (never as a
score of 0). This module:

* classifies every failed call into exactly one `FailureKind`;
* probes health before each call, detects timeouts, restarts a dead or hung process (bounded restart budget,
  exponential backoff, warm-up request after every restart) and logs every incident as a JSON line;
* allows a retry ONLY for idempotent work: a chat completion at a fixed prompt is side-effect free, so the broker may
  repeat it once after a successful recovery. The supervisor never re-runs a pipeline stage or a job, so a recovery
  can never duplicate a side effect. Deterministic failures (EMPTY_OUTPUT, MALFORMED_OUTPUT) are not retried —
  at temperature 0 they would only repeat.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class FailureKind(StrEnum):
    """INFRASTRUCTURE failures. None of them is model-quality evidence; none may ever become a score of 0."""
    MODEL_SERVER_CRASH = "MODEL_SERVER_CRASH"     # process died during / before the call
    MODEL_TIMEOUT = "MODEL_TIMEOUT"               # no response within the call timeout (process alive: hung or slow)
    EMPTY_OUTPUT = "EMPTY_OUTPUT"                 # HTTP 200, well-formed, but no text
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"         # response body is not an OpenAI chat response (protocol garbage);
                                                  # a well-formed answer with wrong/invalid CONTENT is QUALITY, not this
    HEALTHCHECK_FAILED = "HEALTHCHECK_FAILED"     # /health not OK and the restart budget is spent
    OOM = "OOM"                                   # process killed for memory (SIGKILL / allocator failure in log)
    CONNECTION_REFUSED = "CONNECTION_REFUSED"     # nothing listening on the port (server not running)
    STREAM_INTERRUPTED = "STREAM_INTERRUPTED"     # connection closed mid-response while the process stayed alive
    RESOURCE_BLOCKED = "RESOURCE_BLOCKED"         # the resource scheduler refused to load the model (not enough RAM)
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class OutcomeClass(StrEnum):
    """Persisted separately and never collapsed: a wrong answer, a broken server and an unrun task are different."""
    MEASURED = "MEASURED"                         # the model answered and the checker scored it > 0
    QUALITY_ZERO = "QUALITY_ZERO"                 # the model answered and the answer scored 0 (wrong)
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR" # a FailureKind: no answer to judge
    NOT_MEASURED = "NOT_MEASURED"                 # unsupported, skipped, or never run


class ResultState(StrEnum):
    """Per-sample result states. Only PASSED / FAILED are measurements; the other three never become scores."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"   # the task needs a modality / output the model cannot produce
    SKIPPED = "SKIPPED"           # not run (data unreachable, budget) — support not determined
    ERROR = "ERROR"               # the call failed; carries a FailureKind


# ProviderError.kind (apex_one/compute/providers/base.py) -> failure kind when the process state is unknown
_BY_PROVIDER_KIND = {
    "timeout": FailureKind.MODEL_TIMEOUT,
    "empty_output": FailureKind.EMPTY_OUTPUT,
    "malformed_response": FailureKind.MALFORMED_OUTPUT,
    "disconnected": FailureKind.STREAM_INTERRUPTED,
    "connection_refused": FailureKind.CONNECTION_REFUSED,
    "http": FailureKind.UNKNOWN_FAILURE,
    "network": FailureKind.UNKNOWN_FAILURE,
}
# rate limits, auth, payment, config are routing decisions about a provider, not model-server failures
NOT_SERVER_FAILURES = {"rate_limited", "quota_exhausted", "auth", "payment_required", "config"}
OOM_MARKERS = ("out of memory", "failed to allocate", "bad_alloc", "cannot allocate memory", "oom-kill")
RESTART_ON = {FailureKind.MODEL_SERVER_CRASH, FailureKind.OOM, FailureKind.MODEL_TIMEOUT,
              FailureKind.HEALTHCHECK_FAILED, FailureKind.CONNECTION_REFUSED}
RETRY_AFTER_RECOVERY = {FailureKind.MODEL_SERVER_CRASH, FailureKind.OOM, FailureKind.MODEL_TIMEOUT,
                        FailureKind.STREAM_INTERRUPTED, FailureKind.CONNECTION_REFUSED}


def outcome_class(score: float | None, failure_kind: str | None) -> OutcomeClass:
    if score is None:
        return OutcomeClass.INFRASTRUCTURE_ERROR if failure_kind else OutcomeClass.NOT_MEASURED
    return OutcomeClass.QUALITY_ZERO if score == 0 else OutcomeClass.MEASURED


def failure_kind_for(provider_error_kind: str | None) -> FailureKind | None:
    """Failure kind from the error alone (no process information). None = not a model-server failure."""
    if provider_error_kind is None or provider_error_kind in NOT_SERVER_FAILURES:
        return None
    return _BY_PROVIDER_KIND.get(provider_error_kind, FailureKind.UNKNOWN_FAILURE)


def classify(provider_error_kind: str | None, *, alive: bool | None, exit_code: int | None = None,
             log_tail: str = "") -> FailureKind | None:
    """One failure kind per failed call. A dead process outranks the transport symptom it caused."""
    if provider_error_kind in NOT_SERVER_FAILURES:
        return None
    if alive is False:
        if exit_code == -9 or any(m in log_tail.lower() for m in OOM_MARKERS):
            return FailureKind.OOM
        return FailureKind.MODEL_SERVER_CRASH
    return failure_kind_for(provider_error_kind) or FailureKind.UNKNOWN_FAILURE


class SupervisedProcess(Protocol):
    """What the supervisor needs from a server (LocalServer, or the fault-injection fake)."""

    def start(self, wait_s: float = ...) -> str: ...
    def stop(self) -> None: ...
    def healthy(self, timeout: float = ...) -> bool: ...
    def alive(self) -> bool | None: ...
    def exit_code(self) -> int | None: ...
    def log_tail(self, chars: int = ...) -> str: ...
    def warm_up(self, timeout: float = ...) -> bool: ...


class SupervisorError(Exception):
    def __init__(self, kind: FailureKind, message: str):
        super().__init__(f"{kind.value}: {message}")
        self.kind = kind


@dataclass(frozen=True)
class SupervisorPolicy:
    max_restarts: int = 3
    backoff_s: tuple[float, ...] = (2.0, 8.0, 30.0)   # before restart 1, 2, 3 (last value repeats)
    health_timeout_s: float = 3.0
    start_wait_s: float = 1200.0
    warmup_timeout_s: float = 120.0


class ServerSupervisor:
    def __init__(self, name: str, server: SupervisedProcess, *, policy: SupervisorPolicy | None = None,
                 events_path: Path | None = None, sleep: Callable[[float], None] = time.sleep):
        self.name, self.server = name, server
        self.policy = policy or SupervisorPolicy()
        self.events_path = events_path
        self.sleep = sleep
        self.restarts = 0
        self.events: list[dict] = []

    # ---- incident log ----
    def _event(self, event: str, **kw) -> None:
        rec = {"at": datetime.now(UTC).isoformat(), "server": self.name, "event": event, **kw}
        self.events.append(rec)
        if self.events_path is not None:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- lifecycle ----
    def restart(self, reason: FailureKind) -> None:
        """Bounded restart with backoff and a warm-up request. Raises SupervisorError when the budget is spent or
        the restarted server does not become healthy and answer the warm-up."""
        while True:
            if self.restarts >= self.policy.max_restarts:
                self._event("restart_budget_exhausted", reason=reason.value, restarts=self.restarts)
                raise SupervisorError(reason, f"{self.name}: restart budget ({self.policy.max_restarts}) exhausted")
            delay = self.policy.backoff_s[min(self.restarts, len(self.policy.backoff_s) - 1)]
            self.restarts += 1
            self._event("restart", reason=reason.value, attempt=self.restarts, backoff_s=delay)
            self.sleep(delay)
            self.server.stop()
            try:
                self.server.start(wait_s=self.policy.start_wait_s)
                if self.server.warm_up(timeout=self.policy.warmup_timeout_s):
                    self._event("recovered", attempt=self.restarts)
                    return
                self._event("warmup_failed", attempt=self.restarts)
            except Exception as e:  # noqa: BLE001 — a failed start is one spent attempt, never a crash of the caller
                from apex_one.compute.local.resources import ResourceBlocked

                self._event("start_failed", attempt=self.restarts, error=str(e)[:300])
                if isinstance(e, ResourceBlocked):     # waiting does not create RAM: stop now, record why
                    raise SupervisorError(FailureKind.RESOURCE_BLOCKED, str(e)) from e

    def before_call(self) -> None:
        """Pre-call health probe; recover a dead or unhealthy server before sending the request."""
        if self.server.healthy(timeout=self.policy.health_timeout_s):
            return
        alive = self.server.alive()
        if alive is False:          # it died: crash or OOM
            kind = classify("connection_refused", alive=alive, exit_code=self.server.exit_code(),
                            log_tail=self.server.log_tail())
        elif alive is None:         # nothing we started is there: the port is closed
            kind = FailureKind.CONNECTION_REFUSED
        else:                       # running but not ready / not answering /health
            kind = FailureKind.HEALTHCHECK_FAILED
        self._event("unhealthy_before_call", kind=kind.value, alive=alive, exit_code=self.server.exit_code())
        self.restart(kind)

    def after_failure(self, provider_error_kind: str) -> tuple[FailureKind | None, bool]:
        """Classify a failed call and recover if needed. Returns (kind, safe_to_retry_same_request)."""
        alive = self.server.alive()
        t0 = time.monotonic()   # a dying process closes its sockets just before it is reaped: let it settle
        while alive and provider_error_kind in ("disconnected", "connection_refused") and time.monotonic() - t0 < 1.0:
            time.sleep(0.05)
            alive = self.server.alive()
        kind = classify(provider_error_kind, alive=alive, exit_code=self.server.exit_code(),
                        log_tail=self.server.log_tail())
        if kind is None:
            return None, False
        self._event("call_failed", kind=kind.value, provider_error=provider_error_kind, alive=alive,
                    exit_code=self.server.exit_code(), log_tail=self.server.log_tail(400)[-400:])
        recovered = True
        if kind in RESTART_ON:
            try:
                self.restart(kind)
            except SupervisorError:
                recovered = False
        elif kind == FailureKind.STREAM_INTERRUPTED:
            recovered = self.server.healthy(timeout=self.policy.health_timeout_s)
        return kind, recovered and kind in RETRY_AFTER_RECOVERY


# ---- process-wide registry: every ComputeBroker created in this process uses these supervisors ----
_ACTIVE: dict[str, ServerSupervisor] = {}


def register(model_id: str, supervisor: ServerSupervisor) -> None:
    _ACTIVE[model_id] = supervisor


def unregister(model_id: str) -> None:
    _ACTIVE.pop(model_id, None)


def active_supervisors() -> dict[str, ServerSupervisor]:
    return dict(_ACTIVE)


def supervise_running_local_servers(events_path: Path | None = None) -> dict[str, ServerSupervisor]:
    """Supervise every acquired local model whose server is ALREADY running (an operator started it). A model that
    is not running is left alone: supervision recovers a crash, it never starts a model nobody asked for."""
    import os

    if os.environ.get("APEX_DISABLE_LOCAL_MODELS") == "1" or os.environ.get("APEX_SUPERVISE_LOCAL") == "0":
        return {}
    from apex_one.compute.local.acquisition import load_catalogue
    from apex_one.compute.local.server import LocalServer

    try:
        _, specs = load_catalogue()
    except Exception:  # noqa: BLE001 — no catalogue, nothing to supervise
        return {}
    out = {}
    for spec in specs.values():
        if not (spec.dir / "apex_manifest.json").exists():
            continue
        srv = LocalServer(spec)
        if srv.healthy(timeout=0.5):
            out[spec.registry_model] = _ACTIVE.get(spec.registry_model) or ServerSupervisor(
                spec.key, srv, events_path=events_path)
    return out
