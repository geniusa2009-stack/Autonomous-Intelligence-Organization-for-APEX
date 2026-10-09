"""ONE Document Brain: the Document AST. Text never jumps straight to HTML."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from apex_one.core.schemas.common import ApexModel, new_id


class NodeType(StrEnum):
    DOCUMENT = "Document"
    COVER = "Cover"
    OPENING = "Opening"
    OPPORTUNITY_SNAPSHOT = "OpportunitySnapshot"
    FUNDING_CHAPTER = "FundingChapter"
    ELIGIBILITY_CHAPTER = "EligibilityChapter"
    APPLICATION_JOURNEY = "ApplicationJourney"
    TIMELINE = "Timeline"
    COMPARISON = "Comparison"
    HERO_FACT = "HeroFact"
    WARNING = "Warning"
    APEX_TAKE = "ApexTake"
    PROFILE_STORY = "ProfileStory"
    CHECKLIST = "Checklist"
    BREATH = "Breath"
    CLOSING = "Closing"


class ReadingMode(StrEnum):
    GLANCE = "glance"        # < 3 s, one idea
    SCAN = "scan"            # lists, timelines, numbers
    READ = "read"            # narrative paragraphs
    STUDY = "study"          # dense reference, tables
    ACT = "act"              # checklists, CTAs


class Emotion(StrEnum):
    AMBITION = "ambition"
    CALM = "calm"
    URGENCY = "urgency"
    CAUTION = "caution"
    CONFIDENCE = "confidence"
    WARMTH = "warmth"


class TextRun(ApexModel):
    """A run of content. `slot` binds the run to a FactLock: text is rendered FROM the lock."""

    kind: str = "text"       # text | fact | term | url
    text: str = ""
    lang: str = "ar"
    slot: str | None = None
    claim_id: str | None = None
    display: str = "ar"      # which lock display to use: ar | en | cond
    cond: str | None = None  # "true_text|false_text" for boolean facts rendered as words


class Block(ApexModel):
    block_id: str = Field(default_factory=lambda: new_id("B"))
    role: str                # heading | kicker | paragraph | list_item | figure | stat | step | note | cta
    runs: list[TextRun] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class DocNode(ApexModel):
    node_id: str = Field(default_factory=lambda: new_id("N"))
    semantic_type: NodeType
    title_ar: str = ""
    title_en: str = ""
    importance: int = 3                # 1..5
    reading_mode: ReadingMode = ReadingMode.READ
    decision_impact: int = 2           # 1..5 — how much this changes the student's decision
    visual_density: float = 0.5        # 0 airy .. 1 dense
    emotion: Emotion = Emotion.CALM
    first_fixation: str = ""           # block_id the eye MUST land on first
    scan_target_seconds: int = 20
    content: list[Block] = Field(default_factory=list)
    locked_claim_refs: list[str] = Field(default_factory=list)
    children: list["DocNode"] = Field(default_factory=list)
    rhythm_role: str = "information"   # loud | quiet | information | story | warning | breath | action | close


class DocumentAST(ApexModel):
    doc_id: str = Field(default_factory=lambda: new_id("D"))
    title_ar: str
    title_en: str
    language: str = "ar-EG"
    direction: str = "rtl"
    synthetic: bool = False
    root: DocNode
    voice_version: str = ""
    fact_lock_hashes: dict[str, str] = Field(default_factory=dict)

    def pages(self) -> list[DocNode]:
        return list(self.root.children)
