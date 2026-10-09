"""Reader Lab: simulate how different Egyptian readers consume the RENDERED guide.

This is an extractive simulation over the rendered DOM (reading order, font sizes, languages,
viewport), not a human study. It is labelled as such in every metric. A beautiful page that causes
a misunderstanding fails here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.opportunity import ReaderPersona

WORDS_PER_SECOND = {"weak": 2.5, "medium": 3.5, "strong": 4.5}
LATIN_RX = re.compile(r"[A-Za-z]")
ARABIC_RX = re.compile(r"[؀-ۿ]")


@dataclass
class ReadItem:
    text: str
    page: int
    font_px: float
    lang: str = "ar"
    role: str = "p"              # heading | stat | p | li | warning | cta | footer
    slots: list[str] = field(default_factory=list)
    viewport: str = "desktop"


@dataclass
class Answer:
    question: str
    slot: str | None
    found: bool
    correct: bool
    seen_values: list[str] = field(default_factory=list)


@dataclass
class PersonaResult:
    persona_id: str
    answers: list[Answer]
    misunderstandings: list[str]
    words_read: int

    @property
    def score(self) -> float:
        return 100.0 * sum(a.correct for a in self.answers) / max(1, len(self.answers))


class ReaderSimulator:
    def __init__(self, locks: list[FactLock], must_understand: list[str]):
        self.locks = {lk.slot: lk for lk in locks}
        self.must = [s for s in must_understand if s in self.locks]

    def _visible(self, persona: ReaderPersona, items: list[ReadItem]) -> tuple[list[ReadItem], int]:
        view = "mobile" if persona.reading_mode == "mobile" else "desktop"
        seq = [i for i in items if i.viewport == view] or items
        budget_words = int(persona.scan_budget_seconds * WORDS_PER_SECOND.get(persona.english_level, 3.5))
        out, used = [], 0
        for it in seq:
            if it.role == "footer":
                continue
            if persona.english_level == "weak" and it.lang == "en" and not ARABIC_RX.search(it.text):
                continue  # cannot read English-only text
            if persona.reading_mode in ("skim", "mobile") and it.role not in ("heading", "stat", "warning", "cta") \
                    and it.font_px < 17:
                # skimmers read only the first sentence of body text
                text = re.split(r"(?<=[.!?؟،])\s", it.text, maxsplit=1)[0]
            else:
                text = it.text
            words = len(text.split())
            if used + words > budget_words:
                break
            used += words
            out.append(ReadItem(text, it.page, it.font_px, it.lang, it.role, it.slots, it.viewport))
        return out, used

    def simulate(self, persona: ReaderPersona, items: list[ReadItem]) -> PersonaResult:
        seen, words = self._visible(persona, items)
        answers: list[Answer] = []
        for slot in self.must:
            lk = self.locks[slot]
            hits = [i for i in seen if slot in i.slots]
            values = sorted({v for i in hits for v in (lk.display_ar, lk.display_en) if v in i.text})
            correct = bool(hits) and bool(values)
            answers.append(Answer(question=f"What is {slot}?", slot=slot, found=bool(hits), correct=correct,
                                  seen_values=values))
        # next action & main risk
        answers.append(Answer("What should I do next?", None, any(i.role == "cta" for i in seen),
                              any(i.role == "cta" for i in seen)))
        answers.append(Answer("What is the main risk?", None, any(i.role == "warning" for i in seen),
                              any(i.role == "warning" for i in seen)))
        mis: list[str] = []
        seen_slots = {s for i in seen for s in i.slots}
        if "scholarship_coverage.tuition" in seen_slots and "funding.student_contribution_per_year" in self.locks \
                and "funding.student_contribution_per_year" not in seen_slots:
            mis.append("believes the opportunity costs nothing (saw tuition coverage, missed the yearly contribution)")
        if "test_requirement.sat_act" in seen_slots and "test_minimum.toefl_ibt" in self.locks \
                and "test_minimum.toefl_ibt" not in seen_slots:
            mis.append("believes no test is required (saw test-optional, missed the English minimum)")
        if "deadline.application" in self.locks and "deadline.application" not in seen_slots:
            mis.append("does not know the application deadline")
        return PersonaResult(persona.persona_id, answers, mis, words)

    def run(self, personas: list[ReaderPersona], items: list[ReadItem]) -> tuple[list[PersonaResult], Metric]:
        results = [self.simulate(p, items) for p in personas]
        if not results:
            return results, Metric.not_measured("reader.comprehension", "no personas")
        penalty = sum(len(r.misunderstandings) for r in results) * 5.0
        score = max(0.0, sum(r.score for r in results) / len(results) - penalty)
        return results, Metric.measured(
            "reader.comprehension", score,
            method="extractive persona simulation over rendered DOM (not a human study)",
            evidence=[f"{r.persona_id}: {r.score:.0f} ({len(r.misunderstandings)} misunderstandings)" for r in results])
