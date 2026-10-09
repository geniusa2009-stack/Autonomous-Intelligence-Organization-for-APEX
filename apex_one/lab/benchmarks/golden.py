"""Golden end-to-end benchmark: SYNTHETIC Berea-style guide (no real Berea facts).

Proves: evidence -> locked facts -> narrative -> Document AST -> design intent -> multiple layouts ->
render -> QA -> quality decision -> human release gate. The human approval step is NOT simulated here.
"""

from __future__ import annotations

from typing import Any

from apex_one.core.governor.runner import JobRunner
from apex_one.core.schemas.mission import JobStatus

MISSION = "Create an APEX guide for Example Labor College Fall 2027"
EXPECTED_LOCKS = {"deadline.application": "2026-11-01", "fee.application": "USD 0", "test_minimum.toefl_ibt": "80",
                  "test_minimum.ielts": "6.5", "test_requirement.sat_act": "false",
                  "scholarship_coverage.tuition": "100%", "funding.student_contribution_per_year": "USD 1000"}


def run_golden(quality: str = "standard", seed: int = 20271, log=None) -> dict[str, Any]:
    r = JobRunner.create(MISSION, quality=quality, offline_fixture="synthetic_berea_style", seed=seed, log=log)
    job = r.run()
    locks = {lk.slot: lk.value.canonical for lk in r.rd.state.locks}
    checks = {f"lock:{k}": locks.get(k) == v for k, v in EXPECTED_LOCKS.items()}
    checks["stale_cycle_rejected"] = any(c.freshness == "previous-cycle" for c in r.rd.state.claims)
    checks["blog_values_rejected"] = locks.get("fee.application") == "USD 0"
    checks["stops_at_human_gate"] = job.state == "HUMAN_APPROVAL" and job.status == JobStatus.RELEASE_CANDIDATE
    checks["not_final_without_human"] = job.status != JobStatus.FINAL
    q = r.ws.read_json("quality_report.json") if r.ws.exists("quality_report.json") else {}
    checks["critical_gates_pass"] = all(g["status"] == "PASS" for g in q.get("gates", []) if g["kind"] == "critical")
    search = r.ws.read_json("layout_search.json") if r.ws.exists("layout_search.json") else []
    checks["multiple_layouts_evaluated"] = sum(x["evaluated"] for x in search) >= 2 * max(1, len(search))
    return {"job_id": job.job_id, "state": job.state, "status": job.status.value, "checks": checks,
            "all_passed": all(checks.values()),
            "targets": {g["gate"]: (g["status"], g["metric"]["value"]) for g in q.get("gates", []) if g["kind"] == "target"},
            "artifacts": str(r.ws.root)}
