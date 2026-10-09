"""apex-native-repair: classify a rendered failure and apply the targeted fix.

Failure-specific: geometry failures change layout genes; RTL failures are compiler issues and are
escalated to the HTML_BUILD loop; contrast failures change tone. Never a blind restart.
"""

from __future__ import annotations

from apex_one.core.schemas.design import DesignGenome, Genes
from apex_one.core.schemas.quality import QAIssue

FAILURE_CLASSES = {
    "qa.overflow": "GEOMETRY", "qa.page_bounds": "GEOMETRY", "qa.clipping": "GEOMETRY", "qa.collision": "GEOMETRY",
    "qa.margins": "GEOMETRY", "qa.line_length": "TYPOGRAPHY", "qa.font_hierarchy": "TYPOGRAPHY",
    "qa.line_height": "TYPOGRAPHY", "qa.widows_orphans": "TYPOGRAPHY", "qa.contrast": "CONTRAST",
    "qa.rtl_direction": "RTL", "qa.ltr_isolation": "RTL", "qa.mixed_runs": "RTL", "qa.currency": "RTL",
    "qa.percent": "RTL", "qa.long_urls": "RTL", "qa.dom_fact_integrity": "FACT", "vision.card_overuse": "AESTHETIC",
    "brand.palette": "BRAND", "brand.gradients": "BRAND",
}


def classify(issues: list[QAIssue]) -> list[str]:
    kinds = []
    for i in issues:
        k = FAILURE_CLASSES.get(i.check)
        if k and k not in kinds and i.severity in ("critical", "major"):
            kinds.append(k)
    return kinds


def repair_genes(g: Genes, issues: list[QAIssue], genome: DesignGenome) -> tuple[Genes, list[str]]:
    gs = genome.gene_space
    d = g.model_dump()
    applied = []
    checks = {i.check for i in issues if i.severity in ("critical", "major")}
    if checks & {"qa.overflow", "qa.page_bounds", "qa.clipping"}:
        d["base_font_px"] = max(gs["base_font_px"][0], round(g.base_font_px - 1.5, 2))
        d["density"] = min(gs["density"][1], round(g.density + 0.15, 3))
        d["whitespace"] = max(gs["whitespace"][0], round(g.whitespace - 0.15, 3))
        ratios = gs["type_scale_ratio"]
        if g.type_scale_ratio in ratios and ratios.index(g.type_scale_ratio) > 0:
            d["type_scale_ratio"] = ratios[ratios.index(g.type_scale_ratio) - 1]
        applied.append("shrink: font, scale, whitespace; raise density")
    if "qa.collision" in checks:
        d["column_structure"] = "12"
        d["asymmetry"] = 0.2
        applied.append("collision: single column, low asymmetry")
    if "qa.margins" in checks:
        d["margin_mm"] = min(gs["margin_mm"][1], g.margin_mm + 3)
        applied.append("margins: increase page margin")
    if "qa.line_length" in checks:
        d["density"] = max(gs["density"][0], round(g.density - 0.15, 3))
        d["column_structure"] = "7-5" if g.column_structure in ("12", "8-4") else g.column_structure
        applied.append("line length: narrower measure")
    if "qa.contrast" in checks:
        d["tone"] = "light" if g.tone != "light" else "silver"
        applied.append("contrast: tone change")
    if "qa.font_hierarchy" in checks:
        d["base_font_px"] = min(gs["base_font_px"][1], round(g.base_font_px + 1.0, 2))
        applied.append("hierarchy: larger base size")
    return Genes(**d), applied
