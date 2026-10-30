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


# Judge-input contract (VISION_JUDGE_ROBUSTNESS.md): every page a judge sees — calibration and production alike —
# goes through normalize_for_judge(). It is WIDTH-BOUND (each page scaled to the same target width, aspect ratio
# preserved, never capped by height, so two candidates of different heights get the same scale) and never
# upscales: widths above the native render come from a re-render at a higher device scale, not from resampling.
PREPROCESS_VERSION = "width-bound-thumbnail-bicubic-v1"


def normalize_for_judge(path: Path, width: int) -> bytes:
    im = Image.open(path).convert("RGB")
    im.thumbnail((width, 10**6))            # Pillow default resampling (bicubic), aspect ratio preserved
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def preprocess_hash(path: Path, width: int) -> str:
    import hashlib

    return hashlib.sha256(PREPROCESS_VERSION.encode() + normalize_for_judge(path, width)).hexdigest()


def encode_png(path: Path, max_w: int = 768) -> str:
    return base64.b64encode(normalize_for_judge(path, max_w)).decode()


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
    raw: dict[str, str] = field(default_factory=dict)       # model -> raw text (for parser / schema diagnosis)

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
    def __init__(self, broker, model_ids: list[str], workspace=None, max_tokens: int = 1800, timeout: float = 900.0):
        self.broker, self.models, self.ws, self.max_tokens, self.timeout = broker, model_ids, workspace, max_tokens, timeout

    def review(self, page_id: str, png: Path, intent: str) -> PageReview:
        pr = PageReview(page_id)
        b64 = encode_png(png)
        for mid in self.models:
            req = CapabilityRequest(task="vision.council", vision=True, purpose="evaluation", model_id=mid)
            res = self.broker.complete(req, [ChatMessage("user", _prompt(intent), images_b64_png=[b64])],
                                       json_mode=True, max_tokens=self.max_tokens, temperature=0.0, workspace=self.ws,
                                       timeout=self.timeout)
            if not res.executed or not res.text:
                errs = [c.error for c in res.calls if c.error]
                pr.errors[mid] = f"{res.decision.outcome.value}: {errs[-1:] or res.decision.reasons[-1:]}"
                continue
            pr.raw[mid] = res.text[:6000]
            parsed = parse_review(res.text)
            if not parsed:
                pr.errors[mid] = "unparseable review"
                continue
            pr.reviews[mid] = parsed
        return pr


# a judge qualifies only with >= 4 of the 5 calibration cases right (never lowered to make a model pass)
MIN_PASS_RATE = 0.8


def calibrate(council: VisionCouncil, good_png: Path, bad_pngs: dict[str, Path], intent: str) -> dict[str, Any]:
    """Judge reliability: each model must score the good page above every deliberately broken variant on the
    role that the breakage targets. Returns per-model reliability; unreliable judges are excluded from gates."""
    good = council.review("calibration-good", good_png, intent)
    result: dict[str, Any] = {"models": {}}
    target_role = {"low_contrast": "TypographyJudge", "card_overuse": "AIClicheJudge", "gradient": "APEXBrandJudge",
                   "cramped": "EditorialDesignJudge", "no_hierarchy": "VisualHierarchyJudge"}
    bad_reviews = {k: council.review(f"calibration-{k}", p, intent) for k, p in bad_pngs.items()}
    for mid in council.models:
        checks, scores = {}, {}
        for k, br in bad_reviews.items():
            role = target_role.get(k, "EditorialDesignJudge")
            g = good.reviews.get(mid, {}).get(role, {}).get("score")
            b = br.reviews.get(mid, {}).get(role, {}).get("score")
            checks[k] = None if g is None or b is None else bool(g > b)
            scores[k] = {"role": role, "good": g, "broken": b}
        valid = [v for v in checks.values() if v is not None]
        rate = sum(valid) / len(valid) if valid else None
        complete = len(valid) == len(checks) and len(checks) > 0     # one lucky data point is not calibration
        result["models"][mid] = {"checks": checks, "scores": scores, "discrimination_rate": rate,
                                 "valid_checks": len(valid),
                                 "reliable": complete and rate is not None and rate >= MIN_PASS_RATE,
                                 "errors": {k: br.errors.get(mid) for k, br in bad_reviews.items() if br.errors.get(mid)}
                                 | ({"good": good.errors[mid]} if good.errors.get(mid) else {})}
    return result


def model_digest(model_id: str) -> str | None:
    """sha256 digest of the local GGUF serving `model_id` (None if it is not a local model)."""
    from apex_one.compute.local import load_catalogue

    try:
        _, specs = load_catalogue()
    except Exception:  # noqa: BLE001
        return None
    for spec in specs.values():
        man = spec.dir / "apex_manifest.json"
        if spec.registry_model == model_id and man.exists():
            files = json.loads(man.read_text(encoding="utf-8"))["files"]
            main = next((f for f in files if f["file"].endswith(".gguf") and "mmproj" not in f["file"]), None)
            return main["digest"] if main else None
    return None



# ---------------------------------------------------------------- pipeline integration (VISION_QA)

# Council roles that mirror a deterministic metric share its name, so the DisagreementResolver compares them
# against the DOM measurement; the rest stay council-only.
ROLE_METRIC = {"TypographyJudge": "design.typography", "APEXBrandJudge": "design.brand_fit",
               "ReaderAttentionJudge": "reader.comprehension", "AIClicheJudge": "editorial.human_or_model_judgement",
               "VisualHierarchyJudge": "council.visual_hierarchy", "EditorialDesignJudge": "council.editorial_design"}
MAX_CALIBRATION_AGE_DAYS = 30
PAGE_BUDGET = {"draft": 0, "standard": 2, "high": 4, "ultra": 6}
PRIORITY = ["Cover", "OpportunitySnapshot", "Opening", "ApexTake", "Closing", "HeroFact", "Timeline", "FundingChapter"]


def calibration_path() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "bench" / "vision_calibration" / "calibration_results.json"


def reliable_judges(path: Path | None = None, mode: str = "absolute") -> tuple[list[str], dict[str, Any]]:
    """Only judges that passed calibration may influence gates. No calibration => no council (NOT_MEASURED).
    mode="absolute": the six-role scoring council; mode="pairwise": finalist A/B judging. They are calibrated
    separately on the same five cases and a pass in one never qualifies the other."""
    path = path or calibration_path()
    if not path.exists():
        return [], {"reason": f"no calibration results at {path}"}
    from datetime import UTC, datetime, timedelta

    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models" if mode == "absolute" else "pairwise_models", {})
    ok = []
    for m, r in models.items():
        if not r.get("reliable"):
            continue
        why = None
        checks = r.get("checks") or {}
        if r.get("valid_checks") != len(checks) or not checks or None in checks.values():
            why = "incomplete calibration"
        elif sum(bool(v) for v in checks.values()) / len(checks) < MIN_PASS_RATE:
            why = f"below the calibration bar ({sum(bool(v) for v in checks.values())}/{len(checks)}; >= 4/5 needed)"
        elif not r.get("at") or datetime.fromisoformat(r["at"]) < datetime.now(UTC) - timedelta(days=MAX_CALIBRATION_AGE_DAYS):
            why = "calibration missing a timestamp or older than %d days" % MAX_CALIBRATION_AGE_DAYS
        elif r.get("model_digest") != model_digest(m):
            why = "calibrated a different model build (digest mismatch)"
        if why:
            r["rejected"] = why
        else:
            ok.append(m)
    return sorted(ok), models


def page_budget(mode: str) -> int:
    import os

    env = os.environ.get("APEX_VISION_COUNCIL_PAGES")
    return int(env) if env and env.isdigit() else PAGE_BUDGET.get(mode, 0)


def select_pages(pages: list[dict[str, Any]], budget: int) -> list[str]:
    """Decision-critical and loud pages first; the rest in reading order."""
    order = sorted(range(len(pages)), key=lambda i: (PRIORITY.index(pages[i].get("nodeType"))
                                                     if pages[i].get("nodeType") in PRIORITY else len(PRIORITY), i))
    return [pages[i]["pageId"] for i in order[:budget]]


def document_metrics(reviews: list[PageReview]) -> dict[str, Metric]:
    """Per role: median over reviewed pages of the per-page council median."""
    out: dict[str, Metric] = {}
    for role, name in ROLE_METRIC.items():
        vals = [m.value for m in (r.role_metric(role) for r in reviews) if m.value is not None]
        if not vals:
            out[role] = Metric.not_measured(name, "vision council produced no valid review for this role")
            continue
        out[role] = Metric.measured(name, statistics.median(vals),
                                    f"vision council {role}: median over {len(vals)} page(s) of the cross-model median",
                                    evidence=[f"{r.page_id}={r.role_metric(role).value}" for r in reviews
                                              if r.role_metric(role).value is not None])
    return out


def weak_pages(reviews: list[PageReview], floor: float = 70.0) -> dict[str, list[str]]:
    """Pages the council says need repair: any role median below `floor` or a critical problem from any judge."""
    weak: dict[str, list[str]] = {}
    for r in reviews:
        why = [f"{role} median {r.role_metric(role).value:.0f} < {floor:.0f}" for role in ROLES
               if r.role_metric(role).value is not None and r.role_metric(role).value < floor]
        why += [f"{m}/{role}: critical — {p['issue']}" for m, rv in r.reviews.items() for role, x in rv.items()
                for p in x["problems"] if p["severity"] == "critical"]
        if why:
            weak[r.page_id] = why
    return weak
