"""ONE Opportunity Intelligence and reader schemas."""

from __future__ import annotations

from pydantic import Field

from apex_one.core.schemas.common import ApexModel


class Insight(ApexModel):
    """A statement about the opportunity. Facts carry claim refs; opinions are labelled."""

    text_en: str
    text_ar: str = ""
    kind: str = "fact"           # fact | apex_opinion | inference
    claim_refs: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class OpportunityModel(ApexModel):
    opportunity_name: str
    core_value: list[Insight] = Field(default_factory=list)
    hidden_value: list[Insight] = Field(default_factory=list)
    main_barrier: list[Insight] = Field(default_factory=list)
    eligibility_risk: list[Insight] = Field(default_factory=list)
    financial_risk: list[Insight] = Field(default_factory=list)
    academic_risk: list[Insight] = Field(default_factory=list)
    timing_risk: list[Insight] = Field(default_factory=list)
    likely_misunderstanding: list[Insight] = Field(default_factory=list)
    best_fit_student: list[Insight] = Field(default_factory=list)
    poor_fit_student: list[Insight] = Field(default_factory=list)
    competitive_signal: list[Insight] = Field(default_factory=list)
    decision_critical_questions: list[Insight] = Field(default_factory=list)
    student_action_plan: list[Insight] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ReaderPersona(ApexModel):
    persona_id: str
    label: str
    age_range: str = "15-18"
    english_level: str = "medium"          # weak | medium | strong
    reading_mode: str = "full"             # full | skim | mobile
    scan_budget_seconds: int = 120
    needs_full_aid: bool = False
    parent_involved: bool = False
    priorities: list[str] = Field(default_factory=list)


class ReaderModel(ApexModel):
    primary_persona: str
    personas: list[ReaderPersona]
    must_understand: list[str]             # slots readers MUST get right
    tone_notes: list[str] = Field(default_factory=list)
