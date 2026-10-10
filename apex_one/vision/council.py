"""Phase 18 — the real multimodal Vision Council.

Several INDEPENDENT vision models each review the rendered screenshot (never the HTML) through the
ComputeBroker ($0 firewall, purpose=evaluation). One call per (page, model) carries six role rubrics to keep
CPU inference tractable; every role returns structured observations, problems (severity + region), a suggested
repair and a confidence. The council then:

* aggregates per role with the MEDIAN across models (no single model is the judge),
* records disagreements (spread > 25) and checks them against the deterministic DOM metric where one exists,
* never lets the page's designer engine judge alone (designers here are native engines; judges are models).

Judge reliability is measured separately by `calibrate()`: a known-good page vs deliberately broken variants.
A judge that cannot rank the broken page below the good one is reported as UNRELIABLE and its scores are not
used for gates.
"""

from __future__ import annotations

import base64
import io
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from apex_one.compute.providers import ChatMessage
from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.compute import CapabilityRequest

ROLES = {
    "VisualHierarchyJudge": "Is there ONE clear entry point and a clear reading order? Does the eye land on the intended element?",
    "TypographyJudge": "Arabic typography: natural shaping, comfortable size/leading, clean rag, no awkward breaks, English isolated cleanly.",
    "EditorialDesignJudge": "Does it read like a premium editorial publication (intentional grid, whitespace, rhythm) rather than a template?",
    "APEXBrandJudge": "Does it belong to APEX: deep navy, metallic silver, white, precise, premium, futuristic-editorial, restrained accents?",
    "AIClicheJudge": "Does it avoid generic AI design (rounded cards everywhere, gradients, random icons, blobs, dashboards)? 100 = no clichés.",
    "ReaderAttentionJudge": "Would a 16-year-old Egyptian student find the decision-critical facts (deadline, money, eligibility) in 10 seconds?",
}
SEVERITIES = ("critical", "major", "minor")
REGIONS = ("top", "upper-middle", "middle", "lower-middle", "bottom", "full")


def _prompt(intent: str) -> str:
    rubric = "\n".join(f"- {k}: {v}" for k, v in ROLES.items())
    return (
        "You are an independent senior art director on the APEX quality court. The image is ONE rendered A4 page "
        "of an Arabic (right-to-left) student guide. Judge only what you SEE. Be strict and specific.\n"
        f"Page intent: {intent}\nRoles:\n{rubric}\n"
        "Return ONLY JSON of the form {\"<Role>\": {\"score\": 0-100, \"observations\": [str], \"problems\": "
        "[{\"issue\": str, \"severity\": \"critical|major|minor\", \"region\": \"top|upper-middle|middle|lower-middle|"
        "bottom|full\"}], \"suggested_repair\": str, \"confidence\": 0-1}} with all six roles. Be concise: at most "
        "3 observations and 3 problems per role, one sentence each."
    )


def encode_png(path: Path, max_w: int = 768) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_w, int(max_w * 1.42)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def parse_review(text: str) -> dict[str, dict[str, Any]]:
    """Validate and normalise a model's review. Invalid roles are dropped, never guessed."""
    try:
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))  # type: ignore[union-attr]
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        r = data.get(role)
        if not isinstance(r, dict):
            continue
        try:
            score = float(r.get("score"))
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 100:
            continue
        problems = []
        for p in r.get("problems") or []:
            if not isinstance(p, dict) or not p.get("issue"):
                continue
            sev = str(p.get("severity", "minor")).lower()
            reg = str(p.get("region", "full")).lower()
            problems.append({"issue": str(p["issue"])[:240], "severity": sev if sev in SEVERITIES else "minor",
                             "region": reg if reg in REGIONS else "full"})
        try:
            conf = max(0.0, min(1.0, float(r.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        out[role] = {"score": score, "observations": [str(o)[:240] for o in (r.get("observations") or [])][:6],
                     "problems": problems[:8], "suggested_repair": str(r.get("suggested_repair", ""))[:300],
                     "confidence": conf}
    return out


@dataclass
class PageReview:
    page_id: str
    reviews: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)   # model -> role -> review
    errors: dict[str, str] = field(default_factory=dict)

    def role_metric(self, role: str) -> Metric:
        scores = [rv[role]["score"] for rv in self.reviews.values() if role in rv]
        if not scores:
            return Metric.not_measured(f"council.{role}", "no vision model produced a valid review")
        return Metric.measured(f"council.{role}", statistics.median(scores),
                               f"median of {len(scores)} independent vision model(s): {sorted(self.reviews)}",
                               evidence=[f"{m}={rv[role]['score']:.0f}" for m, rv in self.reviews.items() if role in rv])

    def disagreements(self, spread: float = 25.0) -> list[dict[str, Any]]:
        out = []
        for role in ROLES:
            vals = {m: rv[role]["score"] for m, rv in self.reviews.items() if role in rv}
            if len(vals) >= 2 and max(vals.values()) - min(vals.values()) > spread:
                out.append({"page": self.page_id, "role": role, "scores": vals})
        return out


class VisionCouncil:
    def __init__(self, broker, model_ids: list[str], workspace=None, max_tokens: int = 1800):
        self.broker, self.models, self.ws, self.max_tokens = broker, model_ids, workspace, max_tokens

    def review(self, page_id: str, png: Path, intent: str) -> PageReview:
        pr = PageReview(page_id)
        b64 = encode_png(png)
        for mid in self.models:
            req = CapabilityRequest(task="vision.council", vision=True, purpose="evaluation", model_id=mid)
            res = self.broker.complete(req, [ChatMessage("user", _prompt(intent), images_b64_png=[b64])],
                                       json_mode=True, max_tokens=self.max_tokens, temperature=0.0, workspace=self.ws,
                                       timeout=900.0)
            if not res.executed or not res.text:
                errs = [c.error for c in res.calls if c.error]
                pr.errors[mid] = f"{res.decision.outcome.value}: {errs[-1:] or res.decision.reasons[-1:]}"
                continue
            parsed = parse_review(res.text)
            if not parsed:
                pr.errors[mid] = "unparseable review"
                continue
            pr.reviews[mid] = parsed
        return pr


def calibrate(council: VisionCouncil, good_png: Path, bad_pngs: dict[str, Path], intent: str) -> dict[str, Any]:
    """Judge reliability: each model must score the good page above every deliberately broken variant on the
    role that the breakage targets. Returns per-model reliability; unreliable judges are excluded from gates."""
    good = council.review("calibration-good", good_png, intent)
    result: dict[str, Any] = {"models": {}}
    target_role = {"low_contrast": "TypographyJudge", "card_overuse": "AIClicheJudge", "gradient": "APEXBrandJudge",
                   "cramped": "EditorialDesignJudge", "no_hierarchy": "VisualHierarchyJudge"}
    bad_reviews = {k: council.review(f"calibration-{k}", p, intent) for k, p in bad_pngs.items()}
    for mid in council.models:
        checks = {}
        for k, br in bad_reviews.items():
            role = target_role.get(k, "EditorialDesignJudge")
            g = good.reviews.get(mid, {}).get(role, {}).get("score")
            b = br.reviews.get(mid, {}).get(role, {}).get("score")
            checks[k] = None if g is None or b is None else bool(g > b)
        valid = [v for v in checks.values() if v is not None]
        rate = sum(valid) / len(valid) if valid else None
        result["models"][mid] = {"checks": checks, "discrimination_rate": rate,
                                 "reliable": rate is not None and rate >= 0.6}
    return result
