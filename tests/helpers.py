"""Shared, cached pipeline fragments for tests (built once per test session)."""

from __future__ import annotations

import tempfile
from datetime import date
from functools import lru_cache
from pathlib import Path

from apex_one.core.schemas.evidence import ClaimStatus
from apex_one.core.schemas.mission import Job, Mission, QualityMode
from apex_one.core.workspace import JobWorkspace

SYN_MISSION = Mission(text="Create an APEX guide for Example Labor College Fall 2027",
                      opportunity_name="Example Labor College Fall 2027", institution="Example Labor College",
                      cycle="Fall 2027", cycle_year=2027)


@lru_cache(maxsize=1)
def researched_state():
    from apex_one.research.swarm import ResearchDirector

    job = Job(mission=SYN_MISSION, offline_fixture="synthetic_berea_style")
    ws = JobWorkspace(job.job_id, root=Path(tempfile.mkdtemp(prefix="apex-test-")))
    rd = ResearchDirector(job, ws)
    rd.discover()
    rd.expand_and_parse()
    rd.extract()
    rd.contradictions()
    rd.resolve_and_lock()
    return rd.state


def editorial(seed: int = 7, drop_slots: tuple[str, ...] = ()):
    from apex_one.document.ast.builder import build_document_ast
    from apex_one.editorial.architect import NarrativeArchitect
    from apex_one.editorial.voice import load_voice
    from apex_one.editorial.writer import APEXEgyptianWriter
    from apex_one.opportunity import OpportunityModeler
    from apex_one.reader_lab import build_reader_model

    st = researched_state()
    locks = [lk for lk in st.locks if lk.slot not in drop_slots]
    open_slots = sorted({c.slot for c in st.claims if c.status == ClaimStatus.NEEDS_HUMAN})
    opp = OpportunityModeler(locks, open_slots, today=date(2026, 10, 9)).build("Example Labor College")
    reader = build_reader_model(locks, QualityMode.ULTRA)
    plan = NarrativeArchitect(locks, opp, reader).plan()
    voice = load_voice()
    w = APEXEgyptianWriter(voice, locks, opp, institution="Example Labor College", cycle="Fall 2027", seed=seed,
                           synthetic=True)
    nodes = w.write(plan)
    ast = build_document_ast(nodes, institution="Example Labor College", cycle="Fall 2027", synthetic=True,
                             locks=locks, voice_version=voice.version)
    return {"locks": locks, "opp": opp, "reader": reader, "plan": plan, "voice": voice, "writer": w, "ast": ast}
