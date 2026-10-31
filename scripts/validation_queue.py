"""Resumable real-intelligence validation queue (one model in RAM at a time; survives container restarts).

Every step is idempotent and recorded in artifacts/bench/queue_state.json; re-running the script skips finished
steps. Steps per model, in order (only steps that apply to the model run):

  live      live structured test (stored for the provider report)
  gdb       GraphicDesignBench verification bundle, all available samples (vision models)
  calib     absolute (six-role council) calibration with raw scores + identity stamp (vision models)
  pcalib    pairwise calibration, same five cases, both orders (vision models)
  invest    vision contradiction experiments E1-E4 (vision models; E0 = calib)
  council   general council benchmark (new models only)
  rerun     council tasks whose output was empty, at a 4096-token budget
  pages     model writes APEX pages under the DOM contract (5 decision-critical page types)
  robust:W  vision-judge robustness at width W (5 cases x both orders x 3 repeats + legibility probe)
  vector    council tasks added for the capability vector (English factual writing, structured editorial),
            same 500-token task budget as the other prose tasks

Usage: python scripts/validation_queue.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from apex_one.settings import get_settings

ROBUST_WIDTHS = ("640", "320", "480", "768", "native", "1024")   # canonical first, then the sweep
PLAN = [
    ("qwen3-vl-4b-q4kxl", ["gdb", "calib", "pcalib", "invest", "pages"]),
    ("gemma3-4b-q4km", ["gdb", "calib", "pcalib", "invest", "pages"]),
    ("nemotron-3-nano-4b-q4km", ["rerun", "pages"]),
    ("gpt-oss-20b-mxfp4", ["rerun", "pages"]),
    ("qwen3-vl-8b-q4kxl", ["acquire", "live", "calib", "pcalib", "invest", "council", "robust:640", "gdb", "vector",
                           *[f"robust:{w}" for w in ROBUST_WIDTHS if w != "640"]]),
    # Gemma 3 12B: the SAME contracts as the 8B (calibration pages, prompts, checkers, 500-token council budget).
    # robust:640 = pair-order + 3-repeat stability at the canonical input; the other widths run only if 640 passes
    ("gemma3-12b-q4km", ["acquire", "live", "calib", "pcalib", "robust:640",
                         *[f"robust:{w}" for w in ROBUST_WIDTHS if w != "640"],
                         "invest", "council", "gdb", "pages"]),
    ("qwen3-vl-4b-q4kxl", ["vector"]),
    ("gemma3-4b-q4km", ["vector"]),
    ("nemotron-3-nano-4b-q4km", ["vector"]),
    ("qwen3-vl-8b-q4kxl", ["pages"]),          # native-vs-model page comparison (+ RAM record)
    # quantization question (every free remote multimodal route is egress-blocked or keyless): the SAME five cases,
    # canonical preprocessing, pair order, prompt and checker; widths beyond 640 only behind the pre-registered
    # material-improvement gate (material_improvement_gate). No absolute calibration: the question is pairwise.
    ("qwen3-vl-8b-q8kxl", ["acquire", "live", "pcalib", "robust:640", "robust:native",
                           *[f"robust:{w}" for w in ROBUST_WIDTHS if w not in ("640", "native")]]),
    # gpt-oss weights were freed for disk room: re-acquire (same digest) to measure the two writing tasks; a
    # reasoning model that spends the 500-token budget on hidden reasoning gets the documented 4096 re-run
    ("gpt-oss-20b-mxfp4", ["acquire", "vector", "rerun_vector"]),
]
VECTOR_TASKS = ("english_factual_writing", "structured_editorial")
PAGE_TYPES = ["Cover", "OpportunitySnapshot", "Timeline", "ApexTake", "Checklist"]
GOLDEN_JOB = os.environ.get("APEX_BENCH_JOB", "J-2da4830a2781")
# weights that may be removed (re-acquirable, digest recorded) to make disk room for the larger candidates,
# only after every step that needs them has finished
# Licence-blocked (evaluation-only) weights, re-acquirable by digest, freed only after ALL their steps and only when
# the next acquisition needs the room. Production-routed (Qwen3-VL 4B) and admitted-judge (Qwen3-VL 8B) weights are
# never freed: the router and the judge digest check need them on disk.
FREEABLE = {"gpt-oss-20b-mxfp4", "gemma3-12b-q4km", "gemma3-4b-q4km", "nemotron-3-nano-4b-q4km", "qwen3-vl-8b-q8kxl"}


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"done": {}, "failed": {}}

    def done(self, key: str) -> bool:
        return key in self.data["done"]

    def terminal(self, key: str) -> bool:
        """done, or refused by the resource scheduler (re-loading a model only to be refused again is waste;
        APEX_RETRY_BLOCKED=1 retries, e.g. on a machine with more RAM)."""
        f = (self.data["failed"].get(key) or {}).get("info")
        return self.done(key) or (isinstance(f, str) and f.startswith("RESOURCE_BLOCKED")
                                  and os.environ.get("APEX_RETRY_BLOCKED") != "1")

    def mark(self, key: str, info: object = None, failed: bool = False) -> None:
        # the code commit that produced the result (frozen snapshot run; see NEXT_ACTIONS.md)
        (self.data["failed"] if failed else self.data["done"])[key] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                                       "info": info,
                                                                       "commit": os.environ.get("APEX_RUN_COMMIT")}
        if not failed:
            self.data["failed"].pop(key, None)
        self.path.write_text(json.dumps(self.data, indent=2, default=str))


def stamp_calibration(calib: Path, section: str, model_id: str, result: dict) -> None:
    from datetime import UTC, datetime

    from apex_one.core.schemas.common import stable_hash
    from apex_one.vision.council import model_digest

    path = calib / "calibration_results.json"
    data = json.loads(path.read_text()) if path.exists() else {"models": {}}
    result.update({"at": datetime.now(UTC).isoformat(), "model_digest": model_digest(model_id),
                   "pages_hash": stable_hash((calib / "calibration_pages.json").read_text(encoding="utf-8"))})
    data.setdefault(section, {})[model_id] = result
    path.write_text(json.dumps(data, indent=2))


def server_memory(srv) -> dict[str, float] | None:
    """Resident memory of the llama-server process (Linux /proc): current and peak (VmHWM), in GB."""
    try:
        pid = int(srv.pidfile.read_text())
        st = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in
              Path(f"/proc/{pid}/status").read_text().splitlines() if ln.startswith(("VmRSS", "VmHWM")))}
        return {"rss_gb": round(st["VmRSS"] / 1e6, 2), "peak_rss_gb": round(st["VmHWM"] / 1e6, 2)}
    except (OSError, ValueError, KeyError):
        return None


def record_memory(state: "State", key: str, srv, when: str, extra: dict | None = None) -> None:
    mem = server_memory(srv)
    rec = dict((state.data["done"].get(f"{key}:ram") or {}).get("info") or {})
    if mem is not None:
        if when == "loaded":
            rec["loaded_rss_gb"] = mem["rss_gb"]
        rec["peak_rss_gb"] = max(rec.get("peak_rss_gb", 0.0), mem["peak_rss_gb"])
        rec.setdefault("peak_after_steps", []).append(when)
    if extra:     # scheduler accounting of the latest load/unload cycle
        rec["last_cycle"] = extra
        rec.setdefault("cycles", []).append(extra)
    rec["method"] = "llama-server /proc VmRSS after warm-up; VmHWM (peak) after each step; system MemTotal-MemAvailable"
    state.mark(f"{key}:ram", rec)


# A higher-precision build of an already-measured judge exists to answer ONE question: is the baseline's
# order/resolution failure caused by quantization? Pre-registered decision (fixed before the candidate ran):
# run the canonical width only; continue (native width, then the rest) ONLY if the candidate is MATERIALLY better
# there than the baseline on at least one of: defect discrimination (more correct in every repeat, e.g. 5/5),
# position bias (lower), order stability (fewer position-biased case-runs), legibility (reads what the baseline
# misread), repeat stability (fewer cases flipping, lower variance) — and no worse on discrimination. Otherwise
# stop: quantization is not the main limitation, and no sweep is run.
BASELINE_OF = {"qwen3-vl-8b-q8": "qwen3-vl-8b"}


def material_improvement(c: dict, b: dict) -> list[str]:
    better = []
    if c.get("min_correct", 0) > b.get("min_correct", 5):
        better.append(f"discrimination {c.get('correct_per_repeat')} vs {b.get('correct_per_repeat')}")
    if c.get("position_bias_rate", 1.0) < b.get("position_bias_rate", 0.0):
        better.append(f"position bias {c.get('position_bias_rate')} vs {b.get('position_bias_rate')}")
    if c.get("position_bias_cases", 99) < b.get("position_bias_cases", 0):
        better.append("order stability")
    if c.get("legible") and not b.get("legible"):
        better.append("legibility")
    if len(c.get("cases_flipping_across_repeats") or []) < len(b.get("cases_flipping_across_repeats") or []) \
            or c.get("run_variance", 9) < b.get("run_variance", 0):
        better.append("repeat stability")
    if c.get("min_correct", 0) < b.get("min_correct", 0):
        return []                      # worse discrimination cancels any other gain
    return better


def material_improvement_gate(rid: str, width: str) -> str | None:
    from apex_one.lab.benchmarks.vision_robustness import CANONICAL, load, summarize_width

    base = BASELINE_OF.get(rid)
    if base is None:
        return None
    mine, theirs = (load(rid) or {}).get("widths", {}), (load(base) or {}).get("widths", {})
    c, b = summarize_width(mine.get(CANONICAL, {})), summarize_width(theirs.get(CANONICAL, {}))
    gain = material_improvement(c, b)
    if not gain:
        return (f"no material improvement over {base} at {CANONICAL} px (candidate {c.get('correct_per_repeat')}, "
                f"bias {c.get('position_bias_rate')}; baseline {b.get('correct_per_repeat')}, bias "
                f"{b.get('position_bias_rate')}) — quantization is not the main limitation; sweep stopped "
                "(pre-registered)")
    if width != "native":
        n = summarize_width(mine.get("native", {}))
        if not n.get("reliable_all_repeats"):
            return f"native width not reliable for {rid} ({n.get('correct_per_repeat')}) — sweep stopped"
    return None


def run_step(step: str, spec, bench: Path) -> object:
    from apex_one.compute.broker import ComputeBroker

    rid, calib = spec.registry_model, bench / "vision_calibration"
    if step == "live":
        sys.path.insert(0, str(Path(__file__).parent))
        from run_local_council import record_local_live

        rec = record_local_live(spec)
        return {"status": rec.get("status"), "correct": rec.get("structured_correct")}
    if step == "gdb":
        import gdb

        out = bench / "gdb" / f"{spec.key}-full"
        out.mkdir(parents=True, exist_ok=True)
        cmd = [str(Path(sys.executable).parent / "gdb"), "eval", "--suite", "v0-smoke", "--dataset-root",
               str(Path(gdb.__file__).parent / "_verify_data"), "--n", "10", "--provider", "custom", "--custom-entry",
               "apex_one.lab.benchmarks.gdb_provider:APEXBrokerModel", "--custom-init-kwargs",
               json.dumps({"model_id": rid}), "--custom-modality", "text_and_image", "--output-dir", str(out),
               "--output", str(out / "report.json")]
        t0 = time.time()
        with (out / "gdb.log").open("w") as fh:      # cwd=out: GDB writes ./outputs relative to the cwd
            rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=out)
        import importlib.metadata

        from apex_one.lab.benchmarks.gdb_provider import GDB_PREPROCESS
        from apex_one.vision.council import model_digest

        (out / "run_meta.json").write_text(json.dumps({
            "exit_code": rc, "runtime_s": round(time.time() - t0), "model": rid, "n_per_task": 10,
            "model_digest": model_digest(rid), "gguf": spec.tag, "lica_gdb": importlib.metadata.version("lica-gdb"),
            "suite": "v0-smoke", "preprocess": GDB_PREPROCESS}))
        if rc != 0:
            raise RuntimeError(f"gdb exit {rc}")
        rep = json.loads((out / "report.json").read_text(encoding="utf-8")).get("results", {})
        failed = {t: r.get("failure_count") for t, pm in rep.items() for r in pm.values() if r.get("failure_count")}
        if failed:      # failed samples are not measurements: the run is reported, but the step is not done
            raise RuntimeError(f"gdb samples failed (not scored): {failed}")
        return {"exit": rc}
    if step == "calib":
        from apex_one.lab.benchmarks.vision_investigation import investigate

        rep = investigate(rid, calib, bench / "vision_investigation", experiments=("E0",))
        stamp_calibration(calib, "models", rid, dict(rep["E0"]["result"]))
        return {k: rep["E0"][k] for k in ("ties_on_target", "inversions_on_target", "distinct_scores")}
    if step == "pcalib":
        from apex_one.lab.benchmarks.vision_investigation import investigate

        rep = investigate(rid, calib, bench / "vision_investigation", experiments=("E1",))
        stamp_calibration(calib, "pairwise_models", rid, {k: v for k, v in rep["E1"].items() if k != "max_w"})
        from apex_one.vision.council import model_digest
        from apex_one.vision.judge_failures import remember

        remember(rid, rep["E1"], model_digest(rid))     # slot-following becomes a remembered failure pattern
        return {"correct": rep["E1"]["correct"], "valid": rep["E1"]["valid_checks"]}
    if step == "invest":
        from apex_one.lab.benchmarks.vision_investigation import investigate

        rep = investigate(rid, calib, bench / "vision_investigation", experiments=("E2", "E3", "E4"))
        return {k: {"correct": rep[k].get("correct"), "valid": rep[k].get("valid", rep[k].get("valid_checks"))}
                for k in ("E2", "E3", "E4") if k in rep}
    if step == "council":
        from apex_one.compute.benchmark.council import rescore, run_council

        run_council(ComputeBroker(), [rid], bench, calib_dir=calib if spec.vision else None)
        return rescore(bench)["models"].get(rid)
    if step.startswith("robust:"):
        from apex_one.lab.benchmarks.vision_robustness import CANONICAL, load, run_width, status

        width = step.split(":", 1)[1]
        if width != CANONICAL and status(load(rid))[0] == "UNQUALIFIED":
            # pre-registered: a judge that fails the canonical input is UNQUALIFIED whatever other widths show
            return {"not_run": f"canonical {CANONICAL} px failed: {status(load(rid))[1]}"}
        gate = material_improvement_gate(rid, width)
        if gate:
            return {"not_run": gate}
        return run_width(rid, calib, width)
    if step == "vector":
        from apex_one.compute.benchmark.council import rescore, run_council

        run_council(ComputeBroker(), [rid], bench, only=list(VECTOR_TASKS))
        got = {t: rescore(bench)["models"].get(rid, {}).get(t) for t in VECTOR_TASKS}
        if any(v is None for v in got.values()):
            raise RuntimeError(f"vector tasks not measured (call not executed or empty): {got}")
        return got
    if step == "rerun_vector":
        from apex_one.compute.benchmark.council import rescore, run_council

        missing = [t for t in VECTOR_TASKS if rescore(bench)["models"].get(rid, {}).get(t) is None]
        if missing:
            run_council(ComputeBroker(), [rid], bench, only=missing, max_tokens=4096)
        return {"rerun_tasks": missing, "scores": {t: rescore(bench)["models"].get(rid, {}).get(t) for t in VECTOR_TASKS}}
    if step == "rerun":
        from apex_one.compute.benchmark.council import rescore, run_council

        latest = {}
        for line in (bench / "council_runs.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                latest[(r["model"], r["task"])] = r
        tasks = [t for (m, t), r in latest.items() if m == rid and t != "visual_hierarchy"
                 and not (r.get("output") or "").strip()]
        if tasks:
            run_council(ComputeBroker(), [rid], bench, only=tasks, max_tokens=4096)
        return {"rerun_tasks": tasks, "scores": rescore(bench)["models"].get(rid)}
    if step in ("pages", "pages:generate", "pages:render"):
        from apex_one.lab.benchmarks.apex_design_bench import run_apex_design_bench

        phase = {"pages": "interleaved", "pages:generate": "generate", "pages:render": "render"}[step]
        s = run_apex_design_bench(GOLDEN_JOB, bench / "apex_design", [rid], only_types=PAGE_TYPES,
                                  include_native=False, phase=phase)
        return s if phase == "generate" else {**(s["systems"].get(f"llm:{rid}") or {}), "execution": phase}
    raise ValueError(step)


def single_instance(bench: Path):
    """Process-wide lock: two queue processes would load two models at once (2026-10-31 incident: a new chunk
    started while the previous one was still loading its next model). A second queue exits instead of waiting."""
    import fcntl

    bench.mkdir(parents=True, exist_ok=True)
    fh = (bench / "validation_queue.lock").open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another validation_queue process holds the lock — exiting (never two queues, never two models)")
        sys.exit(3)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def main(max_steps: int | None = None) -> None:
    """Run pending steps; with max_steps, stop (exit cleanly, state saved) after that many steps."""
    from apex_one.compute.local import LocalServer, acquire, load_catalogue
    from apex_one.compute.local.resources import (EVALUATION_MODE, ResourceBlocked, ScheduledServer,
                                                  SchedulerViolation, admit, baseline_capacity_gb,
                                                  last_recovery_ok, wait_stable)
    from apex_one.compute.local.supervisor import ServerSupervisor, register, unregister

    bench = get_settings().artifacts_dir / "bench"
    _lock = single_instance(bench)   # noqa: F841 — held for the life of the process
    state = State(bench / "queue_state.json")
    _, specs = load_catalogue()
    for key, steps in PLAN:
        spec = specs[key]
        todo = [s for s in steps if not state.terminal(f"{key}:{s}")]
        if not todo:
            continue
        if "acquire" in todo:
            # admission BEFORE downloading: a model the scheduler would refuse on an idle machine is not fetched
            first = next((x for x in todo if x != "acquire"), "load")
            pre = admit(spec, first, state.data, mode=EVALUATION_MODE, available=baseline_capacity_gb(), others=[])
            if pre.decision == "RESOURCE_BLOCKED":
                log(f"{key}: RESOURCE_BLOCKED before acquisition — {pre.reason} ({pre.estimate_source})")
                for step in todo:
                    state.mark(f"{key}:{step}", f"RESOURCE_BLOCKED: {pre.reason} ({pre.estimate_source})", failed=True)
                continue
            # make room: free re-acquirable weights whose every step is done
            for fk in FREEABLE:
                fsteps = [s for k, ss in PLAN if k == fk for s in ss]
                ggufs = list(specs[fk].dir.glob("*.gguf"))
                if ggufs and all(state.terminal(f"{fk}:{s}") for s in fsteps) \
                        and shutil.disk_usage(spec.dir.parent).free / 1e9 < spec.approx_gb + 3:
                    for g in ggufs:
                        log(f"freeing {g} ({g.stat().st_size / 1e9:.1f} GB; re-acquirable, digest kept)")
                        g.unlink()
                    man = specs[fk].dir / "apex_manifest.json"
                    if man.exists():   # no manifest -> the registry stops routing to the missing weights
                        man.rename(specs[fk].dir / "apex_manifest.freed.json")
                    state.mark(f"{fk}:weights_freed", {"reason": f"disk room for {key}"})
            try:
                acquire(spec, progress=log)
                state.mark(f"{key}:acquire")
            except Exception as e:  # noqa: BLE001
                log(f"{key}: acquire failed: {e}")
                state.mark(f"{key}:acquire", str(e)[:300], failed=True)
                continue
            todo.remove("acquire")
        if not (spec.dir / "apex_manifest.json").exists() or not list(spec.dir.glob("*.gguf")):
            log(f"{key}: weights not on disk — skipped")
            continue
        for other in specs.values():
            if other.key != key:
                LocalServer(other).stop()
        srv = LocalServer(spec)
        # resource scheduler (EVALUATION_MODE: one controlled benchmark process): ADMIT / DEFER / RESOURCE_BLOCKED
        # BEFORE loading, one large model at a time, and no load until the previous unload recovered its memory
        sched = ScheduledServer(srv, qstate=state.data, log_path=bench / "server_reliability" / "resources.jsonl",
                                mode=EVALUATION_MODE)
        recovered, why_rec = last_recovery_ok(state.data)
        try:
            dec = None
            for attempt in range(3):
                try:
                    dec = sched.load(stage=todo[0], wait_s=1200, recovery_ok=recovered)
                    break
                except ResourceBlocked as e:
                    if e.decision.decision != "DEFER" or attempt == 2:
                        raise
                    log(f"{key}: DEFER — {e.decision.reason}; waiting for memory to settle")
                    wait_stable()
                    recovered, why_rec = last_recovery_ok(state.data)
            log(f"{key}: ADMIT — {dec.reason}")
        except ResourceBlocked as e:
            log(f"{key}: {e}")
            if e.decision.decision == "DEFER":     # transient: retried by the next chunk, never marked failed
                log(f"{key}: deferred ({why_rec}); stopping this chunk")
                return
            for step in todo:
                state.mark(f"{key}:{step}", f"RESOURCE_BLOCKED: {e.decision.reason}", failed=True)
            continue
        except Exception as e:  # noqa: BLE001
            log(f"{key}: server failed: {e}")
            state.mark(f"{key}:server", str(e)[:300], failed=True)
            sched.unload()
            continue
        # every broker in this process now probes, restarts (bounded, with backoff + warm-up) and classifies
        # failures of this server; incidents -> artifacts/bench/server_reliability/events.jsonl
        sup = ServerSupervisor(key, srv, events_path=bench / "server_reliability" / "events.jsonl")
        register(spec.registry_model, sup)
        record_memory(state, key, srv, "loaded")
        render_after_unload = False
        try:
            for step in todo:
                if max_steps is not None and max_steps <= 0:
                    log("step budget used; stopping (re-run to continue)")
                    return
                if max_steps is not None:
                    max_steps -= 1
                run_as = step
                stage_ok = sched.admit_stage(step)
                if stage_ok.decision != "ADMIT" and step == "pages":
                    # model + Chromium do not fit together: sequential strategy B — generate every page with the
                    # model (no Chromium), unload the model, THEN render. Reserves are never weakened.
                    gen_ok = sched.admit_stage("pages:generate")
                    log(f"{key}: pages {stage_ok.decision} together with Chromium ({stage_ok.reason}); "
                        f"sequential strategy: generate {gen_ok.decision}")
                    if gen_ok.decision == "ADMIT":
                        run_as, stage_ok, render_after_unload = "pages:generate", gen_ok, True
                if stage_ok.decision != "ADMIT":
                    log(f"{key}: {step} {stage_ok.decision} — {stage_ok.reason}")
                    if stage_ok.decision == "RESOURCE_BLOCKED":
                        state.mark(f"{key}:{step}", f"RESOURCE_BLOCKED: {stage_ok.reason}", failed=True)
                    continue
                log(f"{key}: {run_as} ...")
                try:
                    sup.before_call()       # a dead server must fail the step, never yield empty "answers"
                    info = run_step(run_as, spec, bench)
                    state.mark(f"{key}:{run_as}" if run_as != step else f"{key}:{step}", info)
                    record_memory(state, key, srv, run_as)
                    log(f"{key}: {run_as} done {json.dumps(info, default=str)[:400]}")
                except Exception as e:  # noqa: BLE001
                    render_after_unload = False
                    log(f"{key}: {run_as} FAILED {e}\n{traceback.format_exc()[-800:]}")
                    state.mark(f"{key}:{run_as}", str(e)[:300], failed=True)
        finally:
            unregister(spec.registry_model)
            try:
                cycle = sched.unload()          # raises SchedulerViolation if the server still holds memory
                record_memory(state, key, srv, "unloaded", extra=cycle)
                log(f"{key}: unloaded {json.dumps(cycle)}")
            except SchedulerViolation as e:
                log(f"{key}: SCHEDULER VIOLATION {e}")
                state.mark(f"{key}:unload", str(e)[:300], failed=True)
                raise
        if "MEMORY_LEAK_OR_RESIDUAL" in cycle.get("flags", []):
            log(f"{key}: MEMORY_LEAK_OR_RESIDUAL (recovery {cycle.get('memory_recovery_ratio')}); no next model")
            state.mark(f"{key}:memory_recovery", cycle.get("memory_recovery_ratio"), failed=True)
            return
        if render_after_unload:          # strategy B, phase 2: Chromium alone, model unloaded
            rdec = admit(spec, "pages:render", state.data, mode=EVALUATION_MODE)
            log(f"{key}: pages:render {rdec.decision} — {rdec.reason}")
            if rdec.decision == "ADMIT":
                try:
                    info = run_step("pages:render", spec, bench)
                    state.mark(f"{key}:pages", {**info, "strategy": "B: generate -> unload model -> render"})
                    log(f"{key}: pages (sequential) done {json.dumps(info, default=str)[:300]}")
                except Exception as e:  # noqa: BLE001
                    state.mark(f"{key}:pages", str(e)[:300], failed=True)
            elif rdec.decision == "RESOURCE_BLOCKED":
                state.mark(f"{key}:pages", f"RESOURCE_BLOCKED: {rdec.reason}", failed=True)
    log("ALL DONE")


if __name__ == "__main__":
    main(int(sys.argv[sys.argv.index("--max-steps") + 1]) if "--max-steps" in sys.argv else None)
