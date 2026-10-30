"""Persistent provider-health cache with TTL: a blocked or keyless provider is re-probed periodically, never per task.

Egress-denied hosts (proxy 403) and missing credentials do not change between tasks, so probing them on every job or
evaluation cycle only burns time. A probe result is reused until its TTL expires; an AVAILABLE result is re-checked
sooner than a blocked one. `force=True` (e.g. `apex-one providers status --refresh`) always probes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

TTL_S = {"ok": 30 * 60, "blocked": 6 * 60 * 60}


def _path() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "cache" / "provider_health.json"


def _read() -> dict[str, Any]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get(key: str, now: float | None = None) -> dict[str, Any] | None:
    rec = _read().get(key)
    if not rec:
        return None
    now = time.time() if now is None else now
    ttl = TTL_S["ok" if rec.get("ok") else "blocked"]
    return rec if now - rec.get("at", 0) < ttl else None


def put(key: str, ok: bool, detail: str, **extra: Any) -> None:
    data = _read()
    data[key] = {"ok": ok, "detail": detail, "at": time.time(), **extra}
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
