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


# production judges at the width they were calibrated at: Qwen3-VL 8B is 4/5 at 640 px but 3/5 at 1024 px
CALIBRATED_MAX_W = 640


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
        out["models"][mid] = {"checks": checks, "detail": detail, "valid_checks": len(valid), "correct": correct,
                              "discrimination_rate": correct / len(valid) if valid else None,
                              "reliable": len(valid) == len(checks) and correct >= 4}
    return out
