"""Why does a vision model pass a pairwise hierarchy question but fail absolute calibration?

Experiments on the SAME calibration pages (good + five broken variants), each isolating one suspected cause:

* E0 absolute  — the production council protocol (six roles in one call); raw scores + raw text kept, so ties,
                 inversions, parser drops and truncation can be told apart.
* E1 pairwise  — order-swapped A/B on every case at 640 px (the production pairwise protocol).
* E2 pairwise  — the same at 1024 px (image-scaling sensitivity).
* E3 single    — absolute score for ONLY the targeted role (rubric-overload / schema hypothesis).
* E4 repeat    — E3 repeated (temperature 0 instability).

Every call goes through the $0 broker with purpose=evaluation; results land in
artifacts/bench/vision_investigation/<model>.json.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from apex_one.compute.providers import ChatMessage
from apex_one.core.schemas.compute import CapabilityRequest
from apex_one.vision.pairwise import CALIBRATED_MAX_W

TARGET_ROLE = {"low_contrast": "TypographyJudge", "card_overuse": "AIClicheJudge", "gradient": "APEXBrandJudge",
               "cramped": "EditorialDesignJudge", "no_hierarchy": "VisualHierarchyJudge"}


def _single_role_prompt(role: str, rubric: str, intent: str) -> str:
    return ("You are a strict senior art director. The image is ONE rendered A4 page of an Arabic (right-to-left) "
            f"student guide. Page intent: {intent}. Judge only this criterion — {role}: {rubric} "
            'Return ONLY JSON {"score": 0-100, "reason": "one sentence"}.')


def _score(text: str) -> float | None:
    try:
        v = float(json.loads(re.search(r"\{.*\}", text, re.S).group(0)).get("score"))  # type: ignore[union-attr]
        return v if 0 <= v <= 100 else None
    except Exception:  # noqa: BLE001
        return None


def single_role(broker, model_id: str, png: Path, role: str, intent: str) -> dict[str, Any]:
    from apex_one.vision.council import ROLES, encode_png

    t0 = time.perf_counter()
    res = broker.complete(CapabilityRequest(task="vision.calibration.single", vision=True, purpose="evaluation",
                                            model_id=model_id),
                          [ChatMessage("user", _single_role_prompt(role, ROLES[role], intent),
                                       images_b64_png=[encode_png(png)])],
                          json_mode=True, max_tokens=150, temperature=0.0, timeout=2400.0)
    text = res.text or ""
    return {"score": _score(text) if res.executed else None, "raw": text[:400],
            "executed": res.executed, "latency_s": round(time.perf_counter() - t0, 1)}


def investigate(model_id: str, calib_dir: Path, out_dir: Path, intent: str = "one-page snapshot of "
                "decision-critical facts; deadline must dominate", experiments: tuple[str, ...] =
                ("E0", "E1", "E2", "E3", "E4")) -> dict[str, Any]:
    from apex_one.compute.broker import ComputeBroker
    from apex_one.vision.council import VisionCouncil, calibrate
    from apex_one.vision.pairwise import PairwiseJudge, calibrate_pairwise

    pages = json.loads((calib_dir / "calibration_pages.json").read_text(encoding="utf-8"))
    good = Path(pages.pop("good"))
    broken = {k: Path(v) for k, v in pages.items()}
    broker = ComputeBroker()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{model_id}.json"
    rep: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"model": model_id}

    def save() -> None:
        path.write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    if "E0" in experiments and "E0" not in rep:
        council = VisionCouncil(broker, [model_id], timeout=3600.0)   # CPU: 12B reviews can exceed 15 min
        reviews: dict[str, Any] = {}

        class Recording:          # keeps every PageReview (raw text + parsed roles) for diagnosis
            models = council.models

            def review(self, page_id, png, intent_):
                pr = council.review(page_id, png, intent_)
                reviews[page_id] = {"raw": pr.raw.get(model_id, ""), "errors": pr.errors,
                                    "scores": {r: v["score"] for r, v in pr.reviews.get(model_id, {}).items()}}
                return pr

        res = calibrate(Recording(), good, broken, intent)["models"][model_id]
        flat = [s for r in reviews.values() for s in r["scores"].values()]
        rep["E0"] = {"result": res, "reviews": reviews,
                     "distinct_scores": sorted(set(flat)), "ties_on_target": sum(
                         1 for k, v in res.get("scores", {}).items() if v["good"] is not None and v["good"] == v["broken"]),
                     "inversions_on_target": sum(
                         1 for k, v in res.get("scores", {}).items() if None not in (v["good"], v["broken"])
                         and v["broken"] > v["good"])}
        save()
    for key, width in (("E1", CALIBRATED_MAX_W), ("E2", 1024)):
        if key in experiments and key not in rep:
            rep[key] = {"max_w": width, **calibrate_pairwise(PairwiseJudge(broker, [model_id], max_w=width, timeout=2400.0), good,
                                                             broken, intent)["models"][model_id]}
            save()
    for key in ("E3", "E4"):
        if key in experiments and key not in rep:
            cases = {}
            for k, p in broken.items():
                role = TARGET_ROLE[k]
                g, b = single_role(broker, model_id, good, role, intent), single_role(broker, model_id, p, role, intent)
                cases[k] = {"role": role, "good": g, "broken": b,
                            "pass": None if None in (g["score"], b["score"]) else g["score"] > b["score"]}
            valid = [c["pass"] for c in cases.values() if c["pass"] is not None]
            rep[key] = {"cases": cases, "correct": sum(valid), "valid": len(valid)}
            save()
    return rep
