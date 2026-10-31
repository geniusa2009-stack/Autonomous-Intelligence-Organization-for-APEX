"""Persistent provider-health cache: a blocked or keyless provider is re-probed periodically, never per task — and
never cached forever.

Per provider/host it stores: last_probe, status, failure_type, next_probe_after, latency_ms, auth_state and the
count of consecutive failures. An AVAILABLE result is re-checked after 30 min. A failure is re-checked after a
BOUNDED exponential interval: 30 min x 2^(failures-1), capped at 24 h — so an egress denial that is lifted by a
settings change is noticed within a day at worst, and a flapping provider is not hammered. `force=True` (an explicit
operator refresh) always probes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

OK_INTERVAL_S = 30 * 60
FAIL_BASE_S = 30 * 60
FAIL_MAX_S = 24 * 60 * 60


def _path() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "cache" / "provider_health.json"


def _read() -> dict[str, Any]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def all_entries() -> dict[str, Any]:
    return _read()


def next_interval(ok: bool, consecutive_failures: int) -> int:
    if ok:
        return OK_INTERVAL_S
    return int(min(FAIL_BASE_S * 2 ** max(0, consecutive_failures - 1), FAIL_MAX_S))


def get(key: str, now: float | None = None) -> dict[str, Any] | None:
    """The cached probe if it is still fresh (now < next_probe_after), else None (probe again)."""
    rec = _read().get(key)
    if not rec:
        return None
    now = time.time() if now is None else now
    return rec if now < rec.get("next_probe_after", 0) else None


def put(key: str, ok: bool, detail: str, *, status: str | None = None, failure_type: str | None = None,
        latency_ms: float | None = None, auth_state: str | None = None, now: float | None = None,
        **extra: Any) -> dict[str, Any]:
    data = _read()
    now = time.time() if now is None else now
    fails = 0 if ok else int((data.get(key) or {}).get("consecutive_failures", 0)) + 1
    rec = {"provider": key, "ok": ok, "detail": detail, "status": status or ("AVAILABLE" if ok else "UNAVAILABLE"),
           "failure_type": None if ok else (failure_type or "UNKNOWN"), "last_probe": now, "at": now,
           "latency_ms": latency_ms, "auth_state": auth_state, "consecutive_failures": fails,
           "next_probe_after": now + next_interval(ok, fails), **extra}
    data[key] = rec
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return rec
