"""Job workspace: the traceable artifact directory of a job."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic_core import to_jsonable_python

from apex_one.core.events.log import EventLog
from apex_one.core.security import redact
from apex_one.settings import get_settings


class JobWorkspace:
    def __init__(self, job_id: str, root: Path | None = None):
        self.job_id = job_id
        self.root = (root or get_settings().jobs_dir) / job_id
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("design_candidates", "screenshots", "qa", "sources", "pages"):
            (self.root / sub).mkdir(exist_ok=True)
        self.events = EventLog(self.root / "events.jsonl")
        self.model_calls = EventLog(self.root / "model_calls.jsonl")
        self.routing = EventLog(self.root / "routing_decisions.jsonl")
        self.checks = EventLog(self.root / "checks.jsonl")

    def path(self, rel: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, rel: str, payload: Any) -> Path:
        payload = to_jsonable_python(payload, fallback=str)
        p = self.path(rel)
        p.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return p

    def read_json(self, rel: str) -> Any:
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def exists(self, rel: str) -> bool:
        return (self.root / rel).exists()

    def write_text(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.write_text(text, encoding="utf-8")
        return p

    def check(self, state: str, name: str, passed: bool, detail: str = "") -> None:
        self.checks.emit("check", state=state, check=name, passed=passed, detail=detail)

    def list_artifacts(self) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
