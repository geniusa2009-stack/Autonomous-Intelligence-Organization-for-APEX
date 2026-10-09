"""DesignRouter: builds a per-page Design DAG from the capability matrix. Never every model on every page."""

from __future__ import annotations

from dataclasses import dataclass, field

from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.compute import Availability, IntegrationStatus
from apex_one.design.models.adapters import DesignModelAdapter

PIPELINE_STEPS = {"render", "deterministic_qa", "failure_classification"}
ROUTABLE = {IntegrationStatus.IMPLEMENTED, IntegrationStatus.CONFIGURED_BUT_UNTESTED}


@dataclass
class StepChoice:
    step: str
    engine: str
    native: bool
    considered: list[dict] = field(default_factory=list)


@dataclass
class DesignRoute:
    page_type: str
    route_name: str
    steps: list[StepChoice]

    def engines(self) -> list[str]:
        return [s.engine for s in self.steps]

    def to_dict(self) -> dict:
        return {"page_type": self.page_type, "route": self.route_name,
                "steps": [{"step": s.step, "engine": s.engine, "native": s.native, "considered": s.considered}
                          for s in self.steps]}


class DesignRouter:
    def __init__(self, registry: ArsenalRegistry, adapters: dict[str, DesignModelAdapter], purpose: str = "production"):
        self.registry, self.adapters, self.purpose = registry, adapters, purpose

    def choose(self, role: str) -> StepChoice:
        spec = self.registry.design_role(role)
        considered = []
        for mid in spec.get("specialists", []):
            ad = self.adapters.get(mid)
            if ad is None:
                continue
            avail, detail = ad.availability()
            ok_lic, why_lic = ad.eligible(self.purpose)
            entry = {"model": mid, "integration": ad.integration_status.value, "availability": avail.value,
                     "detail": detail, "licence_ok": ok_lic, "licence": why_lic}
            considered.append(entry)
            if ad.integration_status in ROUTABLE and avail == Availability.AVAILABLE and ok_lic:
                return StepChoice(role, mid, False, considered)
        native = spec.get("native")
        if native:
            return StepChoice(role, native, True, considered)
        if spec.get("general_model_capability"):
            return StepChoice(role, "general-vision-model-via-broker", False, considered)
        return StepChoice(role, "none", True, considered)

    def route_for(self, node_type: str) -> DesignRoute:
        name, steps = self.registry.design_route_for(node_type)
        choices = []
        for st in steps:
            if st in PIPELINE_STEPS:
                choices.append(StepChoice(st, f"apex-{st.replace('_', '-')}", True))
            else:
                choices.append(self.choose(st))
        return DesignRoute(node_type, name, choices)
