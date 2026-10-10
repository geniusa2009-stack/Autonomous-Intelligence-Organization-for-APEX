"""ONE Compute schemas: providers, models, licences, capability requests, routing."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from apex_one.core.schemas.common import ApexModel, utcnow


class IntegrationStatus(StrEnum):
    """Code maturity of an adapter. Static: what has been built."""

    IMPLEMENTED = "IMPLEMENTED"                       # code exists AND was executed in tests
    CONFIGURED_BUT_UNTESTED = "CONFIGURED_BUT_UNTESTED"  # code exists, never run against the real system
    OPTIONAL_DEPENDENCY_MISSING = "OPTIONAL_DEPENDENCY_MISSING"
    NO_FREE_ENDPOINT = "NO_FREE_ENDPOINT"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    NOT_YET_SUPPORTED = "NOT_YET_SUPPORTED"


class Availability(StrEnum):
    """Runtime availability. Dynamic: what a probe found right now."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    NO_FREE_ROUTE = "NO_FREE_ROUTE"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"


class ProductionState(StrEnum):
    PRODUCTION_ALLOWED = "PRODUCTION_ALLOWED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    NON_COMMERCIAL = "NON_COMMERCIAL"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


class Level(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FRONTIER = "frontier"

    @property
    def rank(self) -> int:
        return ["none", "low", "medium", "high", "frontier"].index(self.value)


class Pricing(ApexModel):
    """Price as known to APEX. `verified` false or unknown values => firewall BLOCK."""

    input_per_mtok_usd: float | None = None
    output_per_mtok_usd: float | None = None
    per_request_usd: float | None = None
    free_tier: bool = False
    verified: bool = False
    verified_at: datetime | None = None
    note: str = ""

    def is_known_zero(self) -> bool:
        vals = [self.input_per_mtok_usd, self.output_per_mtok_usd, self.per_request_usd]
        return self.free_tier and self.verified and all(v is not None and v == 0.0 for v in vals)


class Quota(ApexModel):
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None


class PrivacyPolicy(ApexModel):
    public_data_allowed: bool = True
    private_student_data_allowed: bool = False
    training_use_unknown: bool = True
    production_allowed: bool = False


class Capabilities(ApexModel):
    reasoning: Level = Level.NONE
    coding: Level = Level.NONE
    arabic: Level = Level.NONE
    egyptian_arabic: Level = Level.NONE
    vision: bool = False
    structured_output: bool = False
    tool_use: bool = False
    design_roles: list[str] = Field(default_factory=list)


class ProviderEntry(ApexModel):
    id: str
    name: str
    kind: str                         # remote_free | local | self_hosted | mock
    api_style: str                    # openai | gemini | cloudflare | hf_inference | mock | none
    base_url: str | None = None
    base_url_env: str | None = None
    api_key_env: str | None = None
    extra_env: list[str] = Field(default_factory=list)
    free_tier: bool = False
    billing_can_be_enabled: bool = True
    privacy: PrivacyPolicy = Field(default_factory=PrivacyPolicy)
    quota: Quota = Field(default_factory=Quota)              # provider-published (often unknown)
    self_imposed_limits: Quota = Field(default_factory=Quota)  # APEX's own conservative throttle
    terms_reference: str = ""
    notes: str = ""
    integration_status: IntegrationStatus = IntegrationStatus.CONFIGURED_BUT_UNTESTED


class ProviderRoute(ApexModel):
    provider: str
    provider_model_id: str
    model_id_verified: bool = False     # true only after a live /models listing confirmed it
    base_url_env: str | None = None     # per-route endpoint (self-hosted design models)
    base_url: str | None = None         # per-route static endpoint (local llama-server instances)
    pricing: Pricing = Field(default_factory=Pricing)
    quota: Quota | None = None


class ModelEntry(ApexModel):
    id: str
    family: str
    version: str = "unspecified"
    category: str = "general"          # general | design | vision | embedding
    capabilities: Capabilities = Field(default_factory=Capabilities)
    context: int | None = None
    latency: str = "unknown"           # fast | medium | slow | unknown
    routes: list[ProviderRoute] = Field(default_factory=list)
    license_ref: str = ""
    integration_status: IntegrationStatus = IntegrationStatus.NOT_YET_SUPPORTED
    adapter: str = ""
    benchmark_scores: dict[str, float] = Field(default_factory=dict)
    health: str = "unknown"
    description: str = ""
    capability_source: str = "prior-estimate"   # prior-estimate | apex-benchmark
    local_hint: str = ""
    weights_size_gb: float | None = None
    min_ram_gb: float | None = None
    notes: str = ""


class LicenseRecord(ApexModel):
    id: str
    license_name: str = "UNKNOWN"              # VERIFIED licence name (UNKNOWN until verified)
    reported_license: str = ""                 # believed from prior knowledge; never grants rights
    commercial_use: str = "unknown"            # yes | no | conditional | unknown
    research_use: str = "unknown"
    redistribution: str = "unknown"
    derivative_use: str = "unknown"
    dataset_constraints: str = "unknown"
    provider_constraints: str = "unknown"
    production_state: ProductionState = ProductionState.UNKNOWN
    verified_at: datetime | None = None
    verified_by: str | None = None
    source_reference: str = ""
    notes: str = ""

    @property
    def production_allowed(self) -> bool:
        return self.production_state == ProductionState.PRODUCTION_ALLOWED and self.verified_at is not None


class CapabilityRequest(ApexModel):
    task: str
    min_reasoning: Level = Level.NONE
    min_coding: Level = Level.NONE
    min_arabic: Level = Level.NONE
    min_egyptian_arabic: Level = Level.NONE
    vision: bool = False
    structured_output: bool = False
    design_role: str | None = None
    min_context: int = 0
    purpose: str = "production"        # production | research | evaluation (output never enters a deliverable)
    model_id: str | None = None        # target one specific model (councils need independent judges)
    privacy_class: str = "public"
    max_cost_usd: float = 0.0


class FirewallVerdict(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class FirewallDecision(ApexModel):
    verdict: FirewallVerdict
    model_id: str
    provider: str
    reasons: list[str] = Field(default_factory=list)
    estimated_cost_usd: float | None = None


class RouteOutcome(StrEnum):
    EXECUTE = "EXECUTE"
    LOCAL_FALLBACK = "LOCAL_FALLBACK"
    QUEUE = "QUEUE"
    WAIT = "WAIT"
    DEGRADE = "DEGRADE"
    BLOCK = "BLOCK"


class RoutingDecision(ApexModel):
    request: CapabilityRequest
    outcome: RouteOutcome
    model_id: str | None = None
    provider: str | None = None
    provider_model_id: str | None = None
    considered: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    retry_after_seconds: float | None = None
    at: datetime = Field(default_factory=utcnow)


class ModelCallRecord(ApexModel):
    call_id: str
    job_id: str | None
    task: str
    model_id: str
    provider: str
    provider_model_id: str
    outcome: str
    latency_ms: float
    input_chars: int
    output_chars: int
    estimated_cost_usd: float
    error: str | None = None
    prompt_template_version: str = ""
    at: datetime = Field(default_factory=utcnow)
