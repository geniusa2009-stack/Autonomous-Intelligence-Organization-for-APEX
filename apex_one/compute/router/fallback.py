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


def has_native_fallback(task: str) -> bool:
    """Exact task or any parent (editorial.write.egyptian_guide -> editorial.write)."""
    parts = task.split(".")
    return any(".".join(parts[:i]) in NATIVE_FALLBACK_TASKS for i in range(len(parts), 1, -1))


WAIT_THRESHOLD_SECONDS = 60.0
_LOCAL_CACHE: dict[str, tuple[float, bool]] = {}


def local_endpoint_ok(base_url: str, ttl: float = 20.0) -> tuple[bool, str]:
    """Per-route health for local llama-server instances (each model has its own port)."""
    import time

    import httpx

    now = time.time()
    hit = _LOCAL_CACHE.get(base_url)
    if hit and now - hit[0] < ttl:
        return hit[1], "" if hit[1] else "local server not running (cached)"
    try:
        ok = httpx.get(base_url.rstrip("/").removesuffix("/v1") + "/health", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        ok = False
    _LOCAL_CACHE[base_url] = (now, ok)
    return ok, "" if ok else f"local server not running at {base_url} (apex-one local serve)"


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
            if cand.route.base_url and self.router.registry.providers[cand.route.provider].kind == "local":
                ok, why = local_endpoint_ok(cand.route.base_url)
            else:
                ok, why = self.health.usable(cand.route.provider)
            if not ok:
                considered.append({**entry, "rejected": "health", "reasons": [why]})
                continue
            if not cand.route.base_url and cand.route.provider in self.health.state and \
                    self.health.get(cand.route.provider).verified_model_ids:
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
        if has_native_fallback(req.task):
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
