"""Load-test harness mechanics, hermetic (model call and Chromium stubbed): back-pressure, exactly-once restart
recovery, and render admission that reserves memory before it is allocated."""

import sqlite3
import time

from apex_one.lab import load_test as L


def _stub(monkeypatch):
    def fake_job(env, rec, broker):
        time.sleep(0.05)
        with sqlite3.connect(env.db, timeout=30) as c:
            c.execute("INSERT OR IGNORE INTO results VALUES (?, ?, ?)", (rec.jid, "2027-02-16", 1))
        rec.outcome_class, rec.state = "MEASURED", "DONE"
    monkeypatch.setattr(L, "run_job", fake_job)


def test_saturation_rejects_with_backpressure_instead_of_failing(tmp_path, monkeypatch):
    _stub(monkeypatch)
    env = L.Env("m", tmp_path / "r.db")
    jq = L.JobQueue(env, 2, 4, tmp_path / "j.json", lambda: None)
    accepted = [jq.submit(f"j{i}") for i in range(10)]
    assert accepted.count(True) == 4 and all(jq.recs[f"j{i}"].detail == "QUEUE_FULL" for i in range(4, 10))
    jq.start()
    jq.drain(60)
    assert sum(r.state == "DONE" for r in jq.recs.values()) == 4


def test_restart_recovery_runs_unfinished_jobs_exactly_once(tmp_path, monkeypatch):
    _stub(monkeypatch)
    env = L.Env("m", tmp_path / "r.db")
    jq = L.JobQueue(env, 1, 8, tmp_path / "j.json", lambda: None)
    jq.stop_after = 2
    for i in range(5):
        jq.submit(f"j{i}")
    jq.start()
    t0 = time.monotonic()
    while not jq.dead.is_set() and time.monotonic() - t0 < 30:
        time.sleep(0.05)
    states = {k: v.state for k, v in jq.recs.items()}
    assert states["j2"] == "RUNNING" and list(states.values()).count("DONE") == 2
    jq2 = L.JobQueue.resume(tmp_path / "j.json", L.Env("m", tmp_path / "r.db"), 1, lambda: None)
    jq2.start()
    jq2.drain(60)
    with sqlite3.connect(tmp_path / "r.db") as c:
        rows = [r[0] for r in c.execute("SELECT jid FROM results")]
    assert sorted(rows) == [f"j{i}" for i in range(5)]                      # every job once, none twice
    assert all(v.state == "DONE" for v in jq2.recs.values())


def test_render_admission_reserves_memory_before_chromium_allocates(tmp_path, monkeypatch):
    from apex_one.compute.local.resources import admit_increment

    monkeypatch.setattr(L, "available_gb", lambda: 4.0)
    monkeypatch.setattr(L, "admit_increment", lambda stage, need, mode, available=None:
                        admit_increment(stage, need, mode, available=available, total=16.9))
    env = L.Env("m", tmp_path / "r.db")
    first, second = env.try_reserve("render", 1.0), env.try_reserve("render", 1.0)
    assert first.admitted and not second.admitted and second.decision == "DEFER"   # 4.0 - 1.0 - 1.0 < 2.02
    env.release(1.0)
    assert env.try_reserve("render", 1.0).admitted
