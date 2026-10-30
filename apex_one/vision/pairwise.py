"""Phase 19/23 — pairwise finalist judging (PosterReward-style PROTOCOL re-implementation, not its weights).

Each calibrated-reliable vision judge sees the two finalists twice, in both orders. A judge's vote counts only when
it is order-consistent (prefers the same page both times). The council winner needs a strict majority of
consistent votes; anything else is a tie and the deterministic ranking stands. Every disagreement — between
orders (position bias) or between judges — is recorded for the Lab, never hidden.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apex_one.compute.providers import ChatMessage
from apex_one.core.schemas.compute import CapabilityRequest
from apex_one.vision.council import PREPROCESS_VERSION, encode_png, preprocess_hash

QUESTION = ("Two rendered A4 pages of the same Arabic student-guide content. Image A is first, image B is second. "
            "As a strict editorial art director for a premium, restrained brand (deep navy, silver, white), which page "
            "is better overall: clearer hierarchy and entry point, better typography, calmer and more intentional "
            "composition, fewer generic/AI clichés? Page intent: {intent}. Return ONLY JSON "
            '{{"winner": "A" or "B", "reason": "one sentence"}}.')


def _winner(text: str) -> tuple[str | None, str]:
    try:
        d = json.loads(re.search(r"\{.*\}", text, re.S).group(0))  # type: ignore[union-attr]
    except Exception:
        return None, "unparseable"
    w = str(d.get("winner", "")).strip().upper()[:1]
    return (w if w in ("A", "B") else None), str(d.get("reason", ""))[:200]


@dataclass
class PairwiseResult:
    winner: str | None                       # "first" | "second" | None (tie / no consistent majority)
    votes: dict[str, str | None] = field(default_factory=dict)      # model -> first|second|None(inconsistent)
    raw: dict[str, list[Any]] = field(default_factory=dict)
    disagreements: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)       # calls that did not execute / did not parse
    executed_judges: int = 0                                 # judges whose BOTH calls returned a valid answer
    raw_text: dict[str, list[str]] = field(default_factory=dict)     # model -> verbatim answers (A/B order, B/A order)
    latency_s: dict[str, list[float]] = field(default_factory=dict)
    preprocess: dict[str, Any] = field(default_factory=dict)          # width, contract version, input hashes

    @property
    def measured(self) -> bool:
        return self.executed_judges > 0

    def as_dict(self) -> dict[str, Any]:
        return {"status": "MEASURED" if self.measured else "NOT_MEASURED", "winner": self.winner, "votes": self.votes,
                "raw": self.raw, "disagreements": self.disagreements, "failures": self.failures,
                "executed_judges": self.executed_judges, "raw_text": self.raw_text, "latency_s": self.latency_s,
                "preprocess": self.preprocess}


# canonical judge-input width (VISION_JUDGE_ROBUSTNESS.md): Qwen3-VL 8B was 4/5 here but 3/5 at its native 794 px,
# so it is calibrated for THIS normalized input only — see the robustness sweep before trusting any other width
CALIBRATED_MAX_W = 640
POSITION_BIAS_MAX = 0.2      # pre-registered (VISION_JUDGE_ROBUSTNESS.md): at most one of five cases may flip with order


class PairwiseJudge:
    def __init__(self, broker, model_ids: list[str], workspace=None, max_w: int = CALIBRATED_MAX_W,
                 timeout: float = 900.0):
        self.broker, self.models, self.ws, self.max_w, self.timeout = broker, model_ids, workspace, max_w, timeout

    def compare(self, first: Path, second: Path, intent: str) -> PairwiseResult:
        import time

        a, b = encode_png(first, self.max_w), encode_png(second, self.max_w)
        res = PairwiseResult(winner=None, preprocess={
            "width": self.max_w, "version": PREPROCESS_VERSION,
            "first": preprocess_hash(first, self.max_w), "second": preprocess_hash(second, self.max_w)})
        for mid in self.models:
            picks = []
            res.raw_text[mid], res.latency_s[mid] = [], []
            for img1, img2, map_ in ((a, b, {"A": "first", "B": "second"}), (b, a, {"A": "second", "B": "first"})):
                t0 = time.perf_counter()
                req = CapabilityRequest(task="vision.pairwise", vision=True, purpose="evaluation", model_id=mid)
                out = self.broker.complete(req, [ChatMessage("user", QUESTION.format(intent=intent),
                                                             images_b64_png=[img1, img2])],
                                           json_mode=True, max_tokens=120, temperature=0.0, workspace=self.ws,
                                           timeout=self.timeout)
                res.latency_s[mid].append(round(time.perf_counter() - t0, 1))
                res.raw_text[mid].append((out.text or "")[:400])
                w, why = _winner(out.text or "") if out.executed else (None, out.decision.outcome.value)
                picks.append((map_.get(w) if w else None, why))
            res.raw[mid] = picks
            (p1, w1), (p2, w2) = picks
            if p1 is None or p2 is None:
                res.votes[mid] = None
                res.failures.append(f"{mid}: no valid answer ({w1 if p1 is None else w2}) — vote not cast")
                continue
            res.executed_judges += 1
            if p1 == p2:
                res.votes[mid] = p1
            else:
                res.votes[mid] = None
                res.disagreements.append(f"{mid}: order-inconsistent ({p1} vs {p2}) — position bias, vote discarded")
        consistent = [v for v in res.votes.values() if v]
        if len(set(consistent)) > 1:
            res.disagreements.append(f"judges disagree: {res.votes}")
        for side in ("first", "second"):
            if consistent.count(side) * 2 > len(self.models):
                res.winner = side
        return res


def calibrate_pairwise(judge: PairwiseJudge, good: Path, broken: dict[str, Path], intent: str) -> dict[str, Any]:
    """Pairwise calibration on the SAME five cases as absolute calibration (good vs each broken variant).
    `compare` asks every pair in BOTH orders (good shown as image A, then as image B). A case passes only if the judge
    picks the good page in both orders. Reliable for pairwise use: all five cases valid and >= 4/5 passed.
    Order inversion is reported per case: picking the same POSITION both times is position bias."""
    out: dict[str, Any] = {"models": {}}
    results = {k: judge.compare(good, p, intent) for k, p in broken.items()}
    for mid in judge.models:
        checks, detail = {}, {}
        for k, res in results.items():
            (p1, w1), (p2, w2) = res.raw[mid]          # p = which ARGUMENT won: "first" == the good page
            checks[k] = None if p1 is None or p2 is None else (p1 == "first" and p2 == "first")
            detail[k] = {"good_as_A": p1, "good_as_B": p2,
                         "position_bias": None if p1 is None or p2 is None else p1 != p2,
                         "reasons": [w1, w2], "raw_text": res.raw_text.get(mid), "latency_s": res.latency_s.get(mid),
                         "preprocess": res.preprocess}
        valid = [v for v in checks.values() if v is not None]
        correct = sum(valid)
        biased = [d["position_bias"] for d in detail.values() if d["position_bias"] is not None]
        # PAIRWISE_POSITION_BIAS: share of cases where the judge followed the SLOT, not the page
        bias_rate = round(sum(biased) / len(biased), 3) if biased else None
        out["models"][mid] = {"checks": checks, "detail": detail, "valid_checks": len(valid), "correct": correct,
                              "discrimination_rate": correct / len(valid) if valid else None,
                              "position_bias_rate": bias_rate,
                              "reliable": len(valid) == len(checks) and correct >= 4
                              and bias_rate is not None and bias_rate <= POSITION_BIAS_MAX}
    return out


# ---------------------------------------------------------------------------------------------------------------
# Production role of a CANONICAL_640_ONLY judge (frozen policy, PRODUCTION_ROUTING_MATRIX.md):
# SECONDARY_FINALIST_PAIRWISE_JUDGE — advisory A/B preference between two finalists that ALREADY passed
# deterministic QA, on the canonical 640 px normalized input of an A4 page render, from the calibrated model build.
# It is never the release authority and it never judges facts, dates or Egyptian-Arabic quality.
SECONDARY_ROLE = "SECONDARY_FINALIST_PAIRWISE_JUDGE"
ALLOWED_SCOPES = frozenset({"visual_design"})
A4_RATIO = 1123 / 794                      # rendered A4 page (Renderer, device scale 1 = 794 x 1123)
_FORBIDDEN_INTENT = re.compile(r"\bfact|\bdate|deadline|\bcorrect|accura|egyptian|dialect|translat|spelling|grammar"
                               r"|تاريخ|موعد|مصري|عامية", re.I)


class JudgeInputRejected(ValueError):
    """The request is outside what the judge was calibrated for; the caller keeps the deterministic decision."""


def admissibility(first: Path, second: Path, *, intent: str, scope: str, max_w: int,
                  deterministic_qa_passed: bool) -> str | None:
    """Why this request may NOT go to the secondary pairwise judge (None = admissible)."""
    from PIL import Image

    if scope not in ALLOWED_SCOPES:
        return f"scope {scope!r} is not calibrated (allowed: {sorted(ALLOWED_SCOPES)})"
    if _FORBIDDEN_INTENT.search(intent or ""):
        return "intent asks about facts, dates or language quality — never a vision-judge decision"
    if max_w != CALIBRATED_MAX_W:
        return f"judge width {max_w} px is not the canonical {CALIBRATED_MAX_W} px input"
    if not deterministic_qa_passed:
        return "finalists have not passed deterministic QA"
    for p in (first, second):
        with Image.open(p) as im:
            w, h = im.size
        if abs(h / w - A4_RATIO) > 0.005:
            return f"{p.name}: {w}x{h} is not an A4 page render (mobile or arbitrary screenshot)"
        if w < CALIBRATED_MAX_W:
            return f"{p.name}: {w} px wide — below the canonical width (would need upscaling)"
    return None


def secondary_finalist_compare(broker, judges: list[str], first: Path, second: Path, intent: str, *,
                               deterministic_qa_passed: bool, workspace=None, scope: str = "visual_design",
                               max_w: int = CALIBRATED_MAX_W) -> dict[str, Any]:
    """The ONLY production entry point for a pairwise judge. Returns an advisory record; on any inadmissible
    request (or no admitted judge) the result is NOT_MEASURED and the deterministic order stands."""
    base = {"role": SECONDARY_ROLE, "authority": "advisory", "judges": judges}
    if not judges:
        return {**base, "status": "NOT_MEASURED", "reason": "no judge admitted for canonical pairwise use"}
    why = admissibility(first, second, intent=intent, scope=scope, max_w=max_w,
                        deterministic_qa_passed=deterministic_qa_passed)
    if why:
        return {**base, "status": "NOT_MEASURED", "reason": f"inadmissible: {why}"}
    res = PairwiseJudge(broker, judges, workspace=workspace, max_w=max_w).compare(first, second, intent)
    return {**base, **res.as_dict(), "_result": res}
