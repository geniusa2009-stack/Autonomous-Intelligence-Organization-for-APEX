"""APEX Design Genome. SAME DNA, DIFFERENT ORGANISM."""

from __future__ import annotations

import random
from pathlib import Path

import yaml

from apex_one.core.schemas.design import DesignGenome, DesignIntent, Genes
from apex_one.settings import get_settings


def load_genome(config_dir: Path | None = None) -> DesignGenome:
    data = yaml.safe_load(((config_dir or get_settings().config_dir) / "apex_brand.yaml").read_text(encoding="utf-8"))
    return DesignGenome(version=data["genome_version"], invariants=data["invariants"], gene_space=data["gene_space"])


def _pick(rng: random.Random, options: list, bias: list | None = None, p_bias: float = 0.7):
    """Categorical gene choice, biased toward the intent's preferences."""
    if bias and rng.random() < p_bias:
        preferred = [b for b in bias if b in options]
        if preferred:
            return rng.choice(preferred)
    return rng.choice(options)


def sample_genes(genome: DesignGenome, intent: DesignIntent, rng: random.Random) -> Genes:
    gs = genome.gene_space
    archetype = _pick(rng, gs["archetype"], intent.archetype_preferences, 1.0 if intent.archetype_strict else 0.92)
    density_center = intent.density_target
    g = Genes(
        archetype=archetype,
        column_structure=_pick(rng, gs["column_structure"]),
        asymmetry=round(rng.uniform(*gs["asymmetry"]), 3),
        type_scale_ratio=rng.choice(gs["type_scale_ratio"]),
        base_font_px=round(rng.uniform(*gs["base_font_px"]), 2),
        heading_weight=rng.choice(gs["heading_weight"]),
        density=round(min(0.9, max(0.2, rng.gauss(density_center, 0.12))), 3),
        whitespace=round(min(0.9, max(0.2, rng.gauss(1 - density_center, 0.12))), 3),
        margin_mm=round(rng.uniform(*gs["margin_mm"]), 1),
        hero_treatment=rng.choice(gs["hero_treatment"]),
        number_treatment=rng.choice(gs["number_treatment"]),
        section_division=rng.choice(gs["section_division"]),
        timeline_style=rng.choice(gs["timeline_style"]),
        data_viz=rng.choice(gs["data_viz"]),
        visual_metaphor=rng.choice(gs["visual_metaphor"]),
        tone=_pick(rng, gs["tone"], [intent.tone_hint], 0.75),
        arabic_wrap=rng.choice(gs["arabic_wrap"]),
    )
    return g
