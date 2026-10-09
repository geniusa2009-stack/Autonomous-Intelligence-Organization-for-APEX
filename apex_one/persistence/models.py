"""Relational schema. JSON payload columns + indexed key columns.

Works on SQLite (dev) and PostgreSQL (prod). On PostgreSQL the `embedding` columns can be
migrated to pgvector; on SQLite they are JSON arrays.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from apex_one.core.schemas.common import utcnow


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"
    job_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(40), index=True)
    opportunity_name: Mapped[str] = mapped_column(String(300))
    quality_mode: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SourceRow(Base):
    __tablename__ = "sources"
    source_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    evidence_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ClaimRow(Base):
    __tablename__ = "claims"
    claim_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    slot: Mapped[str] = mapped_column(String(200), index=True)
    predicate: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    criticality: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)


class ContradictionRow(Base):
    __tablename__ = "contradictions"
    contradiction_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    slot: Mapped[str] = mapped_column(String(200))
    resolved: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)


class FactLockRow(Base):
    __tablename__ = "fact_locks"
    lock_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    slot: Mapped[str] = mapped_column(String(200))
    lock_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("job_id", "slot", name="uq_lock_job_slot"),)


class KGNodeRow(Base):
    __tablename__ = "kg_nodes"
    node_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class KGEdgeRow(Base):
    __tablename__ = "kg_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src: Mapped[str] = mapped_column(String(120), index=True)
    rel: Mapped[str] = mapped_column(String(64), index=True)
    dst: Mapped[str] = mapped_column(String(120), index=True)
    job_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelCallRow(Base):
    __tablename__ = "model_calls"
    call_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    model_id: Mapped[str] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuotaUsageRow(Base):
    __tablename__ = "quota_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    window: Mapped[str] = mapped_column(String(16))          # minute | day
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("provider", "window", "window_start", name="uq_quota_window"),)


class LicenseVerificationRow(Base):
    """Human-recorded licence verifications. Override the YAML registry at load time."""

    __tablename__ = "license_verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    license_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    verified_by: Mapped[str] = mapped_column(String(120))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class _MemoryMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    job_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SemanticMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_semantic"


class EpisodicMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_episodic"


class EvidenceMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_evidence"


class DesignMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_design"
    verdict: Mapped[str] = mapped_column(String(16), default="neutral")   # approved | rejected | neutral


class VoiceMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_voice"
    verdict: Mapped[str] = mapped_column(String(16), default="neutral")


class FailureMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_failure"
    failure_kind: Mapped[str] = mapped_column(String(32), index=True, default="")


class ApprovalMemoryRow(_MemoryMixin, Base):
    __tablename__ = "memory_approval"
    decision: Mapped[str] = mapped_column(String(16), default="")


class PreferencePairRow(Base):
    __tablename__ = "preference_pairs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    winner: Mapped[str] = mapped_column(String(64))
    loser: Mapped[str] = mapped_column(String(64))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    annotator: Mapped[str] = mapped_column(String(120), default="human")
    winner_features: Mapped[dict] = mapped_column(JSON, default=dict)
    loser_features: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LabProposalRow(Base):
    __tablename__ = "lab_proposals"
    proposal_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), index=True)    # PROPOSED | EVALUATED | APPROVED | REJECTED | PROMOTED
    payload: Mapped[dict] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderAttestationRow(Base):
    """Human attestations: 'this key is on a free tier with billing disabled', 'terms allow production'."""

    __tablename__ = "provider_attestations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))          # free_tier_no_billing | terms_production
    attested_by: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text, default="")
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PriceCheckRow(Base):
    """Live price observations (e.g. OpenRouter /models). A non-zero price blocks the route."""

    __tablename__ = "price_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    provider_model_id: Mapped[str] = mapped_column(String(200), index=True)
    input_per_mtok_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_per_mtok_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_request_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
