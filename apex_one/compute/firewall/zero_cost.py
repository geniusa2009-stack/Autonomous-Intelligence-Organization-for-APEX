"""ZeroCostFirewall — every model request passes through here. Never PAY.

Decision table (all must hold for ALLOW):
  1. Global policy max cost is $0 and the request carries no budget.
  2. Provider is a free-tier/local provider.
  3. Price is KNOWN to be zero:
       local / self-hosted / mock          -> zero by construction
       remote                              -> registry price zero AND (fresh live price check == 0
                                              OR human attestation 'free_tier_no_billing')
     A live observation of any non-zero price blocks, even if an attestation exists.
  4. OpenRouter routes must be ':free' variants.
  5. Licence: production purpose requires a VERIFIED production licence; research and evaluation
     purposes require a licence that is not BLOCKED. Evaluation output (judgements, benchmark scores)
     never enters a deliverable; the release LicenseGuard enforces that.
  6. Provider terms: production purpose on a remote provider requires terms verification.
  7. Privacy: private student data only to providers that allow it (local by default).
  8. Estimated cost must be exactly 0.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apex_one.compute.cost import CostEstimator
from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.policies.cost import COST_POLICY
from apex_one.core.schemas.compute import (
    EVALUATION_TASKS,
    CapabilityRequest,
    FirewallDecision,
    FirewallVerdict,
    ModelEntry,
    ProviderRoute,
)

ZERO_BY_CONSTRUCTION = {"local", "self_hosted", "mock"}
PRICE_CHECK_TTL = timedelta(hours=24)


class PaidRouteBlocked(Exception):
    """Raised when anything attempts to execute a route the firewall did not ALLOW."""


@dataclass
class PriceObservation:
    provider: str
    provider_model_id: str
    input_per_mtok_usd: float | None
    output_per_mtok_usd: float | None
    per_request_usd: float | None
    at: datetime

    def is_zero(self) -> bool:
        vals = (self.input_per_mtok_usd, self.output_per_mtok_usd, self.per_request_usd)
        return all(v is not None and v == 0.0 for v in vals)


class ZeroCostFirewall:
    def __init__(self, registry: ArsenalRegistry, price_observations: list[PriceObservation] | None = None):
        self.registry = registry
        self._prices: dict[tuple[str, str], PriceObservation] = {}
        for obs in price_observations or []:
            self.observe_price(obs)
        assert COST_POLICY.max_api_cost_usd == 0.0
        assert not COST_POLICY.paid_fallback_allowed and not COST_POLICY.auto_billing_allowed

    def observe_price(self, obs: PriceObservation) -> None:
        self._prices[(obs.provider, obs.provider_model_id)] = obs

    def _latest_price(self, provider: str, pid: str) -> PriceObservation | None:
        return self._prices.get((provider, pid))

    def evaluate(self, model: ModelEntry, route: ProviderRoute, request: CapabilityRequest,
                 now: datetime | None = None) -> FirewallDecision:
        now = now or datetime.now(UTC)
        reasons: list[str] = []
        provider = self.registry.providers.get(route.provider)

        if request.max_cost_usd != 0.0:
            reasons.append(f"request carries a budget ({request.max_cost_usd}); APEX budget is exactly $0")
        if COST_POLICY.max_api_cost_usd != 0.0:  # pragma: no cover - constant
            reasons.append("global cost policy corrupted")
        if provider is None:
            return FirewallDecision(verdict=FirewallVerdict.BLOCK, model_id=model.id, provider=route.provider,
                                    reasons=[f"unknown provider {route.provider}"])
        if not provider.free_tier:
            reasons.append(f"provider {provider.id} is not a free-tier provider")

        pricing = route.pricing
        estimated = CostEstimator.estimate(pricing)
        if provider.kind in ZERO_BY_CONSTRUCTION:
            if estimated is None or estimated != 0.0:
                reasons.append(f"local/self-hosted route declares non-zero or unknown price ({estimated})")
        else:
            if estimated is None:
                reasons.append("unknown pricing")
            elif estimated != 0.0:
                reasons.append(f"registry price is non-zero (${estimated:.6f}/request)")
            elif not pricing.free_tier:
                reasons.append("route is not marked free_tier")
            obs = self._latest_price(provider.id, route.provider_model_id)
            if obs is not None and not obs.is_zero():
                reasons.append("live price check observed a NON-ZERO price (provider changed price)")
                estimated = None
            fresh_zero = obs is not None and obs.is_zero() and now - obs.at <= PRICE_CHECK_TTL
            attested = self.registry.has_attestation(provider.id, "free_tier_no_billing", now)
            if not (fresh_zero or attested):  # YAML 'verified' flags never suffice for remote routes
                reasons.append("price not verified: needs a fresh live $0 price check or a human free-tier "
                               "attestation (apex-one providers attest)")
            if provider.id == "openrouter" and not route.provider_model_id.endswith(":free"):
                reasons.append("OpenRouter route is not a ':free' variant")

        # Licence
        if request.purpose == "production":
            if not self.registry.production_allowed(model):
                lic = self.registry.license_for(model)
                reasons.append(f"licence {lic.id} state={lic.production_state} verified={lic.verified_at is not None}: "
                               f"not production-allowed")
            if provider.kind not in ZERO_BY_CONSTRUCTION and not (
                provider.privacy.production_allowed or self.registry.has_attestation(provider.id, "terms_production", now)
            ):
                reasons.append(f"provider {provider.id} terms not verified for production use")
            if provider.kind == "mock":
                reasons.append("mock provider can never serve production output")
        elif not self.registry.research_allowed(model):
            reasons.append(f"licence BLOCKED even for {request.purpose}")
        if request.purpose == "evaluation" and not request.task.startswith(EVALUATION_TASKS):
            reasons.append(f"purpose=evaluation is only for judging/benchmark tasks {EVALUATION_TASKS}, "
                           f"not task {request.task!r}")

        # Privacy
        if request.privacy_class == "private-student-data" and not provider.privacy.private_student_data_allowed:
            reasons.append(f"provider {provider.id} may not receive private student data")
        if not provider.privacy.public_data_allowed:
            reasons.append(f"provider {provider.id} disallows even public data")

        verdict = FirewallVerdict.BLOCK if reasons else FirewallVerdict.ALLOW
        return FirewallDecision(verdict=verdict, model_id=model.id, provider=provider.id, reasons=reasons,
                                estimated_cost_usd=estimated)

    @staticmethod
    def assert_allowed(decision: FirewallDecision | None, provider: str) -> None:
        """Defense in depth: adapters call this immediately before any network request."""
        if decision is None or decision.verdict != FirewallVerdict.ALLOW:
            raise PaidRouteBlocked(f"execution on {provider} without an ALLOW decision")
        if decision.provider != provider:
            raise PaidRouteBlocked("firewall decision does not match the route being executed")
        if decision.estimated_cost_usd is None or decision.estimated_cost_usd != 0.0:
            raise PaidRouteBlocked(f"estimated cost {decision.estimated_cost_usd} is not exactly $0")
