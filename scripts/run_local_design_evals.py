"""Second local evaluation stage (run after scripts/run_local_council.py; one model in RAM at a time):

1. GraphicDesignBench smoke (lica-gdb verification bundle) for vision models, through the APEX broker.
2. APEX design bench: the model writes pages itself under the APEX DOM contract (5 decision-critical page types).

Usage: python scripts/run_local_design_evals.py [--wait-for <council log>] [model_key ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from apex_one.compute.local import LocalServer, load_catalogue
from apex_one.lab.benchmarks.apex_design_bench import run_apex_design_bench
from apex_one.settings import get_settings

ORDER = ["gemma3-4b-q4km", "qwen3-vl-4b-q4kxl", "nemotron-3-nano-4b-q4km", "gpt-oss-20b-mxfp4"]
PAGE_TYPES = ["Cover", "OpportunitySnapshot", "Timeline", "ApexTake", "Checklist"]
GOLDEN_JOB = os.environ.get("APEX_BENCH_JOB", "J-2da4830a2781")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def gdb_smoke(key: str, model_id: str, out: Path) -> None:
    import gdb

    bundle = Path(gdb.__file__).parent / "_verify_data"
    cmd = [str(Path(sys.executable).parent / "gdb"), "eval", "--suite", "v0-smoke", "--dataset-root", str(bundle),
           "--provider", "custom", "--custom-entry", "apex_one.lab.benchmarks.gdb_provider:APEXBrokerModel",
           "--custom-init-kwargs", json.dumps({"model_id": model_id}), "--custom-modality", "text_and_image",
           "--output-dir", str(out), "--output", str(out / "report.json")]
    out.mkdir(parents=True, exist_ok=True)
    with (out / "gdb.log").open("w") as fh:
        rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"{key}: gdb exit {rc}")


def main(argv: list[str]) -> None:
    if argv[:1] == ["--wait-for"]:
        council_log = Path(argv[1])
        argv = argv[2:]
        while "ALL DONE" not in (council_log.read_text() if council_log.exists() else ""):
            time.sleep(120)
        log("council stage finished")
    keys = argv or ORDER
    _, specs = load_catalogue()
    bench = get_settings().artifacts_dir / "bench"
    for key in keys:
        spec = specs[key]
        if not (spec.dir / "apex_manifest.json").exists():
            log(f"{key}: not acquired — skipped")
            continue
        for other in specs.values():
            if other.key != key:
                LocalServer(other).stop()
        srv = LocalServer(spec)
        try:
            srv.start(wait_s=900)
        except Exception as e:  # noqa: BLE001
            log(f"{key}: server failed: {e}")
            continue
        try:
            if spec.vision:
                log(f"{key}: GDB smoke")
                gdb_smoke(key, spec.registry_model, bench / "gdb" / key)
            log(f"{key}: APEX design bench (LLM pages)")
            s = run_apex_design_bench(GOLDEN_JOB, bench / "apex_design", [spec.registry_model],
                                      only_types=PAGE_TYPES, include_native=False)
            log(f"{key}: {json.dumps(s['systems'].get('llm:' + spec.registry_model), ensure_ascii=False)[:600]}")
        finally:
            srv.stop()
    log("ALL DONE")


if __name__ == "__main__":
    main(sys.argv[1:])
