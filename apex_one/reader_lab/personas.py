"""Reader personas and the job's ReaderModel."""

from __future__ import annotations

import yaml

from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.mission import QualityMode
from apex_one.core.schemas.opportunity import ReaderModel, ReaderPersona
from apex_one.settings import get_settings

MUST_UNDERSTAND_ORDER = [
    "deadline.application", "scholarship_coverage.tuition", "funding.student_contribution_per_year",
    "fee.application", "test_minimum.toefl_ibt", "eligibility.financial_need", "deposit.enrollment",
    "test_requirement.sat_act",
]


def load_personas() -> list[ReaderPersona]:
    data = yaml.safe_load((get_settings().config_dir / "readers.yaml").read_text(encoding="utf-8"))
    return [ReaderPersona(**p) for p in data["personas"]]


def build_reader_model(locks: list[FactLock], mode: QualityMode) -> ReaderModel:
    personas = load_personas()
    if mode in (QualityMode.DRAFT, QualityMode.STANDARD):
        personas = [p for p in personas if p.persona_id in ("teen-15-17", "weak-english", "mobile-only")]
    slots = {lk.slot for lk in locks}
    must = [s for s in MUST_UNDERSTAND_ORDER if s in slots]
    return ReaderModel(primary_persona="teen-15-17", personas=personas, must_understand=must,
                       tone_notes=["parents may read along: money must be crystal clear",
                                   "weak-English readers must get every critical fact from Arabic text alone"])
