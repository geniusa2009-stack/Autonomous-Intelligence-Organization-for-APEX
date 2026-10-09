"""NarrativeArchitect: information architecture with deliberate document rhythm.

LOUD · quiet · information · story · warning · breath · action · strong close — never card, card, card.
"""

from __future__ import annotations

from apex_one.core.schemas.common import ApexModel
from apex_one.core.schemas.document import Emotion, NodeType, ReadingMode
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.opportunity import OpportunityModel, ReaderModel


class SectionPlan(ApexModel):
    node_type: NodeType
    rhythm_role: str
    importance: int
    reading_mode: ReadingMode
    decision_impact: int
    density: float
    emotion: Emotion
    scan_target_seconds: int
    rationale: str


class NarrativeArchitect:
    def __init__(self, locks: list[FactLock], opp: OpportunityModel, reader: ReaderModel):
        self.slots = {lk.slot for lk in locks}
        self.dates = [lk for lk in locks if lk.value.type.value == "date"]
        self.opp, self.reader = opp, reader

    def plan(self, emphasis_feedback: list[str] | None = None) -> list[SectionPlan]:
        """`emphasis_feedback` comes from Reader Lab failures (e.g. 'funding.student_contribution_per_year')."""
        fb = set(emphasis_feedback or [])
        P = SectionPlan
        plan: list[SectionPlan] = [
            P(node_type=NodeType.COVER, rhythm_role="loud", importance=5, reading_mode=ReadingMode.GLANCE,
              decision_impact=2, density=0.15, emotion=Emotion.AMBITION, scan_target_seconds=3,
              rationale="identity + promise; one idea"),
            P(node_type=NodeType.OPENING, rhythm_role="quiet", importance=3, reading_mode=ReadingMode.READ,
              decision_impact=2, density=0.35, emotion=Emotion.WARMTH, scan_target_seconds=40,
              rationale="frame the opportunity honestly before numbers"),
            P(node_type=NodeType.OPPORTUNITY_SNAPSHOT, rhythm_role="information", importance=5,
              reading_mode=ReadingMode.SCAN, decision_impact=5, density=0.55, emotion=Emotion.CONFIDENCE,
              scan_target_seconds=15, rationale="decision-critical facts first for skimmers and parents"),
        ]
        if "scholarship_coverage.tuition" in self.slots:
            plan.append(P(node_type=NodeType.HERO_FACT, rhythm_role="loud", importance=4, reading_mode=ReadingMode.GLANCE,
                          decision_impact=4, density=0.12, emotion=Emotion.AMBITION, scan_target_seconds=3,
                          rationale="the single number that changes the decision"))
        if self.opp.core_value or self.opp.financial_risk:
            plan.append(P(node_type=NodeType.FUNDING_CHAPTER, rhythm_role="information", importance=5,
                          reading_mode=ReadingMode.STUDY, decision_impact=5,
                          density=0.6 if "funding.student_contribution_per_year" not in fb else 0.45,
                          emotion=Emotion.CALM, scan_target_seconds=45,
                          rationale="separate what is covered from what the family pays"))
        if self.opp.likely_misunderstanding:
            plan.append(P(node_type=NodeType.WARNING, rhythm_role="warning", importance=5, reading_mode=ReadingMode.GLANCE,
                          decision_impact=5, density=0.3, emotion=Emotion.CAUTION, scan_target_seconds=10,
                          rationale="pre-empt the most likely misunderstanding right after the money"))
        if self.opp.eligibility_risk:
            plan.append(P(node_type=NodeType.ELIGIBILITY_CHAPTER, rhythm_role="information", importance=5,
                          reading_mode=ReadingMode.READ, decision_impact=5, density=0.45, emotion=Emotion.CALM,
                          scan_target_seconds=30, rationale="official wording, quoted, no paraphrase drift"))
        plan.append(P(node_type=NodeType.BREATH, rhythm_role="breath", importance=1, reading_mode=ReadingMode.GLANCE,
                      decision_impact=1, density=0.08, emotion=Emotion.CALM, scan_target_seconds=4,
                      rationale="pause after dense chapters"))
        if any(s.startswith(("application_requirement", "test_minimum")) for s in self.slots):
            plan.append(P(node_type=NodeType.APPLICATION_JOURNEY, rhythm_role="action", importance=4,
                          reading_mode=ReadingMode.SCAN, decision_impact=4, density=0.55, emotion=Emotion.CONFIDENCE,
                          scan_target_seconds=30, rationale="what to prepare, hardest first"))
        if len(self.dates) >= 2:
            plan.append(P(node_type=NodeType.TIMELINE, rhythm_role="information", importance=5,
                          reading_mode=ReadingMode.SCAN, decision_impact=5, density=0.4, emotion=Emotion.URGENCY,
                          scan_target_seconds=12, rationale="dates as a sequence, deadline unmistakable"))
        if self.opp.best_fit_student or self.opp.poor_fit_student:
            plan.append(P(node_type=NodeType.APEX_TAKE, rhythm_role="story", importance=3, reading_mode=ReadingMode.READ,
                          decision_impact=3, density=0.35, emotion=Emotion.WARMTH, scan_target_seconds=30,
                          rationale="labelled APEX opinion, clearly separated from facts"))
        plan.append(P(node_type=NodeType.CHECKLIST, rhythm_role="action", importance=4, reading_mode=ReadingMode.ACT,
                      decision_impact=4, density=0.45, emotion=Emotion.CONFIDENCE, scan_target_seconds=20,
                      rationale="convert understanding into dated actions"))
        plan.append(P(node_type=NodeType.CLOSING, rhythm_role="close", importance=3, reading_mode=ReadingMode.READ,
                      decision_impact=2, density=0.35, emotion=Emotion.AMBITION, scan_target_seconds=20,
                      rationale="strong close, open questions and sources"))
        return self._fix_rhythm(plan)

    @staticmethod
    def _fix_rhythm(plan: list[SectionPlan]) -> list[SectionPlan]:
        """No two consecutive identical rhythm roles (except the forced cover)."""
        closing = [p for p in plan if p.node_type == NodeType.CLOSING]
        out = [plan[0]]
        rest = [p for p in plan[1:] if p.node_type != NodeType.CLOSING]
        while rest:
            nxt = next((p for p in rest if p.rhythm_role != out[-1].rhythm_role), rest[0])
            rest.remove(nxt)
            out.append(nxt)
        return out + closing

    @staticmethod
    def rhythm_violations(plan: list[SectionPlan]) -> list[str]:
        return [f"{a.node_type}->{b.node_type} both {a.rhythm_role}" for a, b in zip(plan, plan[1:])
                if a.rhythm_role == b.rhythm_role]
