"""Background worker: runs PENDING/QUEUED jobs. Queued jobs wait for free capacity, never for payment."""

from __future__ import annotations

import time

from sqlalchemy import select

from apex_one.core.governor.runner import JobRunner
from apex_one.persistence.db import init_db, session_scope
from apex_one.persistence.models import JobRow


def pending_jobs() -> list[str]:
    with session_scope() as s:
        return [r.job_id for r in s.execute(select(JobRow).where(JobRow.status.in_(["PENDING", "QUEUED"]))).scalars()]


def work(once: bool = False, interval: float = 30.0) -> None:
    init_db()
    while True:
        for job_id in pending_jobs():
            JobRunner.load(job_id).run()
        if once:
            return
        time.sleep(interval)
