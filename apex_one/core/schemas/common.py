"""Shared schema primitives."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def stable_hash(payload: Any) -> str:
    data = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class ApexModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=False)


class MetricStatus(StrEnum):
    MEASURED = "MEASURED"
    NOT_MEASURED = "NOT_MEASURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Metric(ApexModel):
    """A quality metric. A score exists ONLY when it was actually measured."""

    name: str
    status: MetricStatus = MetricStatus.NOT_MEASURED
    value: float | None = None
    unit: str = "score_0_100"
    method: str = ""
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)

    @classmethod
    def measured(cls, name: str, value: float, method: str, evidence: list[str] | None = None,
                 unit: str = "score_0_100") -> "Metric":
        return cls(name=name, status=MetricStatus.MEASURED, value=round(float(value), 3),
                   method=method, evidence=evidence or [], unit=unit)

    @classmethod
    def not_measured(cls, name: str, reason: str) -> "Metric":
        return cls(name=name, status=MetricStatus.NOT_MEASURED, value=None, reason=reason)

    def model_post_init(self, __context: Any) -> None:
        if self.status != MetricStatus.MEASURED and self.value is not None:
            raise ValueError(f"metric {self.name}: value present but status={self.status}")
        if self.status == MetricStatus.MEASURED and self.value is None:
            raise ValueError(f"metric {self.name}: MEASURED requires a value")


class Provenance(ApexModel):
    """Which engines contributed to an artifact. Used for licence enforcement."""

    engine_ids: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    research_only: bool = False
    notes: list[str] = Field(default_factory=list)

    def merge(self, other: "Provenance") -> "Provenance":
        return Provenance(
            engine_ids=sorted(set(self.engine_ids) | set(other.engine_ids)),
            model_ids=sorted(set(self.model_ids) | set(other.model_ids)),
            research_only=self.research_only or other.research_only,
            notes=self.notes + other.notes,
        )
