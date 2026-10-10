"""Capability-based routing. Callers ask for capabilities, never for a model name."""

from __future__ import annotations

from dataclasses import dataclass

from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.compute import CapabilityRequest, IntegrationStatus, Level, ModelEntry, ProviderRoute

_LAT = {"fast": 2, "medium": 1, "slow": 0, "unknown": 0}
_ROUTABLE = {IntegrationStatus.IMPLEMENTED, IntegrationStatus.CONFIGURED_BUT_UNTESTED, IntegrationStatus.RESEARCH_ONLY}


@dataclass(frozen=True)
class Candidate:
    model: ModelEntry
    route: ProviderRoute
    score: float


def _lv(v: Level | str) -> int:
    return Level(v).rank


class CapabilityRouter:
    def __init__(self, registry: ArsenalRegistry, *, allow_mock: bool = False):
        self.registry = registry
        self.allow_mock = allow_mock

    def satisfies(self, m: ModelEntry, req: CapabilityRequest) -> bool:
        c = m.capabilities
        if req.design_role:
            return req.design_role in c.design_roles or "*" in c.design_roles
        if m.category == "design":
            return False
        return (_lv(c.reasoning) >= _lv(req.min_reasoning) and _lv(c.coding) >= _lv(req.min_coding)
                and _lv(c.arabic) >= _lv(req.min_arabic) and _lv(c.egyptian_arabic) >= _lv(req.min_egyptian_arabic)
                and (c.vision or not req.vision) and (c.structured_output or not req.structured_output)
                and (m.context or 0) >= req.min_context)

    def candidates(self, req: CapabilityRequest) -> list[Candidate]:
        out: list[Candidate] = []
        for m in self.registry.models.values():
            if m.integration_status not in _ROUTABLE or not m.routes:
                continue
            if m.family == "mock" and not self.allow_mock:
                continue
            if req.model_id and m.id != req.model_id:
                continue
            if not self.satisfies(m, req):
                continue
            bench = m.benchmark_scores.get(req.task) or m.benchmark_scores.get("overall")
            base = bench if bench is not None else (
                _lv(m.capabilities.reasoning) * 3 + _lv(m.capabilities.arabic) * 2
                + _lv(m.capabilities.egyptian_arabic) * 2 + _lv(m.capabilities.coding))
            for r in m.routes:
                prov = self.registry.providers[r.provider]
                local_bonus = 4 if (req.privacy_class != "public" and prov.kind in ("local", "self_hosted")) else 0
                out.append(Candidate(m, r, float(base) + _LAT.get(m.latency, 0) + local_bonus))
        out.sort(key=lambda c: (-c.score, c.model.id, c.route.provider))
        return out
