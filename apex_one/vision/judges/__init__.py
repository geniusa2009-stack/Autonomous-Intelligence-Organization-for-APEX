"""ONE Vision judges. They inspect RENDERED images.

* NativeVisionProxy answers only what is measurable (first fixation via DOM saliency, card overuse,
  whitespace vs intent, similarity to neighbours/history). Subjective questions -> NOT_MEASURED.
* ModelVisionJudge asks a $0 vision-capable model (via the ComputeBroker) with the screenshot attached.
* PosterRewardJudge uses a PosterReward-class specialist when one is available and licence-eligible.
No judge ever produces a single aggregate "truth" score: each criterion is a separate verdict.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from apex_one.compute.providers import ChatMessage
from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.compute import CapabilityRequest
from apex_one.core.schemas.quality import JudgeVerdict

VISION_QUESTIONS = {
    "vision.first_fixation": "Where does the eye go first, and is that the intended element?",
    "vision.hierarchy": "Is the hierarchy clear?",
    "vision.arabic_natural": "Is the Arabic typography visually natural (shaping, spacing, rag)?",
    "vision.memorable": "Is the page memorable?",
    "vision.generic_ai_look": "Does it look generic or AI-generated? (100 = not at all)",
    "vision.card_overuse": "Does it overuse cards? (100 = no card overuse)",
    "vision.whitespace_intent": "Is the whitespace intentional?",
    "vision.brand_belonging": "Does it belong to APEX (deep navy, silver, white, premium editorial precision)?",
    "vision.history_similarity": "Is it too similar to previous pages? (100 = clearly distinct)",
}
SUBJECTIVE = {"vision.arabic_natural", "vision.memorable", "vision.generic_ai_look", "vision.brand_belonging"}


class NativeVisionProxy:
    name = "apex-native-vision-proxy"

    def judge(self, page_metrics: dict, page_qa_metrics: dict[str, Metric], similarity_prev: float | None,
              intended_first: str | None, predicted_first: str | None) -> list[JudgeVerdict]:
        out = []
        ff_ok = intended_first is not None and intended_first == predicted_first
        out.append(JudgeVerdict(judge=self.name, engine=self.name, metric=Metric.measured(
            "vision.first_fixation", 100.0 if ff_ok else 40.0, "DOM saliency prediction vs intended first fixation"),
            passed=ff_ok, rationale=[f"predicted={predicted_first}", f"intended={intended_first}"]))
        h = page_qa_metrics.get("design.hierarchy")
        if h is not None and h.value is not None:
            out.append(JudgeVerdict(judge=self.name, engine=self.name,
                                    metric=Metric.measured("vision.hierarchy", h.value, h.method), passed=h.value >= 80))
        cards = len(page_metrics.get("cardLike", []))
        out.append(JudgeVerdict(judge=self.name, engine=self.name, metric=Metric.measured(
            "vision.card_overuse", max(0.0, 100 - 25 * cards), "count of card-like boxes in DOM"), passed=cards <= 2))
        ws = 1 - page_metrics.get("coverage", 0)
        out.append(JudgeVerdict(judge=self.name, engine=self.name, metric=Metric.measured(
            "vision.whitespace_intent", 100.0 if 0.45 <= ws <= 0.92 else 60.0,
            "whitespace ratio within the intentional band 45–92%"), passed=0.45 <= ws <= 0.92,
            rationale=[f"whitespace={ws:.2f}"]))
        if similarity_prev is not None:
            out.append(JudgeVerdict(judge=self.name, engine=self.name, metric=Metric.measured(
                "vision.history_similarity", 100 * (1 - max(0.0, similarity_prev - 0.5) * 2),
                "dHash similarity to the previous page"), passed=similarity_prev < 0.92))
        for q in sorted(SUBJECTIVE):
            out.append(JudgeVerdict(judge=self.name, engine=self.name,
                                    metric=Metric.not_measured(q, "subjective: requires a vision model or a human"),
                                    passed=None))
        return out


class ModelVisionJudge:
    """Subjective visual critique by a $0 vision-capable model. Returns NOT_MEASURED when none is routable."""

    name = "model-vision-judge"

    def __init__(self, broker, purpose: str = "production"):
        self.broker, self.purpose = broker, purpose

    def judge(self, png: Path, intent_text: str, workspace=None) -> list[JudgeVerdict]:
        req = CapabilityRequest(task="vision.judge", vision=True, purpose=self.purpose)
        b64 = base64.b64encode(png.read_bytes()).decode()
        prompt = ("You are a strict senior editorial art director for APEX (Egyptian student guides). Score 0-100 "
                  "each criterion for THIS rendered page and give one-line reasons. Return JSON {criterion:{score,reason}}. "
                  f"Intent: {intent_text}. Criteria: " + json.dumps(VISION_QUESTIONS, ensure_ascii=False))
        res = self.broker.complete(req, [ChatMessage("user", prompt, images_b64_png=[b64])], json_mode=True,
                                   workspace=workspace, max_tokens=900)
        if not res.executed or not res.text:
            return [JudgeVerdict(judge=self.name, engine="none", passed=None,
                                 metric=Metric.not_measured(q, f"no $0 vision route: {res.decision.outcome.value}"))
                    for q in VISION_QUESTIONS]
        try:
            data = json.loads(re.search(r"\{.*\}", res.text, re.S).group(0))  # type: ignore[union-attr]
        except Exception:
            data = {}
        out = []
        for q in VISION_QUESTIONS:
            item = data.get(q) or {}
            try:
                score = float(item.get("score"))
                out.append(JudgeVerdict(judge=self.name, engine=res.model_id or "", passed=score >= 80,
                                        metric=Metric.measured(q, score, f"vision model {res.model_id}"),
                                        rationale=[str(item.get("reason", ""))[:200]]))
            except (TypeError, ValueError):
                out.append(JudgeVerdict(judge=self.name, engine=res.model_id or "", passed=None,
                                        metric=Metric.not_measured(q, "model returned no parseable score")))
        return out


class PosterRewardJudge:
    """Separate scores (never one aggregate): aesthetic, typography, layout, text quality, artifacts, intent fidelity."""

    CRITERIA = ("aesthetic", "typography", "layout", "text_quality", "artifacts", "intent_fidelity")

    def __init__(self, adapter=None, purpose: str = "production"):
        self.adapter, self.purpose = adapter, purpose

    def judge(self, png: Path, intent_text: str) -> list[JudgeVerdict]:
        if self.adapter is None:
            return [JudgeVerdict(judge="PosterReward", engine="none", passed=None,
                                 metric=Metric.not_measured(f"reward.{c}", "PosterReward not available / not licence-eligible"))
                    for c in self.CRITERIA]
        res = self.adapter.invoke("design_reward", {"spec": {"intent": intent_text},
                                                    "image_b64": base64.b64encode(png.read_bytes()).decode()},
                                  purpose=self.purpose)
        out = []
        for c in self.CRITERIA:
            v = (res.output or {}).get(c)
            out.append(JudgeVerdict(judge="PosterReward", engine=self.adapter.model_id, passed=None if v is None else v >= 80,
                                    metric=Metric.measured(f"reward.{c}", float(v), "PosterReward") if v is not None
                                    else Metric.not_measured(f"reward.{c}", "missing in model output")))
        return out
