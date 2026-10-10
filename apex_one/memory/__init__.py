"""ONE Memory — eight separate memory systems, each with its own table and semantics.

Not "one vector DB called memory": semantic facts, episodes, evidence, design, voice, failures,
approvals and preferences are stored, queried and governed differently.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from apex_one.persistence.db import session_scope
from apex_one.persistence.models import (
    ApprovalMemoryRow,
    DesignMemoryRow,
    EpisodicMemoryRow,
    EvidenceMemoryRow,
    FailureMemoryRow,
    SemanticMemoryRow,
    VoiceMemoryRow,
)


def _tok(s: str) -> set[str]:
    return set(re.findall(r"[\w؀-ۿ]+", s.lower()))


class _Store:
    row = SemanticMemoryRow

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url

    def add(self, key: str, text: str = "", payload: dict[str, Any] | None = None, job_id: str | None = None,
            **cols: Any) -> None:
        with session_scope(self.db_url) as s:
            s.add(self.row(key=key, text=text, payload=payload or {}, job_id=job_id, **cols))

    def all(self, limit: int = 500) -> list[Any]:
        with session_scope(self.db_url) as s:
            return list(s.execute(select(self.row).order_by(self.row.id.desc()).limit(limit)).scalars())

    def by_key(self, key: str) -> list[Any]:
        with session_scope(self.db_url) as s:
            return list(s.execute(select(self.row).where(self.row.key == key)).scalars())

    def search(self, query: str, k: int = 5) -> list[Any]:
        q = _tok(query)
        rows = self.all()
        scored = sorted(((len(q & _tok(r.text + " " + r.key)) / (len(q) or 1), r) for r in rows), key=lambda x: -x[0])
        return [r for sc, r in scored if sc > 0][:k]


class SemanticMemory(_Store):
    """Durable knowledge about institutions/programmes across jobs (only LOCKED facts, with cycle)."""
    row = SemanticMemoryRow


class EpisodicMemory(_Store):
    """What happened in each job: states, loops, outcomes."""
    row = EpisodicMemoryRow


class EvidenceMemory(_Store):
    """Source fingerprints (url, content hash, fetched_at) to detect page changes across cycles."""
    row = EvidenceMemoryRow


class DesignMemory(_Store):
    """Approved/rejected page structures and genes (feeds novelty + preference learning)."""
    row = DesignMemoryRow

    def signature_verdicts(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in reversed(self.all(2000)):
            out[r.key] = r.verdict
        return out


    def layout_references(self, limit: int = 400) -> dict[str, dict]:
        """Approved layouts + layouts of previous guides, for the anti-copy engine (geometry, not pixels)."""
        refs = {}
        for r in self.all(limit):
            occ = (r.payload or {}).get("occupancy")
            if occ and r.verdict in ("approved", "neutral"):
                refs[f"memory:{r.job_id}:{r.key}"] = {"grid": occ, "signature": r.key}
        return refs


class VoiceMemory(_Store):
    """Approved/rejected phrasing from human edits."""
    row = VoiceMemoryRow

    def rejected_phrases(self) -> list[str]:
        return [r.text for r in self.all(2000) if r.verdict == "rejected" and r.text]


class FailureMemory(_Store):
    """Failure kinds and the fixes that resolved them."""
    row = FailureMemoryRow

    def frequent(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.all(5000):
            out[r.failure_kind] = out.get(r.failure_kind, 0) + 1
        return out


class ApprovalMemory(_Store):
    """Human release decisions."""
    row = ApprovalMemoryRow


from apex_one.memory.preference import APEXPreferencePair, PreferenceMemory, PreferenceScorer  # noqa: E402

__all__ = ["ApprovalMemory", "APEXPreferencePair", "DesignMemory", "EpisodicMemory", "EvidenceMemory",
           "FailureMemory", "PreferenceMemory", "PreferenceScorer", "SemanticMemory", "VoiceMemory"]
