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
    ("qwen3-vl-8b-q4kxl", ["acquire", "live", "calib", "pcalib", "invest", "council", "gdb", "vector",
                           *[f"robust:{w}" for w in ROBUST_WIDTHS]]),
    ("gemma3-12b-q4km", ["acquire", "live", "calib", "pcalib", "invest", "council", "gdb"]),
    ("qwen3-vl-4b-q4kxl", ["vector"]),
    ("gemma3-4b-q4km", ["vector"]),
    ("nemotron-3-nano-4b-q4km", ["vector"]),
]
VECTOR_TASKS = ("english_factual_writing", "structured_editorial")
PAGE_TYPES = ["Cover", "OpportunitySnapshot", "Timeline", "ApexTake", "Checklist"]
GOLDEN_JOB = os.environ.get("APEX_BENCH_JOB", "J-2da4830a2781")
# weights that may be removed (re-acquirable, digest recorded) to make disk room for the larger candidates,
# only after every step that needs them has finished
FREEABLE = {"gpt-oss-20b-mxfp4"}


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"done": {}, "failed": {}}

    def done(self, key: str) -> bool:
        return key in self.data["done"]

    def mark(self, key: str, info: object = None, failed: bool = False) -> None:
        (self.data["failed"] if failed else self.data["done"])[key] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                                       "info": info}
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
        (out / "run_meta.json").write_text(json.dumps({"exit_code": rc, "runtime_s": round(time.time() - t0),
                                                       "model": rid, "n_per_task": 10}))
        if rc != 0:
            raise RuntimeError(f"gdb exit {rc}")
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
    if step == "vector":
        from apex_one.compute.benchmark.council import rescore, run_council

        run_council(ComputeBroker(), [rid], bench, only=list(VECTOR_TASKS))
        return {t: rescore(bench)["models"].get(rid, {}).get(t) for t in VECTOR_TASKS}
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
    if step == "pages":
        from apex_one.lab.benchmarks.apex_design_bench import run_apex_design_bench

        s = run_apex_design_bench(GOLDEN_JOB, bench / "apex_design", [rid], only_types=PAGE_TYPES,
                                  include_native=False)
        return s["systems"].get(f"llm:{rid}")
    raise ValueError(step)


def main(max_steps: int | None = None) -> None:
    """Run pending steps; with max_steps, stop (exit cleanly, state saved) after that many steps."""
    from apex_one.compute.local import LocalServer, acquire, load_catalogue

    bench = get_settings().artifacts_dir / "bench"
    state = State(bench / "queue_state.json")
    _, specs = load_catalogue()
    for key, steps in PLAN:
        spec = specs[key]
        todo = [s for s in steps if not state.done(f"{key}:{s}")]
        if not todo:
            continue
        if "acquire" in todo:
            # make room: free re-acquirable weights whose every step is done
            for fk in FREEABLE:
                fsteps = next(s for k, s in PLAN if k == fk)
                ggufs = list(specs[fk].dir.glob("*.gguf"))
                if ggufs and all(state.done(f"{fk}:{s}") for s in fsteps) \
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
        try:
            srv.start(wait_s=1200)
        except Exception as e:  # noqa: BLE001
            log(f"{key}: server failed: {e}")
            state.mark(f"{key}:server", str(e)[:300], failed=True)
            continue
        try:
            for step in todo:
                if max_steps is not None and max_steps <= 0:
                    log("step budget used; stopping (re-run to continue)")
                    return
                if max_steps is not None:
                    max_steps -= 1
                log(f"{key}: {step} ...")
                try:
                    info = run_step(step, spec, bench)
                    state.mark(f"{key}:{step}", info)
                    log(f"{key}: {step} done {json.dumps(info, default=str)[:400]}")
                except Exception as e:  # noqa: BLE001
                    log(f"{key}: {step} FAILED {e}\n{traceback.format_exc()[-800:]}")
                    state.mark(f"{key}:{step}", str(e)[:300], failed=True)
        finally:
            srv.stop()
    log("ALL DONE")


if __name__ == "__main__":
    main(int(sys.argv[sys.argv.index("--max-steps") + 1]) if "--max-steps" in sys.argv else None)
