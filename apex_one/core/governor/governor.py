"""ONE Governor: plans and governs. It never researches, writes or designs itself."""

from __future__ import annotations

from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.mission import ExecutionPlan, Job, PlanStage, QualityMode, QualityProfile
from apex_one.core.state_machine.definition import CHECKS, MAIN_PATH, S
from apex_one.research.swarm import plan_workers

MODE_PARAMS = {
    QualityMode.DRAFT: dict(initial_important=6, initial_other=4, population=4, generations=1, directions=1),
    QualityMode.STANDARD: dict(initial_important=12, initial_other=8, population=6, generations=2, directions=1),
    QualityMode.HIGH: dict(initial_important=20, initial_other=12, population=8, generations=3, directions=2),
    QualityMode.ULTRA: dict(initial_important=32, initial_other=16, population=10, generations=4, directions=3),
}


def quality_profile(mode: QualityMode) -> QualityProfile:
    p = MODE_PARAMS[mode]
    return QualityProfile(mode=mode, layout_candidates_per_page=p["initial_important"],
                          tournament_generations=p["generations"], elite_count=2, convergence_epsilon=0.3)


class Governor:
    def __init__(self, registry: ArsenalRegistry):
        self.registry = registry

    def plan(self, job: Job) -> ExecutionPlan:
        mode = job.policy.quality.mode
        workers, roles = plan_workers(mode)
        params = MODE_PARAMS[mode]
        stages = []
        prev = None
        for st in MAIN_PATH:
            if st in (S.NEW,):
                continue
            stages.append(PlanStage(stage=st.value, depends_on=[prev] if prev else [],
                                    workers=workers if st in (S.SOURCE_DISCOVERY, S.SOURCE_EXPANSION, S.DOCUMENT_PARSE,
                                                              S.EVIDENCE_EXTRACTION) else 1,
                                    budget_model_calls=40 if st in (S.EVIDENCE_EXTRACTION, S.DRAFT, S.VISION_QA) else 0,
                                    checks=list(CHECKS.get(st, ()))))
            prev = st.value
        routes = {name: list(r["steps"]) for name, r in self.registry.design_matrix["routes"].items()}
        return ExecutionPlan(
            stages=stages, research_workers=workers, research_roles=roles, design_route_summary=routes,
            stop_conditions=[
                "unresolved critical contradiction -> AWAITING_HUMAN at FACT_RESOLUTION",
                "missing must-lock fact after research budget -> AWAITING_HUMAN",
                "no research route -> BLOCKED (configuration)",
                "critical deterministic failure after layout recovery budget -> BLOCKED",
                "quality critical gate failure -> not a release candidate",
                "RELEASE_CANDIDATE -> FINAL only by human approval",
            ],
            escalations=[f"layout search: {params['initial_important']} candidates for important pages, "
                         f"{params['initial_other']} otherwise; population {params['population']}; "
                         f"{params['generations']} generations; {params['directions']} creative directions",
                         f"retry budget per failure kind: {job.policy.retry.max_recovery_loops}"])
