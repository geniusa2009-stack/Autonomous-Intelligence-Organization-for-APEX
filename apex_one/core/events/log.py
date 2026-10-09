"""Append-only JSONL event log per job (observability + replay)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from apex_one.core.schemas.common import utcnow
from apex_one.core.security import redact

_LOCK = threading.Lock()


class EventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, /, **data: Any) -> dict[str, Any]:
        record = {"at": utcnow().isoformat(), "event": event, **redact(data)}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _LOCK, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return record

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
