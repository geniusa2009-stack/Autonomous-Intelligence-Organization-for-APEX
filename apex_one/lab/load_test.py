"""Controlled local load test of PRODUCTION_MODE: the scheduler must throttle, never OOM.

`python -m apex_one.lab.load_test --model qwen3-vl-4b-q4kxl` (the production text model) — or `--fake` for the
fault-injection server (harness self-test; never counts as validation).

A job is production-shaped: (1) one structured model call through the ComputeBroker (purpose=production, the
supervised local server), (2) one real Chromium render of an APEX page to PDF, admitted by memory
(`admit_increment`, PRODUCTION_MODE headroom), (3) one SQLite write keyed by the job id (a retried job never
duplicates its side effect). Jobs go through a bounded, journalled queue served by a worker pool.

Scenarios: single_job, small_burst, concurrent_safe, queue_saturation, model_busy, renderer_busy, database_busy,
server_crash (our own server is SIGKILLed mid-queue; the supervisor restarts it), restart_recovery (the queue process
"dies" with jobs in flight; a new one resumes from the journal), memory_pressure (a bounded ballast leaves room for
one render; the others must wait). Measured per scenario: throughput, queue delay, latency, RAM (min MemAvailable,
peak server RSS), CPU, failure rate (by outcome class), recovery time, admission decisions.

Safety: the run is refused unless PRODUCTION_MODE admits the model; nothing else large may be resident; the ballast
never takes MemAvailable below the production headroom + 0.5 GB; a sampler flags the run if MemAvailable falls under
the evaluation headroom. The scheduler kills only the server this harness started.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import queue
import signal
import sqlite3
import statistics
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apex_one.compute.local.resources import (
    CHROMIUM_MEASURED_PEAK_GB,
    EVALUATION_MODE,
    PRODUCTION_MODE,
    admit_increment,
    available_gb,
    llama_servers,
    proc_rss_gb,
    required_headroom,
    swap_used_gb,
)

LOAD_TEST_VERSION = 1     # job shape + the ten scenarios + their PASS checks (module docstring)
RENDER_NEED_GB = 2 * CHROMIUM_MEASURED_PEAK_GB     # same reserve as the PLAYWRIGHT_RENDER profile
REQUEST_NEED_GB = 0.05                              # request buffers; the KV cache is allocated at load
PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>
body{font-family:sans-serif;margin:24mm} h1{color:#0A1A33;font-size:28pt} .fact{font-size:16pt;margin:6mm 0}
</style></head><body><h1>دليل APEX — اختبار الحمل {jid}</h1>
<p class="fact">آخر ميعاد للتقديم: {deadline}</p><p class="fact">Load-test page {jid}</p></body></html>"""
PROMPT = ('Extract the application deadline from this text and return ONLY JSON {"deadline": "YYYY-MM-DD"}.\n'
          "Text: Applications for the {jid} cohort close on 16 February 2027 at 23:59 UTC.")


def out_dir() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "bench" / "load_test"


# ---------------------------------------------------------------- system sampler

class Sampler(threading.Thread):
    def __init__(self, server_pid=lambda: None, floor_gb: float = 0.0, interval: float = 0.25):
        super().__init__(daemon=True)
        self.server_pid, self.floor, self.interval = server_pid, floor_gb, interval
        self.stop_evt, self.min_avail, self.swap_peak, self.server_peak = threading.Event(), float("inf"), 0.0, 0.0
        self.cpu: list[float] = []
        self.breached = False

    @staticmethod
    def _cpu() -> tuple[int, int]:
        vals = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return sum(vals), vals[3] + vals[4]

    def run(self) -> None:
        last = self._cpu()
        while not self.stop_evt.wait(self.interval):
            a = available_gb()
            self.min_avail = min(self.min_avail, a)
            self.swap_peak = max(self.swap_peak, swap_used_gb())
            pid = self.server_pid()
            mem = proc_rss_gb(pid) if pid else None
            if mem:
                self.server_peak = max(self.server_peak, mem["rss_gb"])
            now = self._cpu()
            dt, di = now[0] - last[0], now[1] - last[1]
            if dt > 0:
                self.cpu.append(100.0 * (dt - di) / dt)
            last = now
            if a < self.floor:
                self.breached = True

    def snapshot(self) -> dict[str, Any]:
        return {"min_available_gb": round(self.min_avail, 2) if self.min_avail != float("inf") else None,
                "swap_peak_gb": round(self.swap_peak, 2), "server_peak_rss_gb": round(self.server_peak, 2),
                "cpu_avg_pct": round(statistics.mean(self.cpu), 1) if self.cpu else None,
                "cpu_max_pct": round(max(self.cpu), 1) if self.cpu else None}


# ---------------------------------------------------------------- the job and its queue

@dataclass
class JobRec:
    jid: str
    submitted: float
    started: float | None = None
    ended: float | None = None
    state: str = "QUEUED"            # QUEUED | RUNNING | DONE | FAILED | REJECTED
    outcome_class: str | None = None
    failure_kind: str | None = None
    detail: str = ""
    stage_s: dict[str, float] = field(default_factory=dict)
    render_waits: int = 0


class Env:
    """Shared resources of one harness run."""

    def __init__(self, model_id: str, db: Path, render_pool: int = 4, render_wait_s: float = 120.0):
        self.model_id, self.db = model_id, db
        self.render_sem = threading.BoundedSemaphore(render_pool)
        self.render_wait_s = render_wait_s
        self.admissions: dict[str, int] = {"ADMIT": 0, "DEFER": 0}
        self._lock = threading.Lock()
        # admitted-but-not-yet-allocated stages: without this, N workers could all pass admission before any
        # Chromium has allocated. Held until the stage ends (double-counts while it runs: conservative by design)
        self.reserved_gb = 0.0
        with sqlite3.connect(db) as c:
            c.execute("CREATE TABLE IF NOT EXISTS results (jid TEXT PRIMARY KEY, deadline TEXT, pdf_bytes INTEGER)")

    def try_reserve(self, stage: str, need_gb: float):
        with self._lock:
            dec = admit_increment(stage, need_gb, PRODUCTION_MODE, available=available_gb() - self.reserved_gb)
            self.admissions[dec.decision] = self.admissions.get(dec.decision, 0) + 1
            if dec.admitted:
                self.reserved_gb += need_gb
            return dec

    def release(self, need_gb: float) -> None:
        with self._lock:
            self.reserved_gb = max(0.0, self.reserved_gb - need_gb)


def run_job(env: Env, rec: JobRec, broker) -> None:
    from apex_one.compute.local.supervisor import outcome_class
    from apex_one.compute.providers.base import ChatMessage
    from apex_one.core.schemas.compute import CapabilityRequest

    t = time.monotonic()
    res = broker.complete(CapabilityRequest(task="evidence.extract", purpose="production", model_id=env.model_id),
                          [ChatMessage(role="user", content=PROMPT.replace("{jid}", rec.jid))], json_mode=True,
                          max_tokens=48, temperature=0.0, timeout=180)
    rec.stage_s["model"] = round(time.monotonic() - t, 2)
    if not res.executed or not (res.text or "").strip():
        from apex_one.compute.benchmark.council import call_failure_kind

        rec.failure_kind = call_failure_kind(res) or "EMPTY_OUTPUT"
        rec.outcome_class, rec.state, rec.detail = "INFRASTRUCTURE_ERROR", "FAILED", "model call not executed"
        return
    try:
        deadline = json.loads(res.text)["deadline"]
    except (ValueError, KeyError, TypeError):
        rec.outcome_class, rec.state, rec.detail = outcome_class(0.0, None).value, "FAILED", f"bad JSON {res.text[:60]}"
        return
    t = time.monotonic()                     # render: memory admission first, then a bounded renderer pool
    while True:
        dec = env.try_reserve("render", RENDER_NEED_GB)
        if dec.admitted:
            break
        rec.render_waits += 1
        if time.monotonic() - t > env.render_wait_s:
            rec.outcome_class, rec.failure_kind, rec.state = "INFRASTRUCTURE_ERROR", "RESOURCE_BLOCKED", "FAILED"
            rec.detail = f"render throttled for {env.render_wait_s:.0f} s: {dec.reason}"
            return
        time.sleep(0.5)
    try:
        with env.render_sem:
            from playwright.sync_api import sync_playwright

            from apex_one.compute.hardware import find_chromium

            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=find_chromium())
                pg = b.new_page()
                pg.set_content(PAGE.replace("{jid}", rec.jid).replace("{deadline}", str(deadline)))
                pdf = pg.pdf(format="A4")
                b.close()
    finally:
        env.release(RENDER_NEED_GB)
    rec.stage_s["render"] = round(time.monotonic() - t, 2)
    t = time.monotonic()
    with sqlite3.connect(env.db, timeout=30) as c:      # busy_timeout: wait for a locked DB, never fail fast
        c.execute("INSERT OR IGNORE INTO results VALUES (?, ?, ?)", (rec.jid, str(deadline), len(pdf)))
    rec.stage_s["db"] = round(time.monotonic() - t, 2)
    rec.outcome_class, rec.state = "MEASURED", "DONE"


class JobQueue:
    """Bounded queue + worker pool + a journal (restart recovery: unfinished jobs re-run; finished never re-run)."""

    def __init__(self, env: Env, workers: int, max_queue: int, journal: Path, broker_factory):
        self.env, self.q, self.journal = env, queue.Queue(maxsize=max_queue), journal
        self.recs: dict[str, JobRec] = {}
        self.workers = [threading.Thread(target=self._work, args=(broker_factory(),), daemon=True)
                        for _ in range(workers)]
        self.stop_after: int | None = None       # restart drill: the "process" dies after N started jobs
        self._started = 0
        self._lock = threading.Lock()
        self.dead = threading.Event()

    def _journal(self) -> None:
        with self._lock:
            self.journal.write_text(json.dumps({k: v.__dict__ for k, v in self.recs.items()}, indent=1))

    def submit(self, jid: str) -> bool:
        rec = JobRec(jid, time.monotonic())
        try:
            self.q.put_nowait(rec)
        except queue.Full:                     # back-pressure: the caller is told to retry later
            rec.state, rec.detail = "REJECTED", "QUEUE_FULL"
            self.recs[jid] = rec
            return False
        self.recs[jid] = rec
        self._journal()
        return True

    def start(self) -> None:
        for w in self.workers:
            w.start()

    def _work(self, broker) -> None:
        while not self.dead.is_set():
            try:
                rec = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            with self._lock:
                self._started += 1
                crash = self.stop_after is not None and self._started > self.stop_after
            if crash:                           # simulated process death: this job stays RUNNING in the journal
                rec.state, rec.started = "RUNNING", time.monotonic()
                self._journal()
                self.dead.set()
                self.q.task_done()
                return
            rec.state, rec.started = "RUNNING", time.monotonic()
            self._journal()
            try:
                run_job(self.env, rec, broker)
            except Exception as e:  # noqa: BLE001 — an unexpected harness error is infrastructure, never a score
                rec.state, rec.outcome_class, rec.detail = "FAILED", "INFRASTRUCTURE_ERROR", str(e)[:200]
                rec.failure_kind = rec.failure_kind or "UNKNOWN_FAILURE"
            rec.ended = time.monotonic()
            self._journal()
            self.q.task_done()

    def drain(self, timeout: float = 1800) -> None:
        t0 = time.monotonic()
        while self.q.unfinished_tasks and not self.dead.is_set() and time.monotonic() - t0 < timeout:
            time.sleep(0.2)

    @classmethod
    def resume(cls, journal: Path, env: Env, workers: int, broker_factory) -> JobQueue:
        old = json.loads(journal.read_text())
        jq = cls(env, workers, 10_000, journal, broker_factory)
        for jid, r in old.items():
            if r["state"] in ("QUEUED", "RUNNING"):
                jq.submit(jid)                  # re-run: the DB write is idempotent on the job id
            else:
                jq.recs[jid] = JobRec(**{k: v for k, v in r.items()})
        return jq


# ---------------------------------------------------------------- scenarios

def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, round(p * (len(xs) - 1)))], 2)


def summarize(name: str, jq: JobQueue, t0: float, t1: float, sampler: Sampler, extra: dict[str, Any] | None = None,
              max_failure_rate: float = 0.0) -> dict[str, Any]:
    recs = list(jq.recs.values())
    ran = [r for r in recs if r.state in ("DONE", "FAILED")]
    done = [r for r in recs if r.state == "DONE"]
    failed = [r for r in recs if r.state == "FAILED"]
    qd = [r.started - r.submitted for r in ran if r.started]
    lat = [r.ended - r.started for r in ran if r.ended and r.started]
    snap = sampler.snapshot()
    rate = round(len(failed) / len(ran), 3) if ran else None
    floor = required_headroom(EVALUATION_MODE)
    checks = {"infrastructure_failures_never_scored": all(r.outcome_class == "INFRASTRUCTURE_ERROR"
                                                          for r in failed if r.failure_kind),
              "failure_rate_within_bound": rate is not None and rate <= max_failure_rate,
              "memory_floor_held": not sampler.breached and (snap["min_available_gb"] or 0) >= floor,
              "no_swap": snap["swap_peak_gb"] == 0.0}
    return {"scenario": name, "jobs_submitted": len(recs), "jobs_run": len(ran), "done": len(done),
            "failed": len(failed), "rejected_backpressure": sum(r.state == "REJECTED" for r in recs),
            "failure_rate": rate, "failures_by_kind": _count(r.failure_kind for r in failed),
            "outcome_classes": _count(r.outcome_class for r in ran),
            "throughput_jobs_per_min": round(60 * len(done) / max(t1 - t0, 1e-6), 2),
            "queue_delay_s": {"p50": _pct(qd, 0.5), "p95": _pct(qd, 0.95), "max": _pct(qd, 1.0)},
            "latency_s": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "max": _pct(lat, 1.0)},
            "model_s_p50": _pct([r.stage_s.get("model", 0) for r in done], 0.5),
            "render_s_p50": _pct([r.stage_s.get("render", 0) for r in done], 0.5),
            "db_s_max": _pct([r.stage_s.get("db", 0) for r in done], 1.0),
            "render_throttle_waits": sum(r.render_waits for r in recs),
            "admissions": dict(jq.env.admissions), "duration_s": round(t1 - t0, 1), **snap,
            "required_production_headroom_gb": round(required_headroom(PRODUCTION_MODE), 2),
            "checks": checks, "verdict": "PASS" if all(checks.values()) else "FAIL", **(extra or {})}


def _count(it) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in it:
        if x:
            out[x] = out.get(x, 0) + 1
    return out


def run_scenario(name: str, env_args: dict[str, Any], n: int, workers: int, max_queue: int, broker_factory,
                 server_pid, setup=None, max_failure_rate: float = 0.0, extra_fn=None) -> dict[str, Any]:
    d = out_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*"):
        f.unlink()
    env = Env(db=d / "results.db", **env_args)
    jq = JobQueue(env, workers, max_queue, d / "journal.json", broker_factory)
    sampler = Sampler(server_pid, floor_gb=required_headroom(EVALUATION_MODE))
    sampler.start()
    ctx = setup(env, jq) if setup else {}
    t0 = time.monotonic()
    for i in range(n):
        jq.submit(f"{name}-{i:03d}")
    jq.start()
    jq.drain()
    extra = extra_fn(env, jq, ctx) if extra_fn else {}
    t1 = time.monotonic()
    sampler.stop_evt.set()
    sampler.join(timeout=5)
    if ctx.get("cleanup"):
        ctx["cleanup"]()
    rep = summarize(name, jq, t0, t1, sampler, extra, max_failure_rate)
    (d / "summary.json").write_text(json.dumps(rep, indent=2))
    return rep


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-vl-4b-q4kxl", help="local model key (the production text model)")
    ap.add_argument("--fake", action="store_true", help="fault-injection server instead (harness self-test only)")
    ap.add_argument("--only", default="", help="comma-separated scenario names")
    a = ap.parse_args(argv)
    out_dir().mkdir(parents=True, exist_ok=True)
    lock = (out_dir().parent / "validation_queue.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)     # never alongside the validation queue
    except BlockingIOError:
        raise SystemExit("another benchmark/queue process holds the lock; not starting") from None
    from apex_one.compute.broker import ComputeBroker
    from apex_one.compute.local import load_catalogue
    from apex_one.compute.local.resources import ScheduledServer
    from apex_one.compute.local.server import LocalServer
    from apex_one.compute.local.supervisor import (
        ServerSupervisor,
        SupervisorPolicy,
        register,
        unregister,
    )

    if llama_servers():
        raise SystemExit(f"a model server is already resident: {llama_servers()} — refusing (never two large models)")
    _, specs = load_catalogue()
    spec = specs[a.model]
    if a.fake:
        raise SystemExit("--fake: use tests/test_load_test.py (the harness self-test); a fake run never validates")
    srv = LocalServer(spec)
    sched = ScheduledServer(srv, mode=PRODUCTION_MODE)
    try:
        dec = sched.load(stage="pages")      # MODEL_PLUS_CHROMIUM: renders run beside the resident model
    except Exception as e:  # noqa: BLE001 — ResourceBlocked: a clean refusal is the result
        rep = {"verdict": "RESOURCE_BLOCKED", "model": a.model, "real_model": True, "reason": str(e)}
        (out_dir() / "report.json").write_text(json.dumps(rep, indent=2))
        return rep
    events = out_dir() / "server_events.jsonl"
    if events.exists():        # one event log per run: recovery is never measured against an older run's failure
        events.rename(out_dir() / f"server_events.{int(time.time())}.jsonl")
    sup = ServerSupervisor(spec.registry_model, srv, policy=SupervisorPolicy(backoff_s=(1.0, 4.0, 10.0)),
                           events_path=events)
    register(spec.registry_model, sup)
    pid = lambda: srv.proc.pid if srv.proc and srv.proc.poll() is None else None

    def factory():
        return ComputeBroker(supervisors={spec.registry_model: sup})
    base = {"model_id": spec.registry_model}
    results: list[dict[str, Any]] = []
    only = {x for x in a.only.split(",") if x}

    def go(name, **kw):
        if only and name not in only:
            return
        results.append(run_scenario(name, {**base, **kw.pop("env", {})}, broker_factory=factory, server_pid=pid,
                                    **kw))
        print(json.dumps({k: results[-1][k] for k in ("scenario", "verdict", "done", "failed", "duration_s")}),
              flush=True)

    try:
        go("single_job", n=1, workers=1, max_queue=4)
        go("small_burst", n=5, workers=2, max_queue=8)
        go("concurrent_safe", n=6, workers=3, max_queue=8)
        go("queue_saturation", n=20, workers=2, max_queue=6,
           extra_fn=lambda e, q, c: {"backpressure_is_not_failure": True})
        go("model_busy", n=4, workers=4, max_queue=8)                 # 1 server slot: requests queue at the model
        go("renderer_busy", n=4, workers=4, max_queue=8, env={"render_pool": 1})

        def db_lock(env, jq):
            conn = sqlite3.connect(env.db, timeout=1, check_same_thread=False)
            conn.execute("BEGIN EXCLUSIVE")
            threading.Timer(8.0, conn.rollback).start()             # the DB is held busy for 8 s mid-run
            return {"cleanup": conn.close}
        go("database_busy", n=3, workers=3, max_queue=8, setup=db_lock)

        def crash(env, jq):
            def kill():
                time.sleep(3.0)
                p = pid()
                if p:
                    ctx["killed_at"] = time.monotonic()
                    os.kill(p, signal.SIGKILL)                       # OUR server only (exact PID we started)
            ctx: dict[str, Any] = {}
            threading.Thread(target=kill, daemon=True).start()
            return ctx

        def recovery(env, jq, ctx):
            ok = [json.loads(x) for x in events.read_text().splitlines()] if events.exists() else []
            rec = [e for e in ok if e["event"] == "recovered"]
            return {"server_killed": "killed_at" in ctx, "restarts": sup.restarts,
                    "recovery_events": len(rec), "supervisor_events": _count(e["event"] for e in ok)}
        t_crash = time.time()
        go("server_crash", n=4, workers=2, max_queue=8, setup=crash, extra_fn=recovery, max_failure_rate=0.25)
        if results and results[-1]["scenario"] == "server_crash":
            results[-1]["recovery_time_s"] = _recovery_time(events, t_crash)

        if not only or "restart_recovery" in only:
            results.append(restart_recovery(base, factory, pid))
            print(json.dumps({k: results[-1][k] for k in ("scenario", "verdict", "done", "failed")}), flush=True)
        if not only or "memory_pressure" in only:
            results.append(memory_pressure(base, factory, pid))
            print(json.dumps({k: results[-1][k] for k in ("scenario", "verdict", "done", "failed")}), flush=True)
    finally:
        unregister(spec.registry_model)
        cycle = sched.unload()
    for r in results:              # provenance per scenario: --only reruns mix runs from different commits
        r.setdefault("commit", os.environ.get("APEX_RUN_COMMIT"))
        r.setdefault("run_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    prev = json.loads((out_dir() / "report.json").read_text()) if only and (out_dir() / "report.json").exists() else {}
    if prev.get("scenarios"):      # --only re-runs a scenario: replace it, keep the others' measured results
        fresh = {r["scenario"] for r in results}
        results = [r for r in prev["scenarios"] if r["scenario"] not in fresh] + results
    verdict = "PASS" if results and all(r["verdict"] == "PASS" for r in results) else "FAIL"
    rep = {"verdict": verdict, "model": a.model, "real_model": True, "mode": PRODUCTION_MODE,
           "admission": dec.as_dict(), "scenarios": results, "memory_cycle": cycle,
           "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "commit": os.environ.get("APEX_RUN_COMMIT")}
    (out_dir() / "report.json").write_text(json.dumps(rep, indent=2))
    lock.close()
    return rep


def _recovery_time(events: Path, since: float) -> float | None:
    if not events.exists():
        return None
    ev = [json.loads(x) for x in events.read_text().splitlines()]
    from datetime import datetime

    def t(e: dict[str, Any]) -> float:
        return datetime.fromisoformat(e["at"]).timestamp()
    ev = [e for e in ev if t(e) >= since]
    starts = [e for e in ev if e["event"] in ("unhealthy_before_call", "call_failed")]
    rec = [e for e in ev if e["event"] == "recovered" and t(e) >= t(starts[0])] if starts else []
    if not starts or not rec:
        return None
    return round(t(rec[0]) - t(starts[0]), 1)     # first failure seen -> first recovery after it


def restart_recovery(base: dict[str, Any], factory, pid) -> dict[str, Any]:
    """The queue process dies after 2 jobs started (one left RUNNING); a new process resumes from the journal."""
    d = out_dir() / "restart_recovery"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*"):
        f.unlink()
    env = Env(db=d / "results.db", **base)
    jq = JobQueue(env, 1, 8, d / "journal.json", factory)
    jq.stop_after = 2
    sampler = Sampler(pid, floor_gb=required_headroom(EVALUATION_MODE))
    sampler.start()
    t0 = time.monotonic()
    for i in range(5):
        jq.submit(f"restart-{i:03d}")
    jq.start()
    while not jq.dead.is_set() and time.monotonic() - t0 < 900:
        time.sleep(0.2)
    before = {k: v.state for k, v in jq.recs.items()}
    t_resume = time.monotonic()
    jq2 = JobQueue.resume(d / "journal.json", Env(db=d / "results.db", **base), 1, factory)
    jq2.start()
    jq2.drain()
    t1 = time.monotonic()
    sampler.stop_evt.set()
    sampler.join(timeout=5)
    with sqlite3.connect(d / "results.db") as c:
        rows = [r[0] for r in c.execute("SELECT jid FROM results")]
    extra = {"states_at_crash": before, "db_rows": len(rows), "duplicate_side_effects": len(rows) - len(set(rows)),
             "recovery_time_s": round(t1 - t_resume, 1)}
    rep = summarize("restart_recovery", jq2, t0, t1, sampler, extra)
    rep["checks"]["exactly_once_side_effects"] = len(rows) == 5 and extra["duplicate_side_effects"] == 0
    rep["verdict"] = "PASS" if all(rep["checks"].values()) else "FAIL"
    (d / "summary.json").write_text(json.dumps(rep, indent=2))
    return rep


def _ballast(gb: float) -> bytearray:
    b = bytearray(int(max(gb, 0.0) * 1e9))
    mv = memoryview(b)
    for i in range(0, len(b), 4096):           # touch every page so the memory is really committed
        mv[i] = 1
    mv.release()
    return b


def memory_pressure(base: dict[str, Any], factory, pid) -> dict[str, Any]:
    """Memory is squeezed until not even ONE render fits under the production headroom: every render must wait
    (DEFER) — never start and hope. After 15 s part of the squeeze is released and the waiting renders proceed.
    Bounded: the squeeze never leaves less than the production headroom + 0.5 GB free (above the evaluation floor),
    and the scenario PASSES only if the throttle actually engaged."""
    req = required_headroom(PRODUCTION_MODE)
    squeeze_free = req + 0.5                    # < req + RENDER_NEED_GB: no render can be admitted
    release_gb = 1.6                            # after release: room for one render at a time
    total = available_gb() - squeeze_free
    if total <= release_gb:
        return {"scenario": "memory_pressure", "verdict": "FAIL", "done": 0, "failed": 0,
                "reason": f"cannot squeeze safely: only {available_gb():.1f} GB free"}
    hold = [_ballast(release_gb), _ballast(total - release_gb)]
    released: dict[str, float] = {}

    def release():
        hold[0] = bytearray()                    # free the first part: memory becomes available again
        released["at"] = time.monotonic()
    timer = threading.Timer(15.0, release)
    try:
        timer.start()
        rep = run_scenario("memory_pressure", {**base, "render_wait_s": 300.0}, n=4, workers=4, max_queue=8,
                           broker_factory=factory, server_pid=pid,
                           extra_fn=lambda e, q, c: {"ballast_gb": round(total, 2), "released_gb": release_gb,
                                                     "free_during_squeeze_target_gb": round(squeeze_free, 2)})
        rep["checks"]["throttle_engaged"] = rep["admissions"].get("DEFER", 0) > 0 and rep["render_throttle_waits"] > 0
        rep["checks"]["all_jobs_completed_after_release"] = rep["done"] == 4
        rep["verdict"] = "PASS" if all(rep["checks"].values()) else "FAIL"
        (out_dir() / "memory_pressure" / "summary.json").write_text(json.dumps(rep, indent=2))
        return rep
    finally:
        timer.cancel()
        hold.clear()


if __name__ == "__main__":
    rep = main()
    print(json.dumps({k: rep.get(k) for k in ("verdict", "model", "reason")}))
