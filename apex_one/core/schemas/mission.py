"""Governor schemas: missions, jobs, policies, plans, results, gates."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from apex_one.core.schemas.common import ApexModel, new_id, utcnow


class OpportunityType(StrEnum):
    UNIVERSITY_ADMISSION = "university_admission"
    SCHOLARSHIP = "scholarship"
    SCHOOL = "school"
    COMPETITION = "competition"
    EXCHANGE_PROGRAM = "exchange_program"
    FELLOWSHIP = "fellowship"
    SUMMER_PROGRAM = "summer_program"
    OTHER = "other"


class QualityMode(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"
    ULTRA = "ultra"


class RiskClass(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH_FACTUAL = "high-factual"


class PrivacyClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE_STUDENT_DATA = "private-student-data"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    QUEUED = "QUEUED"            # waiting for free capacity
    BLOCKED = "BLOCKED"          # needs a human / configuration
    FAILED = "FAILED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    RELEASE_CANDIDATE = "RELEASE_CANDIDATE"
    FINAL = "FINAL"


class Mission(ApexModel):
    text: str
    opportunity_name: str
    opportunity_type: OpportunityType = OpportunityType.OTHER
    institution: str | None = None
    cycle: str | None = None          # e.g. "Fall 2027"
    cycle_year: int | None = None
    audience: str = "Egyptian students"
    languages: list[str] = Field(default_factory=lambda: ["ar-EG", "en"])


class RiskProfile(ApexModel):
    risk_class: RiskClass = RiskClass.HIGH_FACTUAL
    critical_predicates: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class ComputePolicy(ApexModel):
    api_budget_usd: float = 0.0
    allow_remote_free: bool = True
    allow_local: bool = True
    allow_research_only_models: bool = False     # only ONE Lab sets this
    max_model_calls: int = 400

    @field_validator("api_budget_usd")
    @classmethod
    def _zero_only(cls, v: float) -> float:
        if v != 0.0:
            raise ValueError("APEX cost policy: api_budget_usd must be exactly 0.0")
        return v


class QualityProfile(ApexModel):
    mode: QualityMode = QualityMode.ULTRA
    layout_candidates_per_page: int = 16
    tournament_generations: int = 3
    elite_count: int = 2
    convergence_epsilon: float = 0.5
    reader_personas: list[str] = Field(default_factory=list)


class RetryPolicy(ApexModel):
    max_attempts_per_stage: int = 3
    max_recovery_loops: int = 4
    backoff_seconds: float = 0.0


class JobPolicy(ApexModel):
    compute: ComputePolicy = Field(default_factory=ComputePolicy)
    quality: QualityProfile = Field(default_factory=QualityProfile)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    human_release_required: bool = True
    seed: int = 20271

    @field_validator("human_release_required")
    @classmethod
    def _always_human(cls, v: bool) -> bool:
        if not v:
            raise ValueError("human release approval cannot be disabled")
        return v


class HumanGate(ApexModel):
    gate_id: str = Field(default_factory=lambda: new_id("G"))
    name: str
    required_for_state: str
    status: str = "PENDING"      # PENDING | APPROVED | REJECTED
    approver: str | None = None
    decided_at: datetime | None = None
    notes: str = ""


class PlanStage(ApexModel):
    stage: str
    depends_on: list[str] = Field(default_factory=list)
    workers: int = 1
    budget_model_calls: int = 0
    checks: list[str] = Field(default_factory=list)


class ExecutionPlan(ApexModel):
    plan_id: str = Field(default_factory=lambda: new_id("P"))
    stages: list[PlanStage]
    research_workers: int
    research_roles: list[str]
    design_route_summary: dict[str, list[str]] = Field(default_factory=dict)
    stop_conditions: list[str] = Field(default_factory=list)
    escalations: list[str] = Field(default_factory=list)


class Failure(ApexModel):
    kind: str          # FACT | VOICE | RTL | GEOMETRY | AESTHETIC | READER | RHYTHM | COMPUTE | RESEARCH | LICENSE
    stage: str
    message: str
    critical: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    at: datetime = Field(default_factory=utcnow)


class StageResult(ApexModel):
    stage: str
    ok: bool
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    outputs: list[str] = Field(default_factory=list)
    failures: list[Failure] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    next_state: str | None = None


class Job(ApexModel):
    job_id: str = Field(default_factory=lambda: new_id("J"))
    mission: Mission
    policy: JobPolicy = Field(default_factory=JobPolicy)
    risk: RiskProfile = Field(default_factory=RiskProfile)
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC
    status: JobStatus = JobStatus.PENDING
    state: str = "NEW"
    history: list[StageResult] = Field(default_factory=list)
    gates: list[HumanGate] = Field(default_factory=list)
    recovery_loops: dict[str, int] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    source_inputs: list[str] = Field(default_factory=list)    # local files/dirs supplied by user
    offline_fixture: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    versions: dict[str, str] = Field(default_factory=dict)
