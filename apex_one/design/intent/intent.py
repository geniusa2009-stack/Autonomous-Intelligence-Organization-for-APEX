"""Design intent: what each page must achieve visually, derived from the Document AST."""

from __future__ import annotations

from apex_one.core.schemas.design import DesignIntent
from apex_one.core.schemas.document import DocNode, NodeType

ARCHETYPES_FOR: dict[NodeType, list[str]] = {
    NodeType.COVER: ["cover-monument"],
    NodeType.OPENING: ["editorial-column", "split-asymmetric"],   # quiet role: no loud archetypes (hero fatigue)
    NodeType.OPPORTUNITY_SNAPSHOT: ["ledger", "split-asymmetric", "hero-number"],
    NodeType.HERO_FACT: ["hero-number", "manifesto"],
    NodeType.FUNDING_CHAPTER: ["ledger", "split-asymmetric", "editorial-column"],
    NodeType.WARNING: ["manifesto", "split-asymmetric"],
    NodeType.ELIGIBILITY_CHAPTER: ["editorial-column", "split-asymmetric"],
    NodeType.BREATH: ["quiet-breath"],
    NodeType.APPLICATION_JOURNEY: ["checklist-sheet", "ledger", "split-asymmetric"],
    NodeType.TIMELINE: ["timeline-rail"],
    NodeType.APEX_TAKE: ["split-asymmetric", "editorial-column"],
    NodeType.CHECKLIST: ["checklist-sheet", "timeline-rail"],
    NodeType.CLOSING: ["manifesto"],      # strong close (rhythm analysis: light editorial closings flatten the ending)
}
TONE_FOR_RHYTHM = {"loud": "dark", "quiet": "light", "information": "light", "story": "silver", "warning": "light",
                   "breath": "silver", "action": "light", "close": "dark"}


def derive_intent(node: DocNode) -> DesignIntent:
    prefs = ARCHETYPES_FOR.get(node.semantic_type, ["editorial-column"])
    emphasis = {"glance": "one dominant element", "scan": "scannable rows with mono figures",
                "read": "comfortable measure and rhythm", "study": "structured reference",
                "act": "numbered actions"}[node.reading_mode.value]
    rationale = [f"{node.semantic_type.value}: reading mode {node.reading_mode.value} -> {emphasis}",
                 f"rhythm role {node.rhythm_role} -> tone {TONE_FOR_RHYTHM.get(node.rhythm_role, 'light')}",
                 f"first fixation must land on block {node.first_fixation}"]
    return DesignIntent(page_id=node.node_id, node_type=node.semantic_type.value, reading_mode=node.reading_mode.value,
                        rhythm_role=node.rhythm_role, emphasis=emphasis, density_target=node.visual_density,
                        tone_hint=TONE_FOR_RHYTHM.get(node.rhythm_role, "light"), first_fixation=node.first_fixation,
                        archetype_preferences=prefs,
                        archetype_strict=node.semantic_type in (NodeType.COVER, NodeType.BREATH, NodeType.TIMELINE,
                                                               NodeType.CLOSING),
                        rationale=rationale)
