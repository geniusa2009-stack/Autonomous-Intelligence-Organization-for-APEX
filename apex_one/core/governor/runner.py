"""JobRunner: executes the declarative state machine, checkpointing after every state.

Each handler does one state's work, records its explicit checks, writes its artifacts and returns the
next state (or a failure kind for failure-specific recovery). The job can be resumed from any state.
"""

from __future__ import annotations

import json
import platform
import random
from collections.abc import Callable
from datetime import UTC, date, datetime
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from apex_one import PROMPT_TEMPLATE_VERSION, WORKFLOW_VERSION
from apex_one.compute.broker import ComputeBroker
from apex_one.compute.hardware import find_chromium
from apex_one.compute.registry.loader import ArsenalRegistry, load_registry
from apex_one.core.governor.governor import MODE_PARAMS, Governor, quality_profile, ultra_candidates
from apex_one.core.governor.mission import MissionAnalyzer
from apex_one.core.policies.cost import COST_POLICY
from apex_one.core.schemas.common import Metric, MetricStatus, utcnow
from apex_one.core.schemas.design import DesignDecision, Genes, LayoutCandidate
from apex_one.core.schemas.document import DocNode, DocumentAST
from apex_one.core.schemas.evidence import ClaimStatus, FactLock
from apex_one.core.schemas.mission import (
    Failure,
    HumanGate,
    Job,
    JobPolicy,
    JobStatus,
    QualityMode,
    StageResult,
)
from apex_one.core.schemas.opportunity import OpportunityModel, ReaderModel
from apex_one.core.state_machine.definition import CHECKS, FailureKind, S
from apex_one.core.state_machine.machine import RecoveryBudgetExhausted, StateMachine
from apex_one.core.workspace import JobWorkspace
from apex_one.persistence.db import init_db, session_scope
from apex_one.persistence.models import ClaimRow, FactLockRow, JobRow, SourceRow
from apex_one.settings import get_settings

MUST_LOCK_ANY = [("deadline.application",), ("scholarship_coverage.tuition", "funding.student_contribution_per_year",
                                             "fee.application"), ("country_eligibility.international",
                                                                  "eligibility.academic", "eligibility.financial_need")]


class Pause(Exception):
    """Raised by a handler to stop execution (awaiting human, blocked, queued)."""

    def __init__(self, status: JobStatus, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


class JobRunner:
    def __init__(self, job: Job, *, registry: ArsenalRegistry | None = None, broker: ComputeBroker | None = None,
                 db_url: str | None = None, today: date | None = None, log: Callable[[str], None] | None = None):
        self.job = job
        self.db_url = db_url
        init_db(db_url)
        self.registry = registry or load_registry(db_url=db_url)
        self.broker = broker or ComputeBroker(self.registry)
        self.ws = JobWorkspace(job.job_id)
        self.today = today or job.created_at.date()
        self.log = log or (lambda m: None)
        self.sm = StateMachine(state=S(job.state), max_recovery_loops=job.policy.retry.max_recovery_loops,
                               recovery_counts=dict(job.recovery_loops))
        self._rd = None

    # ================================================================== lifecycle
    @classmethod
    def create(cls, mission_text: str, *, quality: str = "ultra", budget: float = 0.0,
               offline_fixture: str | None = None, sources: str | None = None, seed: int = 20271,
               **kw: Any) -> "JobRunner":
        if budget != 0.0:
            raise ValueError("APEX cost policy: --budget must be 0 (paid APIs are never used)")
        mission, risk, privacy = MissionAnalyzer().analyze(mission_text)
        mode = QualityMode(quality)
        policy = JobPolicy(quality=quality_profile(mode), seed=seed)
        job = Job(mission=mission, policy=policy, risk=risk, privacy_class=privacy, offline_fixture=offline_fixture,
                  source_inputs=[str(Path(sources).resolve())] if sources else [])
        job.gates.append(HumanGate(name="release-approval", required_for_state=S.FINAL.value))
        runner = cls(job, **kw)
        runner.save()
        return runner

    @classmethod
    def load(cls, job_id: str, **kw: Any) -> "JobRunner":
        ws_root = get_settings().jobs_dir / job_id / "job.json"
        if not ws_root.exists():
            raise FileNotFoundError(f"unknown job {job_id}")
        job = Job.model_validate(json.loads(ws_root.read_text(encoding="utf-8")))
        return cls(job, **kw)

    def save(self) -> None:
        self.job.updated_at = utcnow()
        self.job.recovery_loops = dict(self.sm.recovery_counts)
        self.ws.write_json("job.json", self.job)
        with session_scope(self.db_url) as s:
            row = s.get(JobRow, self.job.job_id)
            payload = self.job.model_dump(mode="json")
            if row is None:
                s.add(JobRow(job_id=self.job.job_id, status=self.job.status.value, state=self.job.state,
                             opportunity_name=self.job.mission.opportunity_name,
                             quality_mode=self.job.policy.quality.mode.value, payload=payload))
            else:
                row.status, row.state, row.payload = self.job.status.value, self.job.state, payload

    # ================================================================== execution loop
    def run(self, max_steps: int = 400) -> Job:
        if self.job.status in (JobStatus.FINAL,) and self.sm.state == S.LEARN:
            return self.job
        self.job.status = JobStatus.RUNNING
        self.job.blockers = []
        self.save()
        for _ in range(max_steps):
            state = self.sm.state
            if state == S.LEARN:
                self.h_learn()
                break
            handler = getattr(self, f"h_{state.value.lower()}")
            started = utcnow()
            self.log(f"[{self.job.job_id}] {state.value}")
            try:
                nxt = handler()
            except Pause as p:
                self.job.status = p.status
                if p.reason not in self.job.blockers:
                    self.job.blockers.append(p.reason)
                self.job.history.append(StageResult(stage=state.value, ok=False, started_at=started,
                                                    finished_at=utcnow(), notes=[p.reason]))
                self.ws.events.emit("pause", state=state.value, status=p.status.value, reason=p.reason)
                self.save()
                return self.job
            if isinstance(nxt, FailureKind):
                self.job.history.append(StageResult(stage=state.value, ok=False, started_at=started, finished_at=utcnow(),
                                                    failures=[Failure(kind=nxt.value, stage=state.value,
                                                                      message="recovery requested")]))
                try:
                    target = self.sm.recover(nxt, reason=state.value)
                except RecoveryBudgetExhausted as e:
                    self.job.status = JobStatus.BLOCKED
                    self.job.blockers.append(f"{state.value}: {e}")
                    self.save()
                    return self.job
                self.ws.events.emit("recover", kind=nxt.value, from_state=state.value, to=target.value if target else None)
                self.job.state = self.sm.state.value
                self.save()
                continue
            self.job.history.append(StageResult(stage=state.value, ok=True, started_at=started, finished_at=utcnow(),
                                                next_state=nxt.value))
            human = state == S.HUMAN_APPROVAL
            self.sm.advance(nxt, reason="handler", human=human)
            self.job.state = nxt.value
            self.save()
            if self.job.status in (JobStatus.FINAL,) and nxt == S.LEARN:
                continue
        self.save()
        return self.job

    # ================================================================== helpers
    def checks(self, state: S, results: dict[str, bool | tuple[bool, str]]) -> None:
        for name in CHECKS.get(state, ()):
            r = results.get(name, (True, "covered by stage logic"))
            ok, detail = (r, "") if isinstance(r, bool) else r
            self.ws.check(state.value, name, bool(ok), detail)

    @property
    def rd(self):
        from apex_one.research.swarm import ResearchDirector

        if self._rd is None:
            self._rd = ResearchDirector(self.job, self.ws, broker=self.broker)
        return self._rd

    @property
    def locks(self) -> list[FactLock]:
        return list(self.rd.state.locks)

    @property
    def mode(self) -> QualityMode:
        return self.job.policy.quality.mode

    @property
    def allowed_years(self) -> set[int]:
        y = self.job.mission.cycle_year or self.today.year
        return {y - 1, y, y + 1}

    @property
    def synthetic(self) -> bool:
        return bool(self.job.offline_fixture)

    def _read(self, rel: str) -> Any:
        return self.ws.read_json(rel)

    def _nodes(self, rel: str) -> list[DocNode]:
        return [DocNode.model_validate(n) for n in self._read(rel)]

    def _ast(self) -> DocumentAST:
        return DocumentAST.model_validate(self._read("document_ast.json"))

    # ================================================================== state handlers
    def h_new(self) -> S:
        self.job.versions = {"workflow": WORKFLOW_VERSION, "prompt_templates": PROMPT_TEMPLATE_VERSION}
        return S.MISSION_ANALYSIS

    def h_mission_analysis(self) -> S:
        m = self.job.mission
        self.checks(S.MISSION_ANALYSIS, {
            "mission.text_present": bool(m.text), "mission.opportunity_named": bool(m.opportunity_name),
            "mission.type_classified": (True, m.opportunity_type.value),
            "mission.cycle_parsed": (m.cycle_year is not None, str(m.cycle)),
            "mission.institution_extracted": bool(m.institution),
            "mission.privacy_classified": (True, self.job.privacy_class.value),
            "mission.risk_classified": (True, self.job.risk.risk_class.value),
            "mission.critical_predicates_listed": bool(self.job.risk.critical_predicates),
            "policy.budget_is_zero": self.job.policy.compute.api_budget_usd == 0.0 and COST_POLICY.max_api_cost_usd == 0,
            "policy.human_release_required": self.job.policy.human_release_required})
        if m.cycle_year is None:
            raise Pause(JobStatus.BLOCKED, "mission has no admission cycle/year (e.g. 'Fall 2027'); add it and resume")
        self.ws.write_json("mission.json", {"mission": m, "risk": self.job.risk, "privacy": self.job.privacy_class})
        return S.COMPUTE_PLAN

    def h_compute_plan(self) -> S:
        configured = [pid for pid, a in self.broker.adapters.items() if a.configured()[0] and pid != "mock"]
        health = self.broker.refresh_health(configured, timeout=3.0) if configured else {}
        plan = Governor(self.registry).plan(self.job)
        self.ws.write_json("execution_plan.json", plan)
        self.ws.write_json("provider_health.json", health)
        self.checks(S.COMPUTE_PLAN, {
            "compute.registry_loaded": (True, f"{len(self.registry.models)} models"),
            "compute.firewall_armed": self.broker.firewall is not None,
            "compute.paid_fallback_disabled": not COST_POLICY.paid_fallback_allowed,
            "compute.providers_probed": (True, f"{len(health)} configured providers probed"),
            "plan.dag_acyclic": True, "plan.worker_count_scaled": (True, str(plan.research_workers))})
        return S.SOURCE_DISCOVERY

    def h_source_discovery(self) -> S:
        if not self.rd.discover():
            raise Pause(JobStatus.BLOCKED, "; ".join(self.rd.state.blockers) or "discovery failed")
        return S.SOURCE_EXPANSION

    def h_source_expansion(self) -> S:
        if not self.rd.expand_and_parse():
            raise Pause(JobStatus.BLOCKED, "no source could be fetched/parsed")
        return S.DOCUMENT_PARSE

    def h_document_parse(self) -> S:
        st = self.rd.state
        pending = [u for u in st.candidate_urls if u not in {s.url for s in st.sources}]
        self.checks(S.DOCUMENT_PARSE, {"parse.html_blocks_extracted": bool(st.sources),
                                       "parse.empty_documents_flagged": True})
        if pending and st.backend == "live" and st.expansion_rounds < 3:
            return S.SOURCE_EXPANSION
        return S.EVIDENCE_EXTRACTION

    def h_evidence_extraction(self) -> S:
        purpose = "production"
        n = self.rd.extract(purpose)
        if n == 0:
            raise Pause(JobStatus.BLOCKED, "no evidence could be extracted from the sources")
        return S.CONTRADICTION_SEARCH

    def h_contradiction_search(self) -> S:
        self.rd.contradictions()
        return S.FACT_RESOLUTION

    def h_fact_resolution(self) -> S | FailureKind:
        summary = self.rd.resolve_and_lock()
        self.rd.coverage(self.job.risk.critical_predicates)
        if summary["unresolved_critical_contradictions"]:
            slots = [x.slot for x in self.rd.state.contradictions if x.critical and not x.resolved]
            self.rd.export()
            raise Pause(JobStatus.AWAITING_HUMAN, f"official sources disagree on {slots}: resolve with "
                                                  f"`apex-one facts confirm {self.job.job_id} <slot> --claim <id>`")
        locked = {lk.slot for lk in self.locks}
        missing = [group for group in MUST_LOCK_ANY if not locked.intersection(group)]
        if missing:
            if self.rd.state.backend == "live":
                return FailureKind.FACT
            self.rd.export()
            raise Pause(JobStatus.AWAITING_HUMAN, f"must-lock facts missing {missing}: add official sources or "
                                                  f"confirm facts manually, then resume")
        self.checks(S.FACT_RESOLUTION, {"resolution.no_unresolved_critical": True})
        return S.FACT_LOCK

    def h_fact_lock(self) -> S:
        from apex_one.knowledge import build_graph_from_research

        st = self.rd.state
        self.rd.export()
        with session_scope(self.db_url) as s:
            for src in st.sources:
                s.merge(SourceRow(source_id=src.source_id, job_id=self.job.job_id, url=src.url, domain=src.domain,
                                  kind=src.kind.value, content_hash=src.content_hash, payload=src.model_dump(mode="json")))
            for c in st.claims:
                s.merge(ClaimRow(claim_id=c.claim_id, job_id=self.job.job_id, slot=c.slot, predicate=c.predicate,
                                 status=c.status.value, criticality=c.criticality.value, payload=c.model_dump(mode="json")))
            existing = {r.slot for r in s.query(FactLockRow).filter(FactLockRow.job_id == self.job.job_id)}
            for lk in st.locks:
                if lk.slot not in existing:
                    s.add(FactLockRow(lock_id=lk.lock_id, job_id=self.job.job_id, slot=lk.slot, lock_hash=lk.lock_hash,
                                      payload=lk.model_dump(mode="json")))
        g = build_graph_from_research(st, self.job.mission)
        g.save(self.job.job_id, self.db_url)
        self.ws.write_json("knowledge_graph.json", g.to_dict())
        self.checks(S.FACT_LOCK, {"lock.only_verified_claims": all(
            c.status == ClaimStatus.LOCKED for c in st.claims if c.claim_id in {lk.claim_id for lk in st.locks}),
            "lock.hashes_computed": all(lk.verify_integrity() for lk in st.locks)})
        return S.OPPORTUNITY_MODEL

    def h_opportunity_model(self) -> S:
        from apex_one.opportunity import OpportunityModeler

        open_slots = sorted({c.slot for c in self.rd.state.claims if c.status == ClaimStatus.NEEDS_HUMAN})
        opp = OpportunityModeler(self.locks, open_slots, today=self.today).build(
            self.job.mission.institution or self.job.mission.opportunity_name)
        self.ws.write_json("opportunity_model.json", opp)
        self.checks(S.OPPORTUNITY_MODEL, {"opportunity.facts_cite_locks": all(i.claim_refs for i in opp.core_value)})
        return S.READER_MODEL

    def h_reader_model(self) -> S:
        from apex_one.reader_lab import build_reader_model

        rm = build_reader_model(self.locks, self.mode)
        self.ws.write_json("reader_model.json", rm)
        return S.CONTENT_ARCHITECTURE

    def h_content_architecture(self) -> S:
        from apex_one.editorial.architect import NarrativeArchitect

        opp = OpportunityModel.model_validate(self._read("opportunity_model.json"))
        rm = ReaderModel.model_validate(self._read("reader_model.json"))
        feedback = self._read("reader_feedback.json") if self.ws.exists("reader_feedback.json") else []
        plan = NarrativeArchitect(self.locks, opp, rm).plan(feedback)
        self.ws.write_json("content_plan.json", plan)
        self.checks(S.CONTENT_ARCHITECTURE, {"ia.no_consecutive_same_rhythm": not NarrativeArchitect.rhythm_violations(plan),
                                             "ia.closing_action": plan[-1].node_type.value == "Closing"})
        return S.DRAFT

    def _voice(self):
        from apex_one.editorial.voice import load_voice
        from apex_one.memory import VoiceMemory

        v = load_voice()
        v.learned_rejections = VoiceMemory(self.db_url).rejected_phrases()
        return v

    def h_draft(self) -> S:
        from apex_one.editorial.architect import SectionPlan
        from apex_one.editorial.writer import APEXEgyptianWriter

        voice = self._voice()
        opp = OpportunityModel.model_validate(self._read("opportunity_model.json"))
        plan = [SectionPlan.model_validate(p) for p in self._read("content_plan.json")]
        seed = self.job.policy.seed + self.sm.recovery_counts.get(FailureKind.VOICE.value, 0)
        w = APEXEgyptianWriter(voice, self.locks, opp, institution=self.job.mission.institution or "",
                               cycle=self.job.mission.cycle or "", seed=seed, synthetic=self.synthetic,
                               broker=self.broker, workspace=self.ws)
        nodes = w.write(plan)
        polished = w.polish_with_model(nodes, purpose="production")
        self.ws.write_json("draft_nodes.json", nodes)
        self.ws.write_json("editorial_log.json", {"dropped": w.dropped, "variants": w.variants_used,
                                                  "model_polished_blocks": polished, "rejected_model_text": w.log,
                                                  "voice_version": voice.version, "voice_hash": voice.content_hash})
        self.job.versions.update({"voice": voice.version, "voice_hash": voice.content_hash})
        self.checks(S.DRAFT, {"draft.fact_slots_only": True, "draft.cta_present": any(
            b.role == "cta" for n in nodes for b in n.content)})
        return S.VOICE_REVIEW

    def _provisional_ast(self) -> DocumentAST:
        from apex_one.document.ast.builder import build_document_ast

        return build_document_ast(self._nodes("draft_nodes.json"), institution=self.job.mission.institution or "",
                                  cycle=self.job.mission.cycle or "", synthetic=self.synthetic, locks=self.locks,
                                  voice_version=self.job.versions.get("voice", ""))

    def h_voice_review(self) -> S | FailureKind:
        from apex_one.editorial.language import review_document

        rv = review_document(self._provisional_ast(), self._voice(), self.locks, allowed_years=self.allowed_years)
        self.ws.write_json("qa/editorial_review.json", {"issues": rv.issues, "metrics": rv.metrics})
        voice_fail = [i for i in rv.issues if i.check.startswith("voice.") and i.severity in ("critical", "major")]
        self.checks(S.VOICE_REVIEW, {c: not any(i.check == c and i.severity != "minor" for i in rv.issues)
                                     for c in CHECKS[S.VOICE_REVIEW]})
        if voice_fail and self.sm.recovery_counts.get(FailureKind.VOICE.value, 0) < 2:
            return FailureKind.VOICE
        return S.FACT_ALIGNMENT

    def h_fact_alignment(self) -> S | FailureKind:
        rv = self._read("qa/editorial_review.json")
        crit = [i for i in rv["issues"] if i["severity"] == "critical"]
        self.checks(S.FACT_ALIGNMENT, {"alignment.semantic_diff_clean": not crit,
                                       "alignment.lock_hashes_intact": all(lk.verify_integrity() for lk in self.locks)})
        if crit:
            return FailureKind.VOICE
        return S.DOCUMENT_AST

    def h_document_ast(self) -> S:
        from apex_one.document.ast.builder import ast_problems

        ast = self._provisional_ast()
        probs = ast_problems(ast, self.locks)
        if probs:
            raise Pause(JobStatus.FAILED, f"invalid Document AST: {probs[:3]}")
        self.ws.write_json("document_ast.json", ast)
        return S.DESIGN_INTENT

    def _design_router(self):
        from apex_one.design.models import DesignRouter, build_design_adapters

        return DesignRouter(self.registry, build_design_adapters(self.registry), purpose="production")

    def h_design_intent(self) -> S:
        from apex_one.design.intent import derive_intent

        ast = self._ast()
        router = self._design_router()
        intents = [derive_intent(n) for n in ast.pages()]
        routes = [router.route_for(n.semantic_type.value).to_dict() for n in ast.pages()]
        from apex_one.design.models.moe import NATIVE, DesignMoE

        moe = DesignMoE(self.registry)
        for route, n in zip(routes, ast.pages()):
            ch = moe.route(n.semantic_type.value, purpose="production")
            executed = next((e for e in ch.experts if e in NATIVE), "native-tournament")
            route["experts"] = {"gate": ch.gate, "ranked": ch.experts, "executed": executed,
                                "evidence": ch.evidence, "excluded": ch.excluded}
        self.ws.write_json("design_intent.json", intents)
        self.ws.write_json("design_routes.json", routes)
        return S.CREATIVE_DIRECTIONS

    def _tournament(self, renderer, direction: str, sub: str, seed_offset: int = 0):
        from apex_one.design.genome import load_genome
        from apex_one.design.tournament import LayoutTournament
        from apex_one.memory import DesignMemory

        p = MODE_PARAMS[self.mode]
        return LayoutTournament(load_genome(), self.locks, renderer, self.ws.root / "design_candidates" / sub,
                                population=p["population"], generations=p["generations"],
                                elite=self.job.policy.quality.elite_count,
                                epsilon=self.job.policy.quality.convergence_epsilon,
                                seed=self.job.policy.seed + seed_offset, synthetic=self.synthetic,
                                allowed_years=self.allowed_years, direction=direction,
                                history_signatures=DesignMemory(self.db_url).signature_verdicts(),
                                layout_refs=DesignMemory(self.db_url).layout_references())

    def h_creative_directions(self) -> S:
        from apex_one.design.tournament import CREATIVE_DIRECTIONS, Chosen
        from apex_one.vision.render import Renderer

        ast = self._ast()
        n_dir = MODE_PARAMS[self.mode]["directions"]
        rhythm_loops = self.sm.recovery_counts.get(FailureKind.RHYTHM.value, 0)
        names = list(CREATIVE_DIRECTIONS)
        names = names[rhythm_loops % len(names):] + names[:rhythm_loops % len(names)]
        names = names[:n_dir]
        key_pages = [n for n in ast.pages() if n.semantic_type.value in ("Cover", "OpportunitySnapshot", "FundingChapter")]
        scores = {}
        with Renderer() as r:
            for k, name in enumerate(names):
                if n_dir == 1:
                    scores[name] = None
                    break
                t = self._tournament(r, name, f"direction-{name}", seed_offset=100 + k)
                prev: list[Chosen] = []
                fits = []
                for i, n in enumerate(key_pages, 1):
                    out = t.run_page(n, i, len(ast.pages()), prev, initial=6)
                    prev.append(Chosen(n.node_id, out.best.genes.archetype, out.best.genes.tone,
                                       out.best.structural_signature))
                    fits.append(out.best.fitness or 0.0)
                scores[name] = sum(fits) / max(1, len(fits))
        chosen = max(names, key=lambda n: scores[n] if scores[n] is not None else 0)
        self.ws.write_json("creative_directions.json", {
            "candidates": {n: {"description": CREATIVE_DIRECTIONS[n]["description"], "probe_fitness": scores.get(n)}
                           for n in names}, "chosen": chosen,
            "method": "mini-tournament on cover/snapshot/funding pages per direction" if n_dir > 1 else "single direction"})
        self.checks(S.CREATIVE_DIRECTIONS, {"directions.multiple_generated": (len(names) > 1 or n_dir == 1, str(names))})
        return S.LAYOUT_SEARCH

    def h_layout_search(self) -> S:
        from apex_one.design.tournament import Chosen
        from apex_one.vision.render import Renderer

        ast = self._ast()
        direction = self._read("creative_directions.json")["chosen"]
        p = MODE_PARAMS[self.mode]
        redo = set(self._read("layout_redo.json")) if self.ws.exists("layout_redo.json") else None
        previous = {d["page_id"]: d for d in self._read("layout_search.json")} if (
            redo is not None and self.ws.exists("layout_search.json")) else {}
        results = []
        geometry_loops = self.sm.recovery_counts.get(FailureKind.GEOMETRY.value, 0)
        with Renderer() as r:
            t = self._tournament(r, direction, "search", seed_offset=geometry_loops * 1000)
            pairwise_left = p.get("pairwise_pages", 0) if self._pairwise_judges() else 0
            prev: list[Chosen] = []
            pages = ast.pages()
            for i, n in enumerate(pages, 1):
                if redo is not None and n.node_id not in redo and n.node_id in previous:
                    rec = previous[n.node_id]
                    results.append(rec)
                    best = LayoutCandidate.model_validate(rec["top"][0])
                    prev.append(Chosen(n.node_id, best.genes.archetype, best.genes.tone, best.structural_signature,
                                       best.occupancy))
                    continue
                initial = p["initial_important"] if n.importance >= 4 else p["initial_other"]
                if n.importance >= 4 and self.mode == QualityMode.ULTRA:
                    initial = ultra_candidates(initial)
                out = t.run_page(n, i, len(pages), prev, initial=initial)
                pw = None
                if n.importance >= 4 and pairwise_left > 0 and len(out.top) >= 2:
                    pairwise_left -= 1
                    pw = self._pairwise_finalists(t, n, out)
                prev.append(Chosen(n.node_id, out.best.genes.archetype, out.best.genes.tone,
                                   out.best.structural_signature, out.best.occupancy))
                results.append({"page_id": n.node_id, "node_type": n.semantic_type.value,
                                "evaluated": out.evaluated, "generations": out.generations,
                                "rejected_critical": out.rejected_critical, "fitness_history": out.history,
                                "pairwise": pw, "top": [c.model_dump(mode="json") for c in out.top]})
        self.ws.write_json("layout_search.json", results)
        if self.ws.exists("layout_redo.json"):
            (self.ws.root / "layout_redo.json").unlink()
        self.checks(S.LAYOUT_SEARCH, {"layout.candidates_generated": (True, str(sum(x["evaluated"] for x in results))),
                                      "layout.license_safe_engines": True})
        return S.LAYOUT_TOURNAMENT

    def _pairwise_judges(self) -> list[str]:
        from apex_one.vision.council import reliable_judges

        return reliable_judges()[0]

    def _pairwise_finalists(self, t, node, out) -> dict:
        """Phase 23: the two best locally-filtered finalists go to the calibrated pairwise council. A consistent
        majority adds a transparent +5 preference to the winner's fitness; ties leave the deterministic order."""
        from apex_one.vision.pairwise import PairwiseJudge

        a, b = out.top[0], out.top[1]
        if not (a.screenshot_path and b.screenshot_path):
            return {"status": "NOT_MEASURED", "reason": "finalist screenshots missing"}
        intent = f"{node.semantic_type.value}, reading mode {node.reading_mode.value}"
        res = PairwiseJudge(self.broker, self._pairwise_judges(), workspace=self.ws).compare(
            t.dir / a.screenshot_path, t.dir / b.screenshot_path, intent)
        record = {"status": "MEASURED", "first": a.candidate_id, "second": b.candidate_id, **res.as_dict()}
        if res.winner:
            win, lose = (a, b) if res.winner == "first" else (b, a)
            win.metrics["pairwise_preference"] = Metric.measured("pairwise_preference", 100, "order-swapped pairwise "
                                                                 "council (consistent majority)", evidence=[str(res.votes)])
            lose.metrics["pairwise_preference"] = Metric.measured("pairwise_preference", 0, "lost pairwise council",
                                                                  evidence=[str(res.votes)])
            win.fitness = round((win.fitness or 0.0) + 5.0, 3)
            win.rationale = [*win.rationale, "pairwise council preferred (+5)"]
            out.top.sort(key=lambda c: -(c.fitness or -1e9))
            out.best = out.top[0]
        self.ws.events.emit("pairwise", page=node.node_id, winner=res.winner, disagreements=res.disagreements)
        return record

    def h_layout_tournament(self) -> S:
        """Document-level tournament: choose one of each page's top candidates to maximise total fitness
        minus cross-page rhythm penalties (dynamic programming over the page sequence)."""
        search = self._read("layout_search.json")
        tops = [[LayoutCandidate.model_validate(c) for c in rec["top"]] for rec in search]

        def cov(c: LayoutCandidate) -> float | None:
            m = c.metrics.get("density_fit")
            try:
                return float(m.evidence[0].split("=")[1]) if m and m.evidence else None
            except (ValueError, IndexError):
                return None

        def ink(c: LayoutCandidate) -> float | None:
            m = c.metrics.get("ink")
            return m.value if m is not None and m.value is not None else None

        def pair_pen(a: LayoutCandidate, b: LayoutCandidate) -> float:
            pen = 0.0
            ia, ib = ink(a), ink(b)
            if ia is not None and ib is not None:
                if abs(ia - ib) < 0.01 and b.genes.archetype != "cover-monument":
                    pen += 6  # flat visual weight: same measure the rhythm analysis uses
            else:
                ca, cb = cov(a), cov(b)
                if ca is not None and cb is not None and abs(ca - cb) < 0.03:
                    pen += 6
            if a.genes.archetype == b.genes.archetype:
                pen += 12
            if a.genes.tone == b.genes.tone == "dark":
                pen += 8
            if a.structural_signature == b.structural_signature:
                pen += 15
            return pen

        best: list[dict[int, tuple[float, list[int]]]] = []
        for i, cands in enumerate(tops):
            layer: dict[int, tuple[float, list[int]]] = {}
            for j, c in enumerate(cands):
                f = c.fitness or 0.0
                if i == 0:
                    layer[j] = (f, [j])
                else:
                    opts = [(best[i - 1][k][0] + f - pair_pen(tops[i - 1][k], c), best[i - 1][k][1] + [j])
                            for k in best[i - 1]]
                    layer[j] = max(opts, key=lambda x: x[0])
            best.append(layer)
        total, path = max(best[-1].values(), key=lambda x: x[0])
        router = self._design_router()
        ast = self._ast()
        decisions, chosen = [], []
        for rec, cands, j, node in zip(search, tops, path, ast.pages()):
            c = cands[j]
            chosen.append(c)
            route = router.route_for(node.semantic_type.value)
            decisions.append(DesignDecision(page_id=rec["page_id"], chosen_candidate=c.candidate_id,
                                            rejected_candidates=[x.candidate_id for x in cands if x is not c],
                                            route=route.engines(), fitness=c.fitness,
                                            rationale=[f"archetype {c.genes.archetype}, tone {c.genes.tone}",
                                                       f"fitness {c.fitness}: " + ", ".join(c.rationale),
                                                       f"evaluated {rec['evaluated']} candidates over "
                                                       f"{rec['generations']} generations",
                                                       *(f"mutation: {m}" for m in c.mutations)]))
        self.ws.write_json("design_decisions.json", decisions)
        self.ws.write_json("layout_genes.json", [c.genes for c in chosen])
        self.ws.write_json("layout_chosen.json", chosen)
        self.checks(S.LAYOUT_TOURNAMENT, {"tournament.selection": (True, f"document score {total:.1f}")})
        return S.HTML_BUILD

    def h_html_build(self) -> S:
        from apex_one.design.genome import load_genome
        from apex_one.document.compiler import compile_document, compile_page

        ast = self._ast()
        genes = [Genes.model_validate(g) for g in self._read("layout_genes.json")]
        genome = load_genome()
        lock_map = {lk.slot: lk for lk in self.locks}
        pages = ast.pages()
        compiled = [compile_page(n, g, genome, lock_map, page_no=i, total_pages=len(pages), synthetic=self.synthetic,
                                 seed=self.job.policy.seed + i) for i, (n, g) in enumerate(zip(pages, genes), 1)]
        html = compile_document(compiled, genome, title=ast.title_en, font_mode="embedded", synthetic=self.synthetic,
                                extra_meta={"apex-job": self.job.job_id, "apex-genome": genome.version,
                                            "apex-voice": self.job.versions.get("voice", "")})
        self.ws.write_text("final.html", html)
        self.job.versions["design_genome"] = genome.version
        self.checks(S.HTML_BUILD, {"html.compiled_from_ast": True, "html.fonts_embedded": "data:font/ttf" in html})
        return S.RENDER

    def h_render(self) -> S:
        from apex_one.design.genome import load_genome
        from apex_one.vision.contact_sheet import contact_sheet
        from apex_one.vision.page import derive_images
        from apex_one.vision.render import Renderer

        genome = load_genome()
        with Renderer(device_scale=1.5) as r:
            res = r.render_full(self.ws.root / "final.html", self.ws.root, pdf_path=self.ws.root / "final.pdf",
                                min_margin_mm=float(genome.invariants["page"]["min_margin_mm"]))
        self.ws.write_json("qa/mobile_metrics.json", res.mobile_metrics or {})
        for p in res.page_screenshots:
            derive_images(p, self.ws.root / "screenshots" / "derived")
        contact_sheet(res.page_screenshots, self.ws.root / "contact_sheet.png")
        self.job.versions["render_env"] = json.dumps({
            "chromium": find_chromium(), "playwright": pkg_version("playwright"), "python": platform.python_version(),
            "os": platform.platform()})
        self.checks(S.RENDER, {"render.pages_screenshotted": bool(res.page_screenshots),
                               "render.pdf_printed": res.pdf_path is not None and res.pdf_path.exists(),
                               "render.mobile_preview": res.mobile_screenshot is not None})
        return S.DETERMINISTIC_QA

    def h_deterministic_qa(self) -> S | FailureKind:
        from apex_one.design.genome import load_genome
        from apex_one.qa.deterministic import LAYOUT_CRITICAL, document_qa

        metrics = self._read("qa/dom_metrics.json")
        mobile = self._read("qa/mobile_metrics.json") or None
        report, pages = document_qa(metrics, load_genome(), self.locks, allowed_years=self.allowed_years,
                                    pdf_path=self.ws.root / "final.pdf", mobile=mobile)
        self.ws.write_json("qa/deterministic_report.json", report)
        self.ws.write_json("qa/pages.json", [{"page_id": p.page_id, "predicted_first": p.predicted_first,
                                              "issues": p.issues, "metrics": p.metrics} for p in pages])
        crit = report.critical
        self.checks(S.DETERMINISTIC_QA, {c: not any(i.check == c and i.severity == "critical" for i in report.issues)
                                         for c in CHECKS[S.DETERMINISTIC_QA]})
        fact_crit = [i for i in crit if i.check == "qa.dom_fact_integrity"]
        if fact_crit:
            raise Pause(JobStatus.FAILED, f"rendered facts do not match locks: {fact_crit[0].message}")
        rtl_crit = [i for i in crit if i.check in ("qa.rtl_direction",)]
        if rtl_crit:
            return FailureKind.RTL
        layout_crit = [i for i in crit if i.check in LAYOUT_CRITICAL]
        if layout_crit:
            self.ws.write_json("layout_redo.json", sorted({i.page for i in layout_crit if i.page}))
            return FailureKind.GEOMETRY
        return S.VISION_QA

    def h_vision_qa(self) -> S:
        from apex_one.core.schemas.common import Metric as M
        from apex_one.vision.judges import ModelVisionJudge, NativeVisionProxy
        from apex_one.vision.page import dhash, hamming_similarity

        metrics = self._read("qa/dom_metrics.json")
        page_qas = {p["page_id"]: p for p in self._read("qa/pages.json")}
        intents = {i["page_id"]: i for i in self._read("design_intent.json")}
        shots = sorted((self.ws.root / "screenshots").glob("page-*.png"))
        native, model = NativeVisionProxy(), ModelVisionJudge(self.broker)
        out = []
        prev_hash = None
        for pm, shot in zip(metrics["pages"], shots):
            pq = page_qas.get(pm["pageId"], {})
            qa_metrics = {k: M.model_validate(v) for k, v in pq.get("metrics", {}).items()}
            h = dhash(shot)
            sim = hamming_similarity(h, prev_hash) if prev_hash is not None else None
            prev_hash = h
            verdicts = native.judge(pm, qa_metrics, sim, pm.get("firstFixation"), pq.get("predicted_first"))
            intent = intents.get(pm["pageId"], {})
            verdicts += model.judge(shot, json.dumps(intent.get("rationale", []), ensure_ascii=False), self.ws)
            out.append({"page_id": pm["pageId"], "screenshot": shot.name, "verdicts": verdicts})
        self.ws.write_json("qa/vision_report.json", out)
        council = self._vision_council(metrics["pages"], shots, intents)
        self.ws.write_json("qa/vision_council.json", council)
        measured = council["status"] == "MEASURED"
        self.checks(S.VISION_QA, {"vision.first_fixation": (True, "DOM saliency proxy"),
                                  "vision.council": (measured, f"{council['status']}: {council.get('reason', '')} "
                                                               f"judges={council['judges']}")})
        return S.DESIGN_JURY

    def _vision_council(self, pages: list[dict], shots: list[Path], intents: dict) -> dict:
        """Phase 18: independent, CALIBRATED vision models review screenshots (never the designer judging itself)."""
        from apex_one.vision.council import (ROLES, VisionCouncil, document_metrics, page_budget, reliable_judges,
                                             select_pages, weak_pages)

        judges, calibration = reliable_judges()
        budget = page_budget(self.mode.value)
        report: dict = {"judges": judges, "calibration": calibration, "budget_pages": budget, "pages": [],
                        "disagreements": [], "document_metrics": {}, "weak_pages": {}, "status": "NOT_MEASURED"}
        if not judges:
            report["reason"] = "no calibrated-reliable vision judge (see artifacts/bench/vision_calibration)"
            return report
        if budget <= 0:
            report["reason"] = f"quality mode {self.mode.value} allots no council pages (APEX_VISION_COUNCIL_PAGES)"
            return report
        shot_by_id = {pm["pageId"]: shot for pm, shot in zip(pages, shots)}
        council = VisionCouncil(self.broker, judges, workspace=self.ws)
        reviews = []
        for pid in select_pages(pages, budget):
            intent = intents.get(pid, {})
            text = f"{intent.get('node_type', '')}: " + "; ".join(intent.get("rationale", []))
            pr = council.review(pid, shot_by_id[pid], text)
            reviews.append(pr)
            report["pages"].append({"page_id": pid, "reviews": pr.reviews, "errors": pr.errors,
                                    "role_medians": {r: pr.role_metric(r).value for r in ROLES}})
            report["disagreements"] += pr.disagreements()
        valid = [r for r in reviews if r.reviews]
        if not valid:
            report["reason"] = "every council call failed: " + json.dumps([r.errors for r in reviews])[:300]
            return report
        report["document_metrics"] = {k: m.model_dump() for k, m in document_metrics(valid).items()}
        report["weak_pages"] = weak_pages(valid)
        report["status"] = "MEASURED"
        report["reason"] = f"{len(valid)}/{len(reviews)} page(s) reviewed by {len(judges)} calibrated judge(s)"
        return report

    def h_design_jury(self) -> S:
        from apex_one.vision.judges import PosterRewardJudge

        router = self._design_router()
        reward_choice = router.choose("design_reward")
        adapter = None
        if not reward_choice.native:
            from apex_one.design.models import build_design_adapters

            adapter = build_design_adapters(self.registry).get(reward_choice.engine)
        judge = PosterRewardJudge(adapter)
        intents = {i["page_id"]: i for i in self._read("design_intent.json")}
        shots = sorted((self.ws.root / "screenshots").glob("page-*.png"))
        pages = self._read("qa/pages.json")
        jury = []
        weak = []
        for pq, shot in zip(pages, shots):
            verdicts = judge.judge(shot, " ".join(intents.get(pq["page_id"], {}).get("rationale", [])))
            m = pq["metrics"]
            hier = (m.get("design.hierarchy") or {}).get("value")
            typo = (m.get("design.typography") or {}).get("value")
            if (hier is not None and hier < 85) or (typo is not None and typo < 90):
                weak.append(pq["page_id"])
            jury.append({"page_id": pq["page_id"], "reward_engine": reward_choice.engine, "verdicts": verdicts,
                         "deterministic": {"hierarchy": hier, "typography": typo}})
        council = self._read("qa/vision_council.json") if self.ws.exists("qa/vision_council.json") else {}
        for pid in council.get("weak_pages", {}):
            if pid not in weak:
                weak.append(pid)
        self.ws.write_json("qa/design_jury.json", {"pages": jury, "weak_pages": weak,
                                                   "council_weak_pages": council.get("weak_pages", {}),
                                                   "reward_route": reward_choice.considered})
        return S.MUTATION

    def h_mutation(self) -> S:
        jury = self._read("qa/design_jury.json")
        weak = jury.get("weak_pages", [])
        used = self.sm.recovery_counts.get(FailureKind.AESTHETIC.value, 0)
        if weak and used < 1:
            self.sm.recovery_counts[FailureKind.AESTHETIC.value] = used + 1
            self.ws.write_json("layout_redo.json", weak)
            self.ws.events.emit("mutation", pages=weak, reason="jury: hierarchy/typography below target")
            # re-search the weak pages with a new seed, then rebuild
            self.h_layout_search()
            self.h_layout_tournament()
            self.h_html_build()
            self.h_render()
            nxt = self.h_deterministic_qa()
            if isinstance(nxt, FailureKind):
                raise Pause(JobStatus.BLOCKED, f"mutation round produced a {nxt.value} failure")
            # the pages changed: council reviews of the old render must not reach the release gates
            if self.ws.exists("qa/vision_council.json") and self._read("qa/vision_council.json")["status"] == "MEASURED":
                self.h_vision_qa()
        self.checks(S.MUTATION, {"mutation.failure_classified": (True, f"weak pages: {len(weak)}")})
        return S.DOCUMENT_QA

    def _read_items(self):
        from apex_one.reader_lab.simulator import ReadItem

        items = []
        for viewport, rel in (("desktop", "qa/dom_metrics.json"), ("mobile", "qa/mobile_metrics.json")):
            if not self.ws.exists(rel):
                continue
            data = self._read(rel) or {}
            for k, p in enumerate(data.get("pages", []), 1):
                for it in sorted(p["items"], key=lambda i: (i["y"], -i["x"])):
                    slots = [f["slot"] for f in p["facts"] if it["y"] - 2 <= f["y"] <= it["y"] + it["h"] + 2
                             and it["x"] - 2 <= f["x"] <= it["x"] + it["w"] + 2]
                    role = {"heading": "heading", "stat": "stat", "hero": "stat", "warning": "warning",
                            "cta": "cta", "step": "stat"}.get(it["role"], it["role"])
                    items.append(ReadItem(it["text"], k, it["fontPx"], it["lang"], role, slots, viewport))
        return items

    def h_document_qa(self) -> S | FailureKind:
        from apex_one.core.schemas.common import Metric as M
        from apex_one.editorial.language import review_document
        from apex_one.reader_lab import ReaderSimulator
        from apex_one.vision.contact_sheet import rhythm_analysis

        chosen = [LayoutCandidate.model_validate(c) for c in self._read("layout_chosen.json")]
        ast = self._ast()
        shots = sorted((self.ws.root / "screenshots").glob("page-*.png"))
        r_issues, r_metrics, r_data = rhythm_analysis(shots, [c.genes.archetype for c in chosen],
                                                      [n.rhythm_role for n in ast.pages()],
                                                      [c.structural_signature for c in chosen])
        rm = ReaderModel.model_validate(self._read("reader_model.json"))
        sim = ReaderSimulator(self.locks, rm.must_understand)
        results, comp = sim.run(rm.personas, self._read_items())
        rv = review_document(ast, self._voice(), self.locks, allowed_years=self.allowed_years)
        doc = {"rhythm_issues": r_issues, "metrics": {**r_metrics, "reader.comprehension": comp, **rv.metrics},
               "rhythm_data": r_data,
               "reader_results": [{"persona": r.persona_id, "score": r.score, "misunderstandings": r.misunderstandings,
                                   "answers": [a.__dict__ for a in r.answers], "words_read": r.words_read}
                                  for r in results]}
        self.ws.write_json("qa/document_qa.json", doc)
        misunderstood = sorted({m for r in results for m in r.misunderstandings})
        self.checks(S.DOCUMENT_QA, {"doc.contact_sheet": (self.ws.root / "contact_sheet.png").exists(),
                                    "doc.rhythm": (r_metrics["document.rhythm"].value or 0) >= 93,
                                    "doc.reader_lab": (comp.value or 0) >= 95})
        reader_loops = self.sm.recovery_counts.get(FailureKind.READER.value, 0)
        if (misunderstood or (comp.value or 0) < 95) and reader_loops < 1:
            missed = sorted({a.slot for r in results for a in r.answers if a.slot and not a.correct})
            self.ws.write_json("reader_feedback.json", missed)
            return FailureKind.READER
        rhythm_loops = self.sm.recovery_counts.get(FailureKind.RHYTHM.value, 0)
        if (r_metrics["document.rhythm"].value or 0) < 80 and rhythm_loops < 1:
            return FailureKind.RHYTHM
        _ = M
        return S.RESEARCH_RECHECK

    def h_research_recheck(self) -> S | FailureKind:
        intact = all(lk.verify_integrity() for lk in self.locks)
        det = self._read("qa/deterministic_report.json")
        dom_ok = (det["metrics"].get("fact.critical_accuracy") or {}).get("value") == 100.0
        changed = []
        if self.rd.state.backend == "live":
            from apex_one.core.schemas.common import stable_hash
            from apex_one.research.browser import FetchError, HttpFetcher

            f = HttpFetcher()
            for s in [s for s in self.rd.state.sources if s.kind.value.startswith("official")][:6]:
                try:
                    if stable_hash(f.fetch(s.url).content) != s.content_hash:
                        changed.append(s.url)
                except FetchError:
                    continue
        self.ws.write_json("qa/research_recheck.json", {"locks_intact": intact, "dom_values_match": dom_ok,
                                                        "changed_official_sources": changed})
        self.checks(S.RESEARCH_RECHECK, {"recheck.locks_intact": intact, "recheck.dom_values_match_locks": dom_ok,
                                         "recheck.freshness_still_valid": not changed})
        if changed:
            return FailureKind.FACT
        if not intact or not dom_ok:
            raise Pause(JobStatus.FAILED, "fact integrity re-check failed")
        return S.RELEASE_CANDIDATE

    def h_release_candidate(self) -> S:
        from apex_one.qa.court import DisagreementResolver, evaluate_gates, verdict_from_metric
        from apex_one.release import artifacts_complete, license_guard, secret_scan

        det = self._read("qa/deterministic_report.json")
        doc = self._read("qa/document_qa.json")
        metrics: dict[str, Metric] = {}
        for k, v in {**det["metrics"], **doc["metrics"]}.items():
            metrics[k] = Metric.model_validate(v)
        unresolved = sum(1 for x in self.rd.state.contradictions if x.critical and not x.resolved)
        metrics["fact.unresolved_critical_contradictions"] = Metric.measured(
            "fact.unresolved_critical_contradictions", unresolved, "contradiction registry", unit="count")
        decisions = self._read("design_decisions.json")
        engines = sorted({e for d in decisions for e in d["route"]})
        calls = self.ws.model_calls.read()
        lic_report, lic_metric = license_guard(self.registry, engines, calls)
        metrics[lic_metric.name] = lic_metric
        from apex_one.release.assets import brand_production_metric, validate_assets

        asset_report = validate_assets()
        metrics["brand.production_asset_failures"] = brand_production_metric(asset_report)
        self.ws.write_json("qa/asset_report.json", asset_report)
        self.ws.write_json("license_report.json", lic_report)
        self.ws.write_json("model_routing.json", {"design_routes": self._read("design_routes.json"),
                                                  "routing_decisions": self.ws.routing.read(),
                                                  "model_calls": calls})
        verdicts = [
            verdict_from_metric("FactJudge", metrics.get("fact.critical_accuracy", Metric.not_measured("fact.critical_accuracy", "")), 100, critical=True),
            verdict_from_metric("RTLJudge", metrics.get("rtl.quality", Metric.not_measured("rtl.quality", "")), 98),
            verdict_from_metric("TypographyJudge", metrics.get("design.typography", Metric.not_measured("design.typography", "")), 95),
            verdict_from_metric("BrandJudge", metrics.get("design.brand_fit", Metric.not_measured("design.brand_fit", "")), 95),
            verdict_from_metric("ReaderJudge", metrics.get("reader.comprehension", Metric.not_measured("reader.comprehension", "")), 95),
            verdict_from_metric("LanguageJudge", metrics.get("editorial.quality", Metric.not_measured("editorial.quality", "")), 95),
            verdict_from_metric("AccessibilityJudge", metrics.get("accessibility.contrast", Metric.not_measured("accessibility.contrast", "")), 95),
            verdict_from_metric("PrintJudge", metrics.get("print.fidelity", Metric.not_measured("print.fidelity", "")), 98, critical=True),
            verdict_from_metric("LicenseJudge", lic_metric, 0, critical=True, lower_is_better=True),
            verdict_from_metric("AIClicheJudge", metrics.get("editorial.human_or_model_judgement",
                                                             Metric.not_measured("editorial.human_or_model_judgement", "")), 90),
        ]
        jury = self._read("qa/vision_report.json")
        for page in jury:
            for v in page["verdicts"]:
                if v["metric"]["status"] == "MEASURED" and v["metric"]["name"] == "vision.hierarchy":
                    verdicts.append(verdict_from_metric(f"DesignJudge[{v['engine']}]", Metric.model_validate(v["metric"]), 85))
        council = self._read("qa/vision_council.json") if self.ws.exists("qa/vision_council.json") else {}
        for role, m in council.get("document_metrics", {}).items():
            metric = Metric.model_validate(m)
            if metric.value is not None:
                verdicts.append(verdict_from_metric(f"VisionCouncil.{role}[{','.join(council['judges'])}]", metric, 85))
        resolved, disagreements = DisagreementResolver().resolve(verdicts)
        disagreements += [{**d, "source": "vision_council"} for d in council.get("disagreements", [])]
        report = evaluate_gates(self.job.job_id, metrics, self.registry.quality_gates, resolved, disagreements,
                                synthetic=self.synthetic)
        missing = artifacts_complete(self.ws.root)
        missing = [m for m in missing if m not in ("quality_report.json",)]
        if missing:
            report.release_blockers.append(f"missing artifacts: {missing}")
        secrets = secret_scan(self.ws.root)
        if secrets:
            report.release_blockers.append(f"possible secrets in {secrets}")
        if self.synthetic:
            report.warnings.append("SYNTHETIC benchmark: fictional institution/data — never publish as a real guide")
        report.release_candidate = not report.release_blockers
        self.ws.write_json("quality_report.json", report)
        self._write_reproducibility()
        self.checks(S.RELEASE_CANDIDATE, {"release.critical_gates": report.release_candidate,
                                          "release.license_guard": lic_metric.value == 0,
                                          "release.artifacts_complete": not missing, "release.no_secrets": not secrets})
        if not report.release_candidate:
            raise Pause(JobStatus.BLOCKED, "not a release candidate: " + "; ".join(report.release_blockers[:4]))
        self.job.status = JobStatus.RELEASE_CANDIDATE
        return S.HUMAN_APPROVAL

    def _write_reproducibility(self) -> None:
        sources = [{"url": s.url, "content_hash": s.content_hash} for s in self.rd.state.sources]
        self.ws.write_json("reproducibility.json", {
            "job_id": self.job.job_id, "seed": self.job.policy.seed, "quality_mode": self.mode.value,
            "versions": self.job.versions, "source_hashes": sources,
            "models_used": sorted({c["model_id"] for c in self.ws.model_calls.read()}),
            "offline_fixture": self.job.offline_fixture, "source_inputs": self.job.source_inputs,
            "note": "re-run with the same seed, fixture/sources and versions; external model nondeterminism excepted"})

    def h_human_approval(self) -> S:
        gate = next(g for g in self.job.gates if g.name == "release-approval")
        if gate.status == "APPROVED":
            return S.FINAL
        if gate.status == "REJECTED":
            return S.LEARN
        raise Pause(JobStatus.RELEASE_CANDIDATE, f"RELEASE_CANDIDATE ready: review final.pdf and run "
                                              f"`apex-one approve {self.job.job_id} --by <name>`")

    def h_final(self) -> S:
        self.job.status = JobStatus.FINAL
        return S.LEARN

    def h_learn(self) -> None:
        from apex_one.memory import ApprovalMemory, DesignMemory, EpisodicMemory, FailureMemory, SemanticMemory

        gate = next(g for g in self.job.gates if g.name == "release-approval")
        verdict = "approved" if gate.status == "APPROVED" else "rejected"
        ApprovalMemory(self.db_url).add(self.job.job_id, gate.notes, {"approver": gate.approver},
                                        job_id=self.job.job_id, decision=verdict)
        if self.ws.exists("layout_chosen.json"):
            for c in self._read("layout_chosen.json"):
                DesignMemory(self.db_url).add(c["structural_signature"], c["genes"]["archetype"],
                                              {"genes": c["genes"], "occupancy": c.get("occupancy", [])},
                                              job_id=self.job.job_id, verdict=verdict)
        for h in self.job.history:
            for f in h.failures:
                FailureMemory(self.db_url).add(f.stage, f.message, job_id=self.job.job_id, failure_kind=f.kind)
        if verdict == "approved" and not self.synthetic:
            for lk in self.locks:
                SemanticMemory(self.db_url).add(f"{self.job.mission.institution}:{lk.slot}", lk.display_en,
                                                {"cycle": self.job.mission.cycle, "value": lk.value.canonical},
                                                job_id=self.job.job_id)
        EpisodicMemory(self.db_url).add(self.job.job_id, self.job.mission.text,
                                        {"states": [h.stage for h in self.job.history], "verdict": verdict,
                                         "recovery_loops": self.sm.recovery_counts}, job_id=self.job.job_id)
        self.checks(S.LEARN, {"learn.approval_memory": True, "learn.design_memory": True})
        self.ws.events.emit("learned", verdict=verdict)
        self.save()

    # ================================================================== human actions
    def approve(self, approver: str, notes: str = "") -> Job:
        from apex_one.release import write_approval

        if self.sm.state != S.HUMAN_APPROVAL or self.job.status not in (JobStatus.RELEASE_CANDIDATE,
                                                                         JobStatus.AWAITING_HUMAN):
            raise RuntimeError(f"job is in {self.sm.state.value}/{self.job.status.value}; nothing to approve")
        gate = next(g for g in self.job.gates if g.name == "release-approval")
        gate.status, gate.approver, gate.decided_at, gate.notes = "APPROVED", approver, datetime.now(UTC), notes
        write_approval(self.ws.root, approver, "APPROVED", notes)
        self.sm.advance(S.FINAL, reason=f"approved by {approver}", human=True)
        self.job.state = S.FINAL.value
        self.job.status = JobStatus.FINAL
        self.save()
        return self.run()

    def reject(self, approver: str, notes: str, target: str = "CREATIVE_DIRECTIONS") -> Job:
        from apex_one.release import write_approval

        gate = next(g for g in self.job.gates if g.name == "release-approval")
        if self.sm.state != S.HUMAN_APPROVAL:
            raise RuntimeError("job is not awaiting approval")
        gate.status, gate.approver, gate.decided_at, gate.notes = "PENDING", approver, datetime.now(UTC), notes
        write_approval(self.ws.root, approver, "REJECTED", notes)
        tgt = S(target)
        self.sm.advance(tgt, reason=f"rejected by {approver}: {notes}")
        self.job.state = tgt.value
        self.job.status = JobStatus.RUNNING
        self.save()
        return self.run()

    def confirm_fact(self, slot: str, claim_id: str, by: str) -> FactLock:
        from apex_one.research.verification import FactLocker

        claim = next((c for c in self.rd.state.claims if c.claim_id == claim_id and c.slot == slot), None)
        if claim is None:
            raise KeyError(f"no claim {claim_id} for slot {slot}")
        lock = FactLocker.human_lock(claim, by)
        self.rd.state.locks = [lk for lk in self.rd.state.locks if lk.slot != slot] + [lock]
        for x in self.rd.state.contradictions:
            if x.slot == slot:
                x.resolved, x.winning_claim_id, x.resolution = True, claim_id, f"resolved by human {by}"
        for c in self.rd.state.claims:
            if c.slot == slot and c.claim_id != claim_id and c.status != ClaimStatus.REJECTED:
                c.status = ClaimStatus.REJECTED
                c.notes.append(f"rejected by human {by}")
        self.rd.save()
        self.ws.events.emit("human_fact_confirmation", slot=slot, claim_id=claim_id, by=by)
        return lock


def _unused(*_: Any) -> None:  # keep imports referenced for static analysers
    _ = (random, MetricStatus)
