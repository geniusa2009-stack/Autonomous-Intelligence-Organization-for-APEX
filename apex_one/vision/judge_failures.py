"""Vision-judge failure patterns kept in FailureMemory, so a known failure mode is rejected automatically.

PAIRWISE_POSITION_BIAS: the judge picks the same visual SLOT (A or B) whatever page is in it. Severity from the
position_bias_rate of the order-swapped calibration: >= 0.8 severe, >= 0.4 moderate, > POSITION_BIAS_MAX mild.
A model build (GGUF digest) with a remembered SEVERE pattern is rejected as a pairwise judge without re-running —
a new build (different digest) must earn its own calibration.
"""

from __future__ import annotations

from typing import Any

PATTERN = "PAIRWISE_POSITION_BIAS"


def position_bias_severity(rate: float | None) -> str | None:
    from apex_one.vision.pairwise import POSITION_BIAS_MAX

    if rate is None or rate <= POSITION_BIAS_MAX:
        return None
    return "severe" if rate >= 0.8 else "moderate" if rate >= 0.4 else "mild"


def bias_rate(record: dict[str, Any]) -> float | None:
    if record.get("position_bias_rate") is not None:
        return record["position_bias_rate"]
    b = [d.get("position_bias") for d in (record.get("detail") or {}).values() if d.get("position_bias") is not None]
    return round(sum(b) / len(b), 3) if b else None


def remember(model_id: str, record: dict[str, Any], digest: str | None, db_url: str | None = None) -> str | None:
    """Store the pattern (once per model build). Returns the severity stored, or None if there is no pattern."""
    from apex_one.memory import FailureMemory

    rate = bias_rate(record)
    sev = position_bias_severity(rate)
    if sev is None:
        return None
    mem = FailureMemory(db_url)
    key = f"vision_judge:{model_id}"
    if any((r.payload or {}).get("digest") == digest and r.failure_kind == PATTERN for r in mem.by_key(key)):
        return sev
    said = [d.get("reasons") for d in (record.get("detail") or {}).values()]
    mem.add(key, f"{model_id} picks the same visual slot regardless of content (position_bias_rate {rate})",
            payload={"pattern": PATTERN, "severity": sev, "position_bias_rate": rate, "digest": digest,
                     "correct": record.get("correct"), "sample_reasons": said[:2]}, failure_kind=PATTERN)
    return sev


def known_failure(model_id: str, digest: str | None, db_url: str | None = None) -> str | None:
    """Reason to reject this model build as a pairwise judge, if FailureMemory holds a SEVERE slot-following
    pattern for exactly this build."""
    try:
        from apex_one.memory import FailureMemory

        rows = FailureMemory(db_url).by_key(f"vision_judge:{model_id}")
    except Exception:  # noqa: BLE001 — no memory store: no remembered failure
        return None
    for r in rows:
        p = r.payload or {}
        if r.failure_kind == PATTERN and p.get("severity") == "severe" and p.get("digest") == digest:
            return f"FailureMemory: {PATTERN} severe (position_bias_rate {p.get('position_bias_rate')})"
    return None
