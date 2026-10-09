"""ONE Evidence schemas: sources, evidence, claims, contradictions, verification, fact locks."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from apex_one.core.schemas.common import ApexModel, new_id, stable_hash, utcnow


class SourceKind(StrEnum):
    OFFICIAL = "official"              # the institution / program owner
    OFFICIAL_DOCUMENT = "official_document"
    GOVERNMENT = "government"
    THIRD_PARTY = "third_party"
    AGGREGATOR = "aggregator"
    FORUM = "forum"
    UNKNOWN = "unknown"


class Source(ApexModel):
    source_id: str = Field(default_factory=lambda: new_id("S"))
    url: str
    title: str = ""
    domain: str = ""
    kind: SourceKind = SourceKind.UNKNOWN
    content_type: str = "text/html"
    content_hash: str = ""
    fetched_at: datetime = Field(default_factory=utcnow)
    published_or_updated: str | None = None
    cycle_year: int | None = None        # the admission/application year the page talks about
    authority: float = 0.0               # 0..1 from SourceAuthorityJudge
    synthetic: bool = False              # true for offline benchmark fixtures
    fetch_method: str = "http"
    text_path: str | None = None         # cached extracted text (artifact relative path)


class Evidence(ApexModel):
    evidence_id: str = Field(default_factory=lambda: new_id("E"))
    source_id: str
    quote: str
    locator: str = ""                    # section heading / page number / css path
    extractor: str = "rule"              # rule | model:<id> | human
    extracted_at: datetime = Field(default_factory=utcnow)


class Criticality(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    CONTEXT = "context"


CRITICAL_PREDICATES = frozenset({
    "deadline", "eligibility", "age", "grade", "country_eligibility", "fee", "funding",
    "scholarship_coverage", "deposit", "test_requirement", "test_minimum",
    "application_requirement", "visa_logistics",
})


class ClaimStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    CORROBORATED = "CORROBORATED"
    CONFLICTED = "CONFLICTED"
    VERIFIED = "VERIFIED"
    LOCKED = "LOCKED"
    REJECTED = "REJECTED"          # e.g. stale cycle or superseded
    NEEDS_HUMAN = "NEEDS_HUMAN"


class ValueType(StrEnum):
    DATE = "date"
    MONEY = "money"
    NUMBER = "number"
    PERCENT = "percent"
    BOOLEAN = "boolean"
    TEXT = "text"
    LIST = "list"


class NormalizedValue(ApexModel):
    type: ValueType
    raw: str
    canonical: str                 # e.g. 2027-01-15, USD 0, 80, true, normalized text
    currency: str | None = None
    amount: float | None = None
    qualifier: str | None = None   # e.g. "per year", "minimum", "postmarked"

    def key(self) -> str:
        return f"{self.type}:{self.canonical}"


class Claim(ApexModel):
    claim_id: str = Field(default_factory=lambda: new_id("C"))
    subject: str                   # e.g. institution/program
    predicate: str                 # deadline, fee, test_minimum, ...
    qualifier: str = ""            # e.g. "international regular decision", "TOEFL iBT"
    value: NormalizedValue
    criticality: Criticality = Criticality.CONTEXT
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    freshness: str = "unknown"     # current-cycle | previous-cycle | undated | unknown
    status: ClaimStatus = ClaimStatus.EXTRACTED
    notes: list[str] = Field(default_factory=list)

    @property
    def slot(self) -> str:
        """Stable slot key used by downstream text: predicate + qualifier."""
        q = self.qualifier.strip().lower().replace(" ", "_")
        return f"{self.predicate}{'.' + q if q else ''}"


class ContradictionKind(StrEnum):
    VALUE_CONFLICT = "value_conflict"
    STALE_CYCLE = "stale_cycle"
    SCOPE_DIFFERENCE = "scope_difference"   # e.g. domestic vs international
    UNIT_DIFFERENCE = "unit_difference"


class Contradiction(ApexModel):
    contradiction_id: str = Field(default_factory=lambda: new_id("X"))
    slot: str
    claim_ids: list[str]
    kind: ContradictionKind
    description: str
    resolved: bool = False
    resolution: str = ""
    winning_claim_id: str | None = None
    critical: bool = False


class Verification(ApexModel):
    claim_id: str
    primary_source_found: bool
    independent_sources: int
    official_sources: int
    contradiction_search_done: bool
    freshness_ok: bool
    semantic_resolution: str
    verdict: ClaimStatus
    reasons: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utcnow)


class FactLock(ApexModel):
    """Immutable downstream record of a verified critical value."""

    lock_id: str = Field(default_factory=lambda: new_id("L"))
    claim_id: str
    slot: str
    predicate: str
    qualifier: str
    value: NormalizedValue
    display_en: str
    display_ar: str
    source_ids: list[str]
    criticality: Criticality = Criticality.CRITICAL
    hedge: str = ""                       # e.g. "estimated" — writer must surface it
    verified_by: str = "apex-verifier"    # apex-verifier | human:<name>
    locked_at: datetime = Field(default_factory=utcnow)
    lock_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.lock_hash:
            object.__setattr__(self, "lock_hash", stable_hash(
                [self.claim_id, self.slot, self.value.canonical, self.display_en, self.display_ar]))

    def verify_integrity(self) -> bool:
        return self.lock_hash == stable_hash(
            [self.claim_id, self.slot, self.value.canonical, self.display_en, self.display_ar])
