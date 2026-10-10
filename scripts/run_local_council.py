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


def record_local_live(spec) -> dict:
    """Phase 14: the real structured-output live test on this model's local route, stored for the live report."""
    from apex_one.compute.live import live_test_route
    from apex_one.compute.registry import load_registry

    reg = load_registry()
    m = reg.models.get(spec.registry_model)
    route = next((r for r in (m.routes if m else []) if r.provider == "llamacpp_local"
                  and r.provider_model_id == spec.key), None)
    rec = live_test_route(reg, m, route) if route else {"status": "UNKNOWN", "detail": "no local route in registry"}
    path = get_settings().artifacts_dir / "live" / "local_live_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    data[spec.key] = rec
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return rec


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
        log(f"{key}: live structured test")
        live = record_local_live(spec)
        log(f"{key}: live {live.get('status')} correct={live.get('structured_correct')} {live.get('structured_ms')} ms")
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
