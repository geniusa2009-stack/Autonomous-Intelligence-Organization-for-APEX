"""One deterministic, resumable path that validates Gemini (free tier) as a vision judge — no code changes needed
once GEMINI_API_KEY exists.

`apex-one vision validate-gemini` runs, in this order, and records every step in
artifacts/bench/gemini_validation/report.json:

  0 preconditions   GEMINI_API_KEY present (else BLOCKED_NO_KEY) and a human free-tier/no-billing attestation
                    (else BLOCKED_NO_ATTESTATION) — the $0 firewall refuses any remote route without one
  1 live            list the models the key can see (a network/auth failure is an infrastructure ERROR, never a score)
  2 identify        resolve the EXACT model: --model, else the newest stable "flash" model that supports
                    generateContent (no -latest alias, no preview/exp/lite/tts/image/embedding); record provider,
                    model, version, display name; pin it (registry route + calibration identity) so every later call
                    and every calibration stamp refer to that concrete model
  3 absolute        absolute calibration (same five cases, six-role council) — E0
  4 pairwise        order-swapped pairwise calibration (same five cases, both orders) — E1, which also yields
  5 order inversion position_bias_rate / order sensitivity (FailureMemory remembers a slot-follower)
  6 repeat stability canonical 640 px: 5 cases x both orders x 3 repeats
  7 legibility      the deadline / tuition read-back probe (part of the canonical robustness run)
  8 widths          320 / 480 / 768 / native / 1024 — ONLY if the canonical width qualifies (pre-registered rule)
  9 reports         regenerate the reports (VISION_JUDGE_ROBUSTNESS, PRODUCTION_ROUTING_MATRIX, ...)

Same thresholds, cases, prompts and checkers as every local judge. Gemini is NOT assumed to pass: UNQUALIFIED is a
valid, recorded outcome. Re-running resumes (the free tier allows ~200 requests/day; a full sweep can take two days).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODEL_ID = "gemini-flash-free"          # registry entry whose gemini route is pinned
PROVIDER = "gemini"
EXCLUDE = re.compile(r"latest|preview|exp|lite|tts|image|embedding|audio|live|thinking|learnlm|aqa", re.IGNORECASE)
STEPS = ("live", "identify", "absolute", "pairwise", "canonical", "widths", "reports")
EXIT_DONE, EXIT_BLOCKED, EXIT_ERROR = 0, 2, 3


def out_dir() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "bench" / "gemini_validation"


def _save(rep: dict[str, Any]) -> None:
    out_dir().mkdir(parents=True, exist_ok=True)
    (out_dir() / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")


def _load() -> dict[str, Any]:
    try:
        return json.loads((out_dir() / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def list_models() -> list[dict[str, Any]]:
    """Full model metadata visible to the key (name, version, displayName, supportedGenerationMethods)."""
    from apex_one.compute.providers import build_adapter
    from apex_one.compute.providers.base import raise_for_status
    from apex_one.compute.registry import load_registry

    ad = build_adapter(load_registry().providers[PROVIDER])
    models, token = [], None
    with ad.client(30.0) as c:
        while True:
            resp = c.get(f"{ad.base_url()}/models", headers=ad._headers(), params={"pageToken": token} if token else None)
            raise_for_status(resp)
            data = resp.json()
            models += data.get("models", [])
            token = data.get("nextPageToken")
            if not token:
                return models


def _version_key(name: str) -> tuple:
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return tuple(float(n) for n in nums[:2]) or (0.0,)


def choose_model(models: list[dict[str, Any]], requested: str | None = None) -> tuple[dict[str, Any] | None, str]:
    """Deterministic choice of the concrete judge model (recorded with its reason)."""
    by = {m.get("name", "").removeprefix("models/"): m for m in models}
    if requested:
        m = by.get(requested)
        return (m, f"requested --model {requested}") if m else (None, f"requested model {requested} not visible to the key")
    ok = [n for n, m in by.items() if "flash" in n and not EXCLUDE.search(n)
          and "generateContent" in (m.get("supportedGenerationMethods") or ["generateContent"])]
    if not ok:
        return None, "no stable flash model supporting generateContent is visible to this key"
    best = max(ok, key=lambda n: (_version_key(n), -len(n), n))
    return by[best], f"newest stable flash model supporting generateContent among {sorted(ok)}"


def _default_runners() -> dict[str, Callable[..., Any]]:
    from apex_one.compute.registry.loader import write_pin
    from apex_one.lab.benchmarks.vision_calibration import stamp_calibration
    from apex_one.lab.benchmarks.vision_investigation import investigate
    from apex_one.lab.benchmarks.vision_robustness import run_width
    from apex_one.lab.reports import build_reports
    from apex_one.vision.council import model_digest
    from apex_one.vision.judge_failures import remember

    def absolute(calib: Path) -> dict[str, Any]:
        rep = investigate(MODEL_ID, calib, out_dir() / "investigation", experiments=("E0",))
        stamp_calibration(calib, "models", MODEL_ID, dict(rep["E0"]["result"]))
        return {k: rep["E0"].get(k) for k in ("ties_on_target", "inversions_on_target", "distinct_scores")} | {
            "correct": rep["E0"]["result"].get("valid_checks"), "reliable": rep["E0"]["result"].get("reliable")}

    def pairwise(calib: Path) -> dict[str, Any]:
        rep = investigate(MODEL_ID, calib, out_dir() / "investigation", experiments=("E1",))
        stamp_calibration(calib, "pairwise_models", MODEL_ID, {k: v for k, v in rep["E1"].items() if k != "max_w"})
        remember(MODEL_ID, rep["E1"], model_digest(MODEL_ID))
        return {k: rep["E1"].get(k) for k in ("correct", "valid_checks", "position_bias_rate", "reliable")}

    return {"list_models": list_models, "pin": write_pin, "absolute": absolute, "pairwise": pairwise,
            "width": lambda calib, w: run_width(MODEL_ID, calib, w), "reports": build_reports}


def validate_gemini(model: str | None = None, force: bool = False,
                    runners: dict[str, Callable[..., Any]] | None = None) -> tuple[int, dict[str, Any]]:
    """Run (or resume) the whole validation; returns (exit code, report)."""
    from apex_one.compute.local.supervisor import failure_kind_for
    from apex_one.compute.registry import load_registry
    from apex_one.lab.benchmarks.vision_robustness import (
        CANONICAL,
        WIDTHS,
        load,
        qualification,
        status,
    )
    from apex_one.settings import get_settings

    rep = {} if force else _load()
    rep.setdefault("steps", {})
    rep["last_run_at"] = datetime.now(UTC).isoformat()

    def done(step: str) -> bool:
        return not force and rep["steps"].get(step, {}).get("state") == "PASSED"

    def mark(step: str, state: str, **info: Any) -> None:
        rep["steps"][step] = {"state": state, "at": datetime.now(UTC).isoformat(), **info}
        _save(rep)

    if not os.environ.get("GEMINI_API_KEY"):
        rep["status"] = "BLOCKED_NO_KEY"
        rep["next"] = "store a Gemini free-tier key as the environment secret GEMINI_API_KEY (never enable billing)"
        _save(rep)
        return EXIT_BLOCKED, rep
    if not load_registry().has_attestation(PROVIDER, "free_tier_no_billing", datetime.now(UTC)):
        rep["status"] = "BLOCKED_NO_ATTESTATION"
        rep["next"] = ('apex-one providers attest gemini --by "<name>" --note "AI Studio key, project has no billing"'
                       " — the $0 firewall refuses remote routes without it")
        _save(rep)
        return EXIT_BLOCKED, rep
    run = {**_default_runners(), **(runners or {})}
    calib = get_settings().artifacts_dir / "bench" / "vision_calibration"
    try:
        if not done("live") or not done("identify"):
            models = run["list_models"]()
            rep["live"] = {"ok": True, "status": "LIVE_TESTED", "models_visible": len(models)}
            mark("live", "PASSED", models_visible=len(models))
            chosen, why = choose_model(models, model)
            if chosen is None:
                rep["status"] = "ERROR"
                mark("identify", "ERROR", reason=why)
                return EXIT_ERROR, rep
            name = chosen["name"].removeprefix("models/")
            rep["model"] = {"provider": PROVIDER, "model": name, "version": chosen.get("version"),
                            "display_name": chosen.get("displayName"), "chosen_because": why,
                            "registry_model": MODEL_ID}
            run["pin"](MODEL_ID, PROVIDER, name, chosen.get("version"), display_name=chosen.get("displayName"))
            mark("identify", "PASSED", **rep["model"])
        if not done("absolute"):
            mark("absolute", "PASSED", **run["absolute"](calib))
        if not done("pairwise"):
            mark("pairwise", "PASSED", **run["pairwise"](calib))
        if not done("canonical"):      # repeat stability + order inversion + legibility at the canonical input
            run["width"](calib, CANONICAL)
            summ = ((load(MODEL_ID) or {}).get("widths") or {}).get(CANONICAL) or {}
            mark("canonical", "PASSED", qualification=qualification(summ) if summ else None)
        st, why = status(load(MODEL_ID))
        if st == "UNQUALIFIED":
            mark("widths", "SKIPPED", reason=f"canonical {CANONICAL} px failed — pre-registered: no width sweep ({why})")
        elif not done("widths"):
            for w in (x for x in WIDTHS if x != CANONICAL):
                run["width"](calib, w)
            mark("widths", "PASSED", widths=[x for x in WIDTHS if x != CANONICAL])
        rep["verdict"], rep["verdict_reason"] = status(load(MODEL_ID))
        run["reports"]()
        mark("reports", "PASSED")
        rep["status"] = "COMPLETED"
        _save(rep)
        return EXIT_DONE, rep
    except Exception as e:  # noqa: BLE001 — an infrastructure failure is recorded as such, never as a quality score
        step = next((s for s in STEPS if rep["steps"].get(s, {}).get("state") != "PASSED"), "unknown")
        kind = failure_kind_for(getattr(e, "kind", None) or "unknown")
        rep["status"] = "ERROR"
        rep.setdefault("live", {}).setdefault("ok", step != "live")
        mark(step, "ERROR", failure_kind=getattr(kind, "value", kind), error=str(e)[:300],
             note="infrastructure error: re-run the same command to resume")
        return EXIT_ERROR, rep
