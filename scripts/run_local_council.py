"""Sequentially run the real local model council: calibration (vision) + council benchmark per model.

Usage: python scripts/run_local_council.py [model_key ...]
Waits for acquisition to finish for models still downloading. Stops each server afterwards (RAM budget).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from apex_one.compute.benchmark.council import run_council
from apex_one.compute.broker import ComputeBroker
from apex_one.compute.local import LocalServer, load_catalogue
from apex_one.lab.benchmarks.vision_calibration import run_calibration
from apex_one.settings import get_settings

ORDER = ["gemma3-4b-q4km", "nemotron-3-nano-4b-q4km", "qwen3-vl-4b-q4kxl", "gpt-oss-20b-mxfp4"]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main(keys: list[str]) -> None:
    _, specs = load_catalogue()
    bench = get_settings().artifacts_dir / "bench"
    calib = bench / "vision_calibration"
    for key in keys:
        spec = specs[key]
        waited = 0
        while not (spec.dir / "apex_manifest.json").exists() and waited < 6 * 3600:
            log(f"{key}: waiting for acquisition")
            time.sleep(120)
            waited += 120
        if not (spec.dir / "apex_manifest.json").exists():
            log(f"{key}: NOT ACQUIRED — skipped")
            continue
        for other in specs.values():
            if other.key != key:
                LocalServer(other).stop()
        srv = LocalServer(spec)
        try:
            log(f"{key}: starting server")
            srv.start(wait_s=900)
        except Exception as e:  # noqa: BLE001
            log(f"{key}: server failed: {e}")
            continue
        broker = ComputeBroker()
        rid = spec.registry_model
        if spec.vision and (calib / "calibration_pages.json").exists():
            log(f"{key}: vision calibration")
            res = run_calibration([rid], calib)
            log(f"{key}: calibration {json.dumps(res['models'].get(rid))}")
        log(f"{key}: council benchmark")
        data = run_council(broker, [rid], bench, calib_dir=calib if spec.vision else None)
        log(f"{key}: scores {json.dumps(data['models'].get(rid))}")
        srv.stop()
    log("ALL DONE")


if __name__ == "__main__":
    main(sys.argv[1:] or ORDER)
