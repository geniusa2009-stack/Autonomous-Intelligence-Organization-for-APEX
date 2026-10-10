"""Design search: candidate generation -> deterministic filter -> scoring -> tournament selection,
elitism, mutation, crossover, stop-on-convergence. Never accept the first output.

Fitness uses only MEASURED metrics. A specialist reward model (PosterReward) contributes only when it
actually ran; otherwise its component is absent, never imputed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apex_one.core.schemas.common import Metric, MetricStatus, Provenance
from apex_one.core.schemas.design import DesignGenome, Genes, LayoutCandidate
from apex_one.core.schemas.document import DocNode
from apex_one.core.schemas.evidence import FactLock
from apex_one.design.genome.genome import sample_genes
from apex_one.design.intent.intent import derive_intent
from apex_one.design.mutation import crossover, mutate, operators_for_weakness
from apex_one.design.repair import repair_genes
from apex_one.document.compiler.compiler import compile_document, compile_page
from apex_one.qa.deterministic import page_qa
from apex_one.vision.render.renderer import Renderer, ensure_fonts

CREATIVE_DIRECTIONS: dict[str, dict[str, Any]] = {
    "quiet-precision": {"description": "light editorial pages, hairline rules, underline-rule numbers",
                        "tone_bias": {"loud": "dark", "story": "light", "breath": "silver"},
                        "number_treatment": "underline-rule", "min_ratio": 1.25, "metaphor": "none"},
    "monumental": {"description": "dark monumental openers, large type scale, mono figures",
                   "tone_bias": {"loud": "dark", "close": "dark"}, "number_treatment": "mono-figure",
                   "min_ratio": 1.333, "metaphor": "grid-lines"},
    "blueprint": {"description": "silver structural tones, blueprint metaphor, outlined hero numbers",
                  "tone_bias": {"loud": "dark", "information": "light", "story": "silver"},
                  "number_treatment": "outlined", "min_ratio": 1.333, "metaphor": "blueprint"},
}

WEIGHTS = {"design.hierarchy": 0.24, "design.typography": 0.18, "design.brand_fit": 0.14, "rtl.quality": 0.10,
           "accessibility.contrast": 0.06, "geometry.alignment": 0.06, "density_fit": 0.14, "novelty": 0.08,
           "specialist_reward": 0.10}


@dataclass
class Chosen:
    page_id: str
    archetype: str
    tone: str
    signature: str
    occupancy: list[int] = field(default_factory=list)


@dataclass
class PageOutcome:
    best: LayoutCandidate
    top: list[LayoutCandidate]
    evaluated: int
    generations: int
    rejected_critical: int
    history: list[float] = field(default_factory=list)
    route: dict = field(default_factory=dict)


class LayoutTournament:
    def __init__(self, genome: DesignGenome, locks: list[FactLock], renderer: Renderer, work_dir: Path, *,
                 population: int, generations: int, elite: int, epsilon: float, seed: int, synthetic: bool,
                 allowed_years: set[int], direction: str = "quiet-precision",
                 history_signatures: dict[str, str] | None = None, reward_fn=None,
                 layout_refs: dict[str, dict] | None = None):
        self.genome, self.locks = genome, locks
        self.lock_map = {lk.slot: lk for lk in locks}
        self.renderer, self.dir = renderer, work_dir
        self.population, self.generations, self.elite, self.epsilon = population, generations, elite, epsilon
        self.rng = random.Random(seed)
        self.seed, self.synthetic, self.allowed_years = seed, synthetic, allowed_years
        self.direction = CREATIVE_DIRECTIONS.get(direction, CREATIVE_DIRECTIONS["quiet-precision"])
        self.direction_name = direction
        self.history = history_signatures or {}
        self.reward_fn = reward_fn
        self.layout_refs = layout_refs or {}
        self.dir.mkdir(parents=True, exist_ok=True)
        ensure_fonts(self.dir)
        self._batch = 0

    # ------------------------------------------------------------------ generation
    def _seed_genes(self, node: DocNode, n: int) -> list[Genes]:
        intent = derive_intent(node)
        tone = self.direction["tone_bias"].get(node.rhythm_role)
        if tone:
            intent = intent.model_copy(update={"tone_hint": tone})
        out = []
        for _ in range(n):
            g = sample_genes(self.genome, intent, self.rng)
            d = g.model_dump()
            if self.rng.random() < 0.6:
                d["number_treatment"] = self.direction["number_treatment"]
            if d["type_scale_ratio"] < self.direction["min_ratio"] and self.rng.random() < 0.6:
                d["type_scale_ratio"] = self.direction["min_ratio"]
            if self.rng.random() < 0.5:
                d["visual_metaphor"] = self.direction["metaphor"]
            out.append(Genes(**d))
        return out

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, node: DocNode, genes_list: list[Genes], page_no: int, total: int, prev: list[Chosen],
                 generation: int, parents: list[list[str]] | None = None,
                 mutations: list[list[str]] | None = None) -> list[LayoutCandidate]:
        cands = [LayoutCandidate(page_id=node.node_id, genes=g, generation=generation,
                                 parents=(parents[k] if parents else []), mutations=(mutations[k] if mutations else []),
                                 provenance=Provenance(engine_ids=["apex-native-layout", "apex-native-compiler"]))
                 for k, g in enumerate(genes_list)]
        compiled = [compile_page(node, c.genes, self.genome, self.lock_map, page_no=page_no, total_pages=total,
                                 synthetic=self.synthetic, seed=self.seed + page_no, scope=f"c-{c.candidate_id}")
                    for c in cands]
        self._batch += 1
        html_path = self.dir / f"batch-{node.node_id}-g{generation}-{self._batch}.html"
        html_path.write_text(compile_document(compiled, self.genome, title="candidates", synthetic=self.synthetic),
                             encoding="utf-8")
        res = self.renderer.measure(html_path, float(self.genome.invariants["page"]["min_margin_mm"]))
        intent = derive_intent(node)
        for c, comp, pm in zip(cands, compiled, res.metrics["pages"]):
            c.html_path = str(html_path.name)
            c.structural_signature = comp.signature
            pq = page_qa(pm, self.genome, self.locks, allowed_years=self.allowed_years,
                         fonts_loaded=res.metrics.get("fonts", []), html_dir=res.metrics.get("htmlDir", "rtl"))
            c.metrics = dict(pq.metrics)
            c.critical_failures = [f"{i.check}: {i.message}" for i in pq.critical]
            c.metrics["density_fit"] = self._density_fit(pm["coverage"], intent.density_target)
            from apex_one.design.similarity import occupancy_grid

            c.occupancy = occupancy_grid(pm)
            c.metrics["novelty"] = self._novelty(c, prev, strict=intent.archetype_strict)
            if self.reward_fn is not None:
                c.metrics["specialist_reward"] = self.reward_fn(node, c)
            else:
                c.metrics["specialist_reward"] = Metric.not_measured(
                    "specialist_reward", "no PosterReward-class model available on a $0 licence-eligible route")
            c.fitness, c.rationale = self._fitness(c)
        return cands

    @staticmethod
    def _density_fit(coverage: float, density_target: float) -> Metric:
        target = 0.12 + 0.45 * density_target
        return Metric.measured("density_fit", max(0.0, 100 - abs(coverage - target) * 250),
                               "coverage vs intent density target", evidence=[f"cov={coverage:.2f}", f"target={target:.2f}"])

    def _novelty(self, c: LayoutCandidate, prev: list[Chosen], strict: bool = False) -> Metric:
        score, why = 100.0, []
        if prev and prev[-1].archetype == c.genes.archetype:
            score -= 35
            why.append("same archetype as previous page")
        if any(p.signature == c.structural_signature for p in prev):
            score -= 25
            why.append("structure already used in this document")
        if prev and prev[-1].tone == c.genes.tone == "dark":
            score -= 15
            why.append("consecutive dark pages")
        if len(prev) >= 2 and prev[-1].tone == prev[-2].tone == c.genes.tone:
            score -= 10
            why.append("three pages with the same tone")
        loud = {"hero-number", "cover-monument", "manifesto"}
        if c.genes.archetype in loud and sum(1 for p in prev if p.archetype in loud) >= 3:
            score -= 30
            why.append("hero fatigue: already 3+ loud pages")
        # Phase 22 anti-copy: geometric layout similarity vs this document AND approved/previous layouts
        from apex_one.design.similarity import MUTATE_AT, REJECT_AT, layout_similarity

        me = {"grid": c.occupancy, "signature": c.structural_signature, "dhash": None}
        refs = {f"doc:{p.page_id}": {"grid": p.occupancy, "signature": p.signature} for p in prev if p.occupancy}
        if not strict:   # strict archetypes (cover, breath, timeline, closing) are brand DNA across guides
            refs.update(self.layout_refs)
        sims = {k: layout_similarity(me, v) for k, v in refs.items()}
        if sims:
            nearest = max(sims, key=sims.get)
            mx = sims[nearest]
            if mx >= REJECT_AT:
                score -= 45
                why.append(f"LAYOUT_SIMILARITY {mx:.2f} >= {REJECT_AT} vs {nearest} (near-copy)")
            elif mx >= MUTATE_AT:
                score -= 20
                why.append(f"LAYOUT_SIMILARITY {mx:.2f} >= {MUTATE_AT} vs {nearest}")
        verdict = self.history.get(c.structural_signature)
        if verdict == "rejected":
            score -= 30
            why.append("structure previously REJECTED by a human")
        elif verdict == "approved":
            score -= 8
            why.append("structure used in an earlier approved guide (avoid template feel)")
        return Metric.measured("novelty", max(0.0, score), "sequence-aware structural novelty", evidence=why)

    @staticmethod
    def _fitness(c: LayoutCandidate) -> tuple[float | None, list[str]]:
        num = den = 0.0
        parts = []
        for name, w in WEIGHTS.items():
            m = c.metrics.get(name)
            if m is None or m.status != MetricStatus.MEASURED or m.value is None:
                continue
            num += w * m.value
            den += w
            parts.append(f"{name}={m.value:.0f}")
        if den == 0:
            return None, ["no measured metrics"]
        f = num / den
        if c.critical_failures:
            f -= 1000
        return round(f, 3), parts

    def _screenshot_top(self, node: DocNode, top: list[LayoutCandidate], page_no: int, total: int) -> None:
        """Real screenshots of the finalists: measured visual weight (ink) for document rhythm, and A/B/C images
        for human preference review."""
        from apex_one.vision.page import ink_stats

        compiled = [compile_page(node, c.genes, self.genome, self.lock_map, page_no=page_no, total_pages=total,
                                 synthetic=self.synthetic, seed=self.seed + page_no, scope=f"c-{c.candidate_id}")
                    for c in top]
        path = self.dir / f"top-{node.node_id}.html"
        path.write_text(compile_document(compiled, self.genome, title="finalists", synthetic=self.synthetic),
                        encoding="utf-8")
        res = self.renderer.measure(path, float(self.genome.invariants["page"]["min_margin_mm"]),
                                    screenshot_dir=self.dir, screenshot_prefix=f"top-{node.node_id}")
        for c, shot in zip(top, res.page_screenshots):
            lum, ink = ink_stats(shot)
            c.screenshot_path = str(shot.name)
            c.metrics["ink"] = Metric.measured("ink", ink, "screenshot ink density (same measure as rhythm analysis)",
                                               unit="ratio", evidence=[f"luminance={lum:.3f}"])

    # ------------------------------------------------------------------ evolution
    def _tournament_pick(self, ranked: list[LayoutCandidate], k: int = 3) -> LayoutCandidate:
        pool = self.rng.sample(ranked, min(k, len(ranked)))
        return max(pool, key=lambda c: c.fitness or -1e9)

    def run_page(self, node: DocNode, page_no: int, total: int, prev: list[Chosen], initial: int) -> PageOutcome:
        intent = derive_intent(node)
        evaluated = self.evaluate(node, self._seed_genes(node, initial), page_no, total, prev, 0)
        all_c = list(evaluated)
        best_hist: list[float] = []
        gens = 0
        for gen in range(1, self.generations + 1):
            gens = gen
            survivors = [c for c in all_c if not c.critical_failures]
            if not survivors:
                # failure-specific repair of the least-bad candidates
                worst_first = sorted(all_c, key=lambda c: len(c.critical_failures))[: self.population]
                repaired, notes = [], []
                for c in worst_first:
                    from apex_one.core.schemas.quality import QAIssue

                    issues = [QAIssue(check=f.split(":")[0], severity="critical", message=f) for f in c.critical_failures]
                    g, applied = repair_genes(c.genes, issues, self.genome)
                    repaired.append(g)
                    notes.append(["repair:" + "; ".join(applied)])
                new = self.evaluate(node, repaired, page_no, total, prev, gen,
                                    parents=[[c.candidate_id] for c in worst_first], mutations=notes)
                all_c += new
                continue
            ranked = sorted(survivors, key=lambda c: -(c.fitness or -1e9))
            best = ranked[0].fitness or 0.0
            if best_hist and best - best_hist[-1] < self.epsilon:
                best_hist.append(best)
                break   # converged
            best_hist.append(best)
            elites = ranked[: self.elite]
            children, parents, muts = [], [], []
            while len(children) < self.population:
                p1, p2 = self._tournament_pick(ranked), self._tournament_pick(ranked)
                child = crossover(p1.genes, p2.genes, self.rng) if p1 is not p2 and self.rng.random() < 0.5 else p1.genes
                weak = sorted((k for k in ("design.hierarchy", "design.typography", "density_fit", "design.brand_fit",
                                           "geometry.alignment", "novelty")
                               if p1.metrics.get(k) and p1.metrics[k].value is not None),
                              key=lambda k: p1.metrics[k].value)[:2]
                ops = operators_for_weakness([("novelty" if k == "novelty" else k) for k in weak])
                op = self.rng.choice(ops)
                direction = 0
                dm = p1.metrics.get("density_fit")
                if op in ("density", "whitespace") and dm and dm.evidence:
                    cov = float(dm.evidence[0].split("=")[1])
                    tgt = float(dm.evidence[1].split("=")[1])
                    direction = 1 if (cov < tgt) == (op == "density") else -1
                if intent.archetype_strict and op == "archetype":
                    op = "grid"
                child = mutate(child, op, self.genome, self.rng, intent.archetype_preferences, direction)
                if intent.archetype_strict and child.archetype not in intent.archetype_preferences:
                    child = child.model_copy(update={"archetype": intent.archetype_preferences[0]})
                children.append(child)
                parents.append([p1.candidate_id] + ([p2.candidate_id] if p2 is not p1 else []))
                muts.append([op])
            all_c += self.evaluate(node, children, page_no, total, prev, gen, parents, muts)
            del elites
        final = sorted([c for c in all_c if not c.critical_failures] or all_c, key=lambda c: -(c.fitness or -1e9))
        self._screenshot_top(node, final[:3], page_no, total)
        return PageOutcome(best=final[0], top=final[:3], evaluated=len(all_c), generations=gens,
                           rejected_critical=sum(1 for c in all_c if c.critical_failures), history=best_hist)
