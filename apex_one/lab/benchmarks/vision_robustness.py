"""Vision-judge robustness: does a pairwise judge's calibration survive a change of input resolution?

For each width in WIDTHS the judge sees the SAME five calibration cases (good page vs each deliberately broken
variant), in BOTH orders, REPEATS times. Inputs go through the production judge-input contract
(apex_one.vision.council.normalize_for_judge, width-bound, aspect ratio kept). Widths above the native render
(794 CSS px for an A4 page) are produced by RE-RENDERING the page at a higher device scale — never by upscaling an
image, which would add pixels but no information.

Per width we store: accuracy per repeat, order sensitivity (cases where the judge picked the same POSITION in both
orders), run variance across repeats, per-call latency, every raw answer, a consistency confidence, the input
preprocessing hashes, and a legibility probe (can the judge READ the decision-critical facts at this width?).

Confidence: the judge is NOT asked to self-report confidence — that would change the calibrated prompt. Instead,
per case, p = share of its 2 x REPEATS answers that picked the good page and confidence = |2p - 1|
(1 = unanimous, 0 = coin flip). It is a measured consistency, not a probability of being right.

Pre-registered rules (fixed before any robustness result was observed; never tuned afterwards):
  reliable at a width  = every repeat has all five cases valid and >= 4/5 correct (MIN_PASS_RATE)
  legible at a width   = the judge reads BOTH probe facts (application deadline, tuition coverage) correctly
  ROBUSTLY_CALIBRATED  = reliable at EVERY width where it is legible, and legible at the canonical width,
                         at native width and at 1024 px
  CANONICAL_640_ONLY   = reliable and legible at the canonical width (640 px) but not robust
  UNQUALIFIED          = not reliable or not legible at the canonical width (a single lucky 4/5 is not enough)
  INCOMPLETE           = the canonical width has not finished all repeats yet
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from apex_one.vision.council import MIN_PASS_RATE, PREPROCESS_VERSION, encode_png, preprocess_hash
from apex_one.vision.pairwise import CALIBRATED_MAX_W

WIDTHS = ("320", "480", "640", "768", "native", "1024")
REPEATS = 3
INTENT = "one-page snapshot of decision-critical facts; deadline must dominate"
CANONICAL = str(CALIBRATED_MAX_W)
STATUSES = ("ROBUSTLY_CALIBRATED", "CANONICAL_640_ONLY", "UNQUALIFIED", "INCOMPLETE")
PROBE = ("This is one rendered page of an Arabic student guide. Read it carefully and return ONLY JSON "
         '{"application_deadline": "<the application deadline exactly as printed>", '
         '"tuition_coverage": "<the tuition coverage exactly as printed>"}.')


def robustness_dir() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "bench" / "vision_robustness"


def _pages(calib_dir: Path) -> tuple[Path, dict[str, Path]]:
    from apex_one.lab.benchmarks.vision_calibration import calibration_pages

    return calibration_pages(calib_dir)


def native_width(calib_dir: Path) -> int:
    from PIL import Image

    return Image.open(_pages(calib_dir)[0]).size[0]


def probe_truth(calib_dir: Path) -> dict[str, str]:
    """Ground truth for the legibility probe, read from the visible page's locked fact spans."""
    import re

    from bs4 import BeautifulSoup

    html = (calib_dir / "good.html").read_text(encoding="utf-8")
    idx = int(re.search(r"nth-of-type\((\d+)\)", html).group(1))  # type: ignore[union-attr]
    page = BeautifulSoup(html, "lxml").select("section.page")[idx - 1]
    get = lambda slot: page.select_one(f'[data-slot="{slot}"]').get_text(" ", strip=True)  # noqa: E731
    return {"application_deadline": get("deadline.application"), "tuition_coverage": get("scholarship_coverage.tuition")}


def _norm(v: str) -> str:
    from apex_one.research.evidence.normalize import find_dates, to_ascii_digits

    t = to_ascii_digits(str(v))
    d = find_dates(t)
    return d[0][0].isoformat() if d else "".join(t.split()).replace("٪", "%")


def min_font_px(calib_dir: Path) -> float | None:
    """Smallest computed font size (CSS px) of visible text on the calibration page."""
    from apex_one.vision.render.renderer import Renderer

    js = """() => { let m = 1e9; for (const el of document.querySelectorAll('section.page *')) {
        if (!el.offsetParent || !el.childNodes.length) continue;
        if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
        m = Math.min(m, parseFloat(getComputedStyle(el).fontSize)); } return m < 1e9 ? m : null; }"""
    with Renderer() as r:
        page = r._page(834, 1123, 1.0)
        try:
            page.goto((calib_dir / "good.html").resolve().as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            return page.evaluate(js)
        finally:
            page.close()


def inputs_for(calib_dir: Path, out_dir: Path, wkey: str) -> tuple[int, Path, dict[str, Path], str]:
    """(width, good, broken, how). At or below native: the calibration PNGs (the judge downscales them). Above
    native: every variant re-rendered at device scale width/native, so the extra pixels carry real detail."""
    native = native_width(calib_dir)
    width = native if wkey == "native" else int(wkey)
    good, broken = _pages(calib_dir)
    if width <= native:
        return width, good, broken, "calibration render, downscaled by the judge-input contract" if width < native \
            else "calibration render at native size (no resampling)"
    from PIL import Image

    from apex_one.vision.render.renderer import Renderer

    d = out_dir / "inputs" / f"w{width}"
    d.mkdir(parents=True, exist_ok=True)
    shots: dict[str, Path] = {}
    with Renderer(device_scale=width / native) as r:
        for name in ("good", *broken):
            dst = d / f"{name}-01.png"
            if not dst.exists():
                res = r.measure(calib_dir / f"{name}.html", screenshot_dir=d, screenshot_prefix=name)
                assert res.page_screenshots and res.page_screenshots[0] == dst
            shots[name] = dst
    got = Image.open(shots["good"]).size[0]
    if abs(got - width) > 2:
        raise RuntimeError(f"re-render produced width {got}, expected {width}")
    return width, shots.pop("good"), shots, f"re-rendered at device scale {width / native:.3f} (no upscaling)"


def legibility(broker, model_id: str, good: Path, width: int, truth: dict[str, str]) -> dict[str, Any]:
    from apex_one.compute.providers import ChatMessage
    from apex_one.core.schemas.compute import CapabilityRequest

    t0 = time.perf_counter()
    req = CapabilityRequest(task="vision.legibility", vision=True, purpose="evaluation", model_id=model_id)
    out = broker.complete(req, [ChatMessage("user", PROBE, images_b64_png=[encode_png(good, width)])],
                          json_mode=True, max_tokens=160, temperature=0.0, timeout=2400)
    text = out.text or ""
    try:
        import re

        got = json.loads(re.search(r"\{.*\}", text, re.S).group(0))  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        got = {}
    read = {k: _norm(got.get(k, "")) == _norm(v) for k, v in truth.items()}
    return {"legible": out.executed and all(read.values()), "read": read, "answer": got, "raw": text[:400],
            "truth": truth, "latency_s": round(time.perf_counter() - t0, 1), "executed": out.executed}


def run_width(model_id: str, calib_dir: Path, wkey: str, out_dir: Path | None = None,
              repeats: int = REPEATS) -> dict[str, Any]:
    """Resumable: each finished repeat is saved before the next starts."""
    from apex_one.compute.broker import ComputeBroker
    from apex_one.vision.pairwise import PairwiseJudge, calibrate_pairwise

    out_dir = out_dir or robustness_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{model_id}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"model": model_id, "widths": {}}
    width, good, broken, how = inputs_for(calib_dir, out_dir, wkey)
    w = data["widths"].setdefault(wkey, {"width": width, "inputs": how, "reps": []})
    w.update({"width": width, "inputs": how, "preprocess_version": PREPROCESS_VERSION,
              "input_hashes": {n: preprocess_hash(p, width) for n, p in {"good": good, **broken}.items()}})
    broker = ComputeBroker()

    def save() -> None:
        from apex_one.vision.council import model_digest

        data["model_digest"] = model_digest(model_id)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    while len(w["reps"]) < repeats:
        t0 = time.perf_counter()
        res = calibrate_pairwise(PairwiseJudge(broker, [model_id], max_w=width, timeout=2400.0), good, broken, INTENT)
        w["reps"].append({**res["models"][model_id], "wall_s": round(time.perf_counter() - t0, 1)})
        save()
    if "legibility" not in w:
        w["legibility"] = legibility(broker, model_id, good, width, probe_truth(calib_dir))
        save()
    return summarize_width(w)


def summarize_width(w: dict[str, Any]) -> dict[str, Any]:
    reps = w.get("reps", [])
    if not reps:
        return {"width": w.get("width"), "repeats": 0}
    correct = [r.get("correct", 0) for r in reps]
    cases = list(reps[0]["checks"])
    bias = [d.get("position_bias") for r in reps for d in r["detail"].values()]
    flips = [k for k in cases if len({r["checks"].get(k) for r in reps}) > 1]
    conf = []
    for k in cases:
        picks = [p for r in reps for p in (r["detail"][k].get("good_as_A"), r["detail"][k].get("good_as_B"))
                 if p is not None]
        if picks:
            share = sum(p == "first" for p in picks) / len(picks)
            conf.append(abs(2 * share - 1))
    lat = [x for r in reps for d in r["detail"].values() for x in (d.get("latency_s") or [])]
    leg = w.get("legibility") or {}
    return {"width": w["width"], "inputs": w.get("inputs"), "repeats": len(reps), "correct_per_repeat": correct,
            "accuracy": round(statistics.mean(correct) / len(cases), 3), "min_correct": min(correct),
            "all_valid": all(r.get("valid_checks") == len(cases) for r in reps),
            "reliable_all_repeats": all(r.get("valid_checks") == len(cases)
                                        and r.get("correct", 0) / len(cases) >= MIN_PASS_RATE for r in reps),
            "order_sensitivity": round(sum(bool(b) for b in bias) / max(1, sum(b is not None for b in bias)), 3),
            "position_bias_cases": sum(bool(b) for b in bias),
            "run_variance": round(statistics.pvariance(correct), 3), "cases_flipping_across_repeats": flips,
            "cases_failed_every_repeat": [k for k in cases if all(r["checks"].get(k) is False for r in reps)],
            "confidence_mean": round(statistics.mean(conf), 3) if conf else None,
            "median_call_latency_s": statistics.median(lat) if lat else None,
            "legible": leg.get("legible"), "legibility_read": leg.get("read"),
            "preprocess_version": w.get("preprocess_version"), "input_hash_good": (w.get("input_hashes") or {}).get("good")}


def status(data: dict[str, Any] | None) -> tuple[str, str]:
    """Apply the pre-registered rules (module docstring) to one judge's robustness results."""
    if not data:
        return "INCOMPLETE", "no robustness results"
    s = {k: summarize_width(v) for k, v in data.get("widths", {}).items()}
    c = s.get(CANONICAL)
    if not c or c.get("repeats", 0) < REPEATS or c.get("legible") is None:
        return "INCOMPLETE", f"canonical {CANONICAL} px has {c.get('repeats', 0) if c else 0}/{REPEATS} repeats"
    if not (c["reliable_all_repeats"] and c["legible"]):
        return "UNQUALIFIED", (f"canonical {CANONICAL} px: correct per repeat {c['correct_per_repeat']}, "
                               f"legible={c['legible']}")
    done = {k: v for k, v in s.items() if v.get("repeats", 0) >= REPEATS and v.get("legible") is not None}
    missing = [k for k in WIDTHS if k not in done]
    must_be_legible = [CANONICAL, "native", "1024"]
    unreliable = [k for k, v in done.items() if v["legible"] and not v["reliable_all_repeats"]]
    illegible_required = [k for k in must_be_legible if k in done and not done[k]["legible"]]
    if not missing and not unreliable and not illegible_required:
        return "ROBUSTLY_CALIBRATED", "reliable at every legible width"
    why = [f"unreliable at {', '.join(unreliable)}"] if unreliable else []
    why += [f"illegible at {', '.join(illegible_required)}"] if illegible_required else []
    other_illegible = [k for k, v in done.items() if not v["legible"] and k not in must_be_legible]
    why += [f"illegible (so not counted) at {', '.join(other_illegible)}"] if other_illegible else []
    why += [f"not yet measured: {', '.join(missing)}"] if missing else []
    return "CANONICAL_640_ONLY", "; ".join(why)


def load(model_id: str, out_dir: Path | None = None) -> dict[str, Any] | None:
    p = (out_dir or robustness_dir()) / f"{model_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
