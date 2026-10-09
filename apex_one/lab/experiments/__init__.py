"""ONE Lab self-improvement: detect -> propose -> experiment -> compare -> HUMAN approval -> promote/reject.

Production intelligence is never modified directly: an approved overlay is written to
config/promoted_overrides.yaml, which is versioned and reviewable.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import yaml

from apex_one.persistence.db import init_db, session_scope
from apex_one.persistence.models import LabProposalRow
from apex_one.settings import get_settings

ALLOWED_OVERLAY_KEYS = {"tournament.weights", "quality.mode_params", "voice.rejected_phrases", "genome.gene_space"}


def propose(weakness: str, overlay: dict[str, Any], by: str) -> dict:
    bad = set(overlay) - ALLOWED_OVERLAY_KEYS
    if bad:
        raise ValueError(f"overlay keys not allowed: {bad}")
    init_db()
    pid = f"LAB-{uuid.uuid4().hex[:8]}"
    payload = {"proposal_id": pid, "weakness": weakness, "overlay": overlay, "proposed_by": by,
               "at": datetime.now(UTC).isoformat(), "results": None}
    with session_scope() as s:
        s.add(LabProposalRow(proposal_id=pid, status="PROPOSED", payload=payload))
    return payload


def run_experiment(proposal_id: str) -> dict:
    from apex_one.design.tournament import tournament as T
    from apex_one.lab.benchmarks.design_bench import run_design_bench

    with session_scope() as s:
        row = s.get(LabProposalRow, proposal_id)
        if row is None:
            raise KeyError(proposal_id)
        payload = dict(row.payload)
    out_dir = get_settings().artifacts_dir / "lab" / proposal_id
    baseline = run_design_bench(out_dir / "baseline")
    original = dict(T.WEIGHTS)
    try:
        if "tournament.weights" in payload["overlay"]:
            T.WEIGHTS.update(payload["overlay"]["tournament.weights"])
        candidate = run_design_bench(out_dir / "candidate")
    finally:
        T.WEIGHTS.clear()
        T.WEIGHTS.update(original)
    payload["results"] = {"baseline": {"passed": baseline["passed"], "measured": baseline["measured"]},
                          "candidate": {"passed": candidate["passed"], "measured": candidate["measured"]},
                          "better_or_equal": candidate["passed"] >= baseline["passed"]}
    with session_scope() as s:
        row = s.get(LabProposalRow, proposal_id)
        row.status, row.payload = "EVALUATED", payload
    return payload


def decide(proposal_id: str, by: str, approve: bool) -> dict:
    with session_scope() as s:
        row = s.get(LabProposalRow, proposal_id)
        if row is None:
            raise KeyError(proposal_id)
        if row.status != "EVALUATED":
            raise RuntimeError("a proposal must be EVALUATED by the benchmark before a human decision")
        payload = dict(row.payload)
        payload["decided_by"], payload["decided_at"] = by, datetime.now(UTC).isoformat()
        row.status = "PROMOTED" if approve else "REJECTED"
        row.payload = payload
    if approve:
        path = get_settings().config_dir / "promoted_overrides.yaml"
        current = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "overrides": []}
        current["overrides"].append({"proposal_id": proposal_id, "overlay": payload["overlay"], "approved_by": by,
                                     "at": payload["decided_at"]})
        path.write_text(yaml.safe_dump(current, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"proposal_id": proposal_id, "status": "PROMOTED" if approve else "REJECTED",
            "results": json.loads(json.dumps(payload.get("results")))}
