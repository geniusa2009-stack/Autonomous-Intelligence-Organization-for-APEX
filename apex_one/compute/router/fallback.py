"""FallbackPlanner: firewall -> health -> quota -> rate limit, then LOCAL_FALLBACK / WAIT / QUEUE / DEGRADE.

It can never produce a PAY outcome: there is no such outcome.
"""

from __future__ import annotations

from apex_one.compute.firewall.zero_cost import ZeroCostFirewall
from apex_one.compute.health import HealthMonitor
from apex_one.compute.quotas.tracker import QuotaTracker, RateLimitTracker
from apex_one.compute.router.capability import Candidate, CapabilityRouter
from apex_one.core.schemas.compute import (
    CapabilityRequest,
    FirewallDecision,
    FirewallVerdict,
    RouteOutcome,
    RoutingDecision,
)

# Tasks that APEX can always perform with its own deterministic engines.
NATIVE_FALLBACK_TASKS = {
    "mission.analyze", "evidence.extract", "opportunity.model", "editorial.architect", "editorial.write",
    "editorial.critique", "design.layout", "design.html", "design.svg", "design.reward", "design.repair",
    "reader.simulate", "research.query_plan",
}
WAIT_THRESHOLD_SECONDS = 60.0


class FallbackPlanner:
    def __init__(self, router: CapabilityRouter, firewall: ZeroCostFirewall, health: HealthMonitor,
                 quotas: QuotaTracker, rate_limits: RateLimitTracker):
        self.router, self.firewall, self.health = router, firewall, health
        self.quotas, self.rate_limits = quotas, rate_limits

    def plan(self, req: CapabilityRequest, exclude: set[tuple[str, str]] | None = None
             ) -> tuple[RoutingDecision, Candidate | None, FirewallDecision | None]:
        exclude = exclude or set()
        considered: list[dict] = []
        min_wait: float | None = None
        for cand in self.router.candidates(req):
            key = (cand.model.id, cand.route.provider)
            if key in exclude:
                continue
            entry = {"model": cand.model.id, "provider": cand.route.provider, "score": cand.score}
            fw = self.firewall.evaluate(cand.model, cand.route, req)
            if fw.verdict == FirewallVerdict.BLOCK:
                considered.append({**entry, "rejected": "firewall", "reasons": fw.reasons})
                continue
            ok, why = self.health.usable(cand.route.provider)
            if not ok:
                considered.append({**entry, "rejected": "health", "reasons": [why]})
                continue
            if cand.route.provider in self.health.state and self.health.get(cand.route.provider).verified_model_ids:
                ids = self.health.get(cand.route.provider).verified_model_ids
                if cand.route.provider_model_id not in ids:
                    considered.append({**entry, "rejected": "model_not_listed",
                                       "reasons": [f"{cand.route.provider_model_id} not in provider listing"]})
                    continue
            cool = self.rate_limits.cooldown_remaining(cand.route.provider)
            if cool > 0:
                min_wait = cool if min_wait is None else min(min_wait, cool)
                considered.append({**entry, "rejected": "rate_limited", "retry_after": cool})
                continue
            qc = self.quotas.check(self.router.registry.providers[cand.route.provider])
            if not qc.ok:
                min_wait = qc.retry_after_seconds if min_wait is None else min(min_wait, qc.retry_after_seconds)
                considered.append({**entry, "rejected": "quota", "reasons": [qc.reason],
                                   "retry_after": qc.retry_after_seconds})
                continue
            return (RoutingDecision(request=req, outcome=RouteOutcome.EXECUTE, model_id=cand.model.id,
                                    provider=cand.route.provider, provider_model_id=cand.route.provider_model_id,
                                    considered=considered, reasons=["first candidate passing all gates"]),
                    cand, fw)

        reasons = [f"no executable $0 route among {len(considered)} candidates"]
        if req.task in NATIVE_FALLBACK_TASKS:
            outcome = RouteOutcome.LOCAL_FALLBACK
            reasons.append("APEX native deterministic engine will perform the task")
        elif min_wait is not None and min_wait <= WAIT_THRESHOLD_SECONDS:
            outcome = RouteOutcome.WAIT
            reasons.append(f"free capacity returns in {min_wait:.0f}s")
        elif min_wait is not None:
            outcome = RouteOutcome.QUEUE
            reasons.append(f"free capacity exhausted; queued (retry after ~{min_wait:.0f}s)")
        else:
            outcome = RouteOutcome.DEGRADE
            reasons.append("no free route and no native engine: result will be NOT_MEASURED/degraded")
        return (RoutingDecision(request=req, outcome=outcome, considered=considered, reasons=reasons,
                                retry_after_seconds=min_wait), None, None)
