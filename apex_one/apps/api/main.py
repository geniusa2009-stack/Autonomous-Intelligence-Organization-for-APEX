"""APEX ONE FastAPI service. Typed endpoints; never exposes secrets."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from apex_one import WORKFLOW_VERSION, __version__
from apex_one.core.schemas.mission import Job

app = FastAPI(title="APEX ONE ULTRA", version=__version__,
              description="Autonomous Research, Editorial, Design & Quality Intelligence Organization ($0 API cost)")
_locks: dict[str, threading.Lock] = {}


class CreateJob(BaseModel):
    opportunity: str = Field(..., examples=["Berea College Fall 2027"])
    quality: str = "ultra"
    budget: float = 0.0
    offline_fixture: str | None = None
    sources_dir: str | None = None
    seed: int = 20271
    run: bool = True


class Approval(BaseModel):
    approver: str
    notes: str = ""


class Preference(BaseModel):
    page_id: str
    ranking: list[str]
    reasons: list[str] = []
    annotator: str


class JobSummary(BaseModel):
    job_id: str
    state: str
    status: str
    opportunity: str
    blockers: list[str]


def _summary(job: Job) -> JobSummary:
    return JobSummary(job_id=job.job_id, state=job.state, status=job.status.value,
                      opportunity=job.mission.opportunity_name, blockers=job.blockers)


def _load(job_id: str):
    from apex_one.core.governor.runner import JobRunner

    try:
        return JobRunner.load(job_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


def _run(job_id: str) -> None:
    lock = _locks.setdefault(job_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        _load(job_id).run()
    finally:
        lock.release()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "workflow": WORKFLOW_VERSION}


@app.get("/ready")
def ready() -> dict:
    from apex_one.compute.hardware import find_chromium
    from apex_one.persistence.db import db_ready, init_db

    init_db()
    ok_db, chromium = db_ready(), find_chromium()
    if not ok_db:
        raise HTTPException(503, "database not migrated")
    return {"ready": True, "database": ok_db, "chromium": bool(chromium)}


@app.post("/jobs", response_model=JobSummary, status_code=201)
def create_job(body: CreateJob, background: BackgroundTasks) -> JobSummary:
    from apex_one.core.governor.runner import JobRunner

    if body.budget != 0.0:
        raise HTTPException(422, "APEX cost policy: budget must be 0")
    text = body.opportunity if body.opportunity.lower().startswith(("create", "make")) else \
        f"Create an APEX guide for {body.opportunity}"
    r = JobRunner.create(text, quality=body.quality, budget=body.budget, offline_fixture=body.offline_fixture,
                         sources=body.sources_dir, seed=body.seed)
    if body.run:
        background.add_task(_run, r.job.job_id)
    return _summary(r.job)


@app.get("/jobs/{job_id}", response_model=JobSummary)
def get_job(job_id: str) -> JobSummary:
    return _summary(_load(job_id).job)


@app.post("/jobs/{job_id}/resume", response_model=JobSummary)
def resume_job(job_id: str, background: BackgroundTasks) -> JobSummary:
    r = _load(job_id)
    background.add_task(_run, job_id)
    return _summary(r.job)


@app.post("/jobs/{job_id}/approve", response_model=JobSummary)
def approve_job(job_id: str, body: Approval) -> JobSummary:
    try:
        return _summary(_load(job_id).approve(body.approver, body.notes))
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/jobs/{job_id}/preferences")
def record_preference(job_id: str, body: Preference) -> dict:
    from apex_one.memory import PreferenceMemory

    pairs = PreferenceMemory().record_ranking(body.ranking, reasons=body.reasons, annotator=body.annotator,
                                              job_id=job_id, page_id=body.page_id)
    return {"pairs": len(pairs)}


@app.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str) -> dict:
    r = _load(job_id)
    return {"job_id": job_id, "artifacts": [a for a in r.ws.list_artifacts() if not a.startswith("design_candidates/")]}


@app.get("/jobs/{job_id}/artifacts/{path:path}")
def get_artifact(job_id: str, path: str):
    r = _load(job_id)
    target = (r.ws.root / path).resolve()
    if r.ws.root.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "artifact not found")
    return FileResponse(target)


@app.get("/providers")
def providers() -> list[dict]:
    from apex_one.apps.status import provider_status
    from apex_one.compute.registry import load_registry

    return provider_status(load_registry())


@app.get("/models")
def models(category: str | None = None) -> list[dict]:
    from apex_one.apps.status import model_status
    from apex_one.compute.registry import load_registry

    return model_status(load_registry(), category)


@app.get("/studio", response_class=HTMLResponse)
def studio() -> str:
    return (Path(__file__).resolve().parents[1] / "studio" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/jobs")
def list_jobs() -> list[JobSummary]:
    from sqlalchemy import select

    from apex_one.persistence.db import init_db, session_scope
    from apex_one.persistence.models import JobRow

    init_db()
    with session_scope() as s:
        rows = s.execute(select(JobRow).order_by(JobRow.created_at.desc()).limit(50)).scalars().all()
        return [JobSummary(job_id=r.job_id, state=r.state, status=r.status, opportunity=r.opportunity_name,
                           blockers=r.payload.get("blockers", [])) for r in rows]
