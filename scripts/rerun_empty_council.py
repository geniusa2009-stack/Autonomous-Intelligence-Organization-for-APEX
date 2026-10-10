"""Re-run council tasks whose latest output was EMPTY (reasoning models that spent the budget on hidden reasoning)
with a larger token budget, then rescore every stored output with the current checkers.

Usage: python scripts/rerun_empty_council.py [--max-tokens 4096]
"""

from __future__ import annotations

import json
import sys
import time

from apex_one.compute.benchmark.council import rescore, run_council
from apex_one.compute.broker import ComputeBroker
from apex_one.compute.local import LocalServer, load_catalogue
from apex_one.settings import get_settings


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main(argv: list[str]) -> None:
    max_tokens = int(argv[argv.index("--max-tokens") + 1]) if "--max-tokens" in argv else 4096
    bench = get_settings().artifacts_dir / "bench"
    latest: dict[tuple[str, str], dict] = {}
    for line in (bench / "council_runs.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[(r["model"], r["task"])] = r
    todo: dict[str, list[str]] = {}
    for (model, task), r in latest.items():
        if task != "visual_hierarchy" and not (r.get("output") or "").strip():
            todo.setdefault(model, []).append(task)
    log(f"empty outputs to re-run: {todo}")
    _, specs = load_catalogue()
    for spec in specs.values():
        tasks = todo.get(spec.registry_model)
        if not tasks:
            continue
        for other in specs.values():
            if other.key != spec.key:
                LocalServer(other).stop()
        srv = LocalServer(spec)
        try:
            srv.start(wait_s=900)
            log(f"{spec.key}: re-running {tasks} at max_tokens={max_tokens}")
            run_council(ComputeBroker(), [spec.registry_model], bench, only=tasks, max_tokens=max_tokens)
        finally:
            srv.stop()
    data = rescore(bench)
    log("rescored: " + json.dumps({m: e.get("overall") for m, e in data["models"].items()}))
    log("ALL DONE")


if __name__ == "__main__":
    main(sys.argv[1:])
