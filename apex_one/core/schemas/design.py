"""APEX Design Genome, design intent and layout candidate schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from apex_one.core.schemas.common import ApexModel, Metric, Provenance, new_id


class Genes(ApexModel):
    """Evolvable DNA. Invariant DNA lives in DesignGenome.invariants and never mutates."""

    archetype: str = "editorial-column"
    grid_columns: int = 12
    column_structure: str = "8-4"          # e.g. 12, 8-4, 7-5, 5-7, 4-4-4, 3-9
    asymmetry: float = 0.3                 # 0 symmetric .. 1 strongly asymmetric
    type_scale_ratio: float = 1.333
    base_font_px: float = 15.0
    heading_weight: int = 700
    density: float = 0.5
    whitespace: float = 0.5                # 0 tight .. 1 generous
    margin_mm: float = 16.0
    hero_treatment: str = "giant-number"   # giant-number | band | split | quiet | none
    number_treatment: str = "mono-figure"  # mono-figure | outlined | underline-rule | inline
    section_division: str = "rule"         # rule | space | tone-shift | numeral
    timeline_style: str = "rail"           # rail | ladder | ledger
    data_viz: str = "bar-fraction"         # bar-fraction | stacked-ledger | none
    visual_metaphor: str = "grid-lines"    # grid-lines | orbit | blueprint | none
    tone: str = "light"                    # light | dark | silver
    arabic_wrap: str = "balance"           # balance | pretty | normal


class DesignGenome(ApexModel):
    version: str
    invariants: dict[str, Any]
    gene_space: dict[str, Any]
    defaults: Genes = Field(default_factory=Genes)


class DesignIntent(ApexModel):
    page_id: str
    node_type: str
    reading_mode: str
    rhythm_role: str
    emphasis: str
    density_target: float
    tone_hint: str
    first_fixation: str
    archetype_preferences: list[str]
    archetype_strict: bool = False
    rationale: list[str] = Field(default_factory=list)


class LayoutCandidate(ApexModel):
    candidate_id: str = Field(default_factory=lambda: new_id("LC"))
    page_id: str
    genes: Genes
    generation: int = 0
    parents: list[str] = Field(default_factory=list)
    mutations: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    html_path: str | None = None
    screenshot_path: str | None = None
    metrics: dict[str, Metric] = Field(default_factory=dict)
    critical_failures: list[str] = Field(default_factory=list)
    fitness: float | None = None
    rationale: list[str] = Field(default_factory=list)
    structural_signature: str = ""


class DesignDecision(ApexModel):
    decision_id: str = Field(default_factory=lambda: new_id("DD"))
    page_id: str
    chosen_candidate: str
    rejected_candidates: list[str] = Field(default_factory=list)
    route: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    fitness: float | None = None
