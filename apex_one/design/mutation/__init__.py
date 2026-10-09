"""Mutation and crossover operators over evolvable genes (invariant DNA is untouchable)."""

from __future__ import annotations

import random

from apex_one.core.schemas.design import DesignGenome, Genes

OPERATORS = ["typography", "grid", "whitespace", "hierarchy", "density", "hero_treatment", "number_treatment",
             "image_balance", "section_division", "arabic_wrapping", "data_visualization", "visual_metaphor", "archetype"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def mutate(g: Genes, op: str, genome: DesignGenome, rng: random.Random, prefs: list[str] | None = None,
           direction: int = 0) -> Genes:
    gs = genome.gene_space
    d = g.model_dump()
    sign = direction or rng.choice([-1, 1])
    if op == "typography":
        ratios = gs["type_scale_ratio"]
        idx = ratios.index(g.type_scale_ratio) if g.type_scale_ratio in ratios else 2
        d["type_scale_ratio"] = ratios[int(_clamp(idx + sign, 0, len(ratios) - 1))]
        d["base_font_px"] = round(_clamp(g.base_font_px + sign * rng.uniform(0.5, 1.5), *gs["base_font_px"]), 2)
        d["heading_weight"] = rng.choice(gs["heading_weight"])
    elif op == "grid":
        d["column_structure"] = rng.choice([c for c in gs["column_structure"] if c != g.column_structure])
        d["asymmetry"] = round(_clamp(g.asymmetry + rng.uniform(-0.3, 0.3), *gs["asymmetry"]), 3)
    elif op == "whitespace":
        d["whitespace"] = round(_clamp(g.whitespace + sign * rng.uniform(0.08, 0.2), *gs["whitespace"]), 3)
        d["margin_mm"] = round(_clamp(g.margin_mm + sign * rng.uniform(1, 3), *gs["margin_mm"]), 1)
    elif op == "hierarchy":
        ratios = gs["type_scale_ratio"]
        idx = ratios.index(g.type_scale_ratio) if g.type_scale_ratio in ratios else 2
        d["type_scale_ratio"] = ratios[int(_clamp(idx + (direction or 1), 0, len(ratios) - 1))]
        d["heading_weight"] = 700
    elif op == "density":
        d["density"] = round(_clamp(g.density + sign * rng.uniform(0.08, 0.2), *gs["density"]), 3)
    elif op == "hero_treatment":
        d["hero_treatment"] = rng.choice([h for h in gs["hero_treatment"] if h != g.hero_treatment])
    elif op == "number_treatment":
        d["number_treatment"] = rng.choice([n for n in gs["number_treatment"] if n != g.number_treatment])
    elif op in ("image_balance", "visual_metaphor"):
        d["visual_metaphor"] = rng.choice([m for m in gs["visual_metaphor"] if m != g.visual_metaphor])
    elif op == "section_division":
        d["section_division"] = rng.choice([s for s in gs["section_division"] if s != g.section_division])
    elif op == "arabic_wrapping":
        d["arabic_wrap"] = rng.choice([w for w in gs["arabic_wrap"] if w != g.arabic_wrap])
    elif op == "data_visualization":
        d["data_viz"] = rng.choice([v for v in gs["data_viz"] if v != g.data_viz])
    elif op == "archetype":
        options = [a for a in (prefs or gs["archetype"]) if a != g.archetype] or gs["archetype"]
        d["archetype"] = rng.choice(options)
    elif op == "tone":
        d["tone"] = rng.choice([t for t in gs["tone"] if t != g.tone])
    return Genes(**d)


def crossover(a: Genes, b: Genes, rng: random.Random) -> Genes:
    da, db = a.model_dump(), b.model_dump()
    return Genes(**{k: (da[k] if rng.random() < 0.5 else db[k]) for k in da})


def operators_for_weakness(weak_metrics: list[str]) -> list[str]:
    table = {
        "design.typography": ["typography", "arabic_wrapping"],
        "design.hierarchy": ["hierarchy", "hero_treatment", "number_treatment"],
        "density_fit": ["density", "whitespace"],
        "design.brand_fit": ["section_division", "visual_metaphor"],
        "geometry.alignment": ["grid"],
        "novelty": ["archetype", "grid", "section_division"],
        "accessibility.contrast": ["tone"],
    }
    ops: list[str] = []
    for m in weak_metrics:
        ops += [o for o in table.get(m, []) if o not in ops]
    return ops or ["typography", "grid", "whitespace"]
