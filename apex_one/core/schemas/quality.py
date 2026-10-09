"""Quality court, gates and reports."""

from __future__ import annotations

from pydantic import Field

from apex_one.core.schemas.common import ApexModel, Metric


class QAIssue(ApexModel):
    check: str
    severity: str           # critical | major | minor | info
    message: str
    page: str | None = None
    selector: str | None = None
    data: dict = Field(default_factory=dict)


class QAReport(ApexModel):
    scope: str              # page id | document
    issues: list[QAIssue] = Field(default_factory=list)
    metrics: dict[str, Metric] = Field(default_factory=dict)

    @property
    def critical(self) -> list[QAIssue]:
        return [i for i in self.issues if i.severity == "critical"]


class JudgeVerdict(ApexModel):
    judge: str
    metric: Metric
    passed: bool | None          # None => could not judge (NOT_MEASURED)
    critical: bool = False       # a critical judge failing is a veto
    rationale: list[str] = Field(default_factory=list)
    engine: str = ""


class GateResult(ApexModel):
    gate: str
    kind: str                    # critical | target
    threshold: float | None
    metric: Metric
    status: str                  # PASS | FAIL | NOT_MEASURED


class QualityReport(ApexModel):
    job_id: str
    gates: list[GateResult] = Field(default_factory=list)
    verdicts: list[JudgeVerdict] = Field(default_factory=list)
    disagreements: list[dict] = Field(default_factory=list)
    release_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    release_candidate: bool = False
