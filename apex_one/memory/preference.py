"""APEX preference learning: human rankings (B > A > C) with reasons -> APEXPreferencePair dataset ->
optional small local Bradley-Terry scorer. Training requires explicit human approval and produces a
CANDIDATE scorer that only ONE Lab can promote."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select

from apex_one.core.schemas.common import ApexModel
from apex_one.persistence.db import session_scope
from apex_one.persistence.models import PreferencePairRow

REASONS = ["less card-like", "stronger hierarchy", "cleaner Arabic", "more premium", "too generic", "too busy",
           "too similar to old guide", "better rhythm", "clearer numbers", "more breathing room"]
FEATURES = ["type_scale_ratio", "base_font_px", "density", "whitespace", "asymmetry", "margin_mm",
            "design.hierarchy", "design.typography", "design.brand_fit", "density_fit", "novelty"]


class APEXPreferencePair(ApexModel):
    job_id: str | None = None
    page_id: str | None = None
    winner: str
    loser: str
    reasons: list[str] = []
    annotator: str = "human"
    winner_features: dict[str, float] = {}
    loser_features: dict[str, float] = {}


def candidate_features(genes: dict[str, Any], metrics: dict[str, Any]) -> dict[str, float]:
    f: dict[str, float] = {}
    for k in FEATURES:
        if k in genes and isinstance(genes[k], (int, float)):
            f[k] = float(genes[k])
        elif k in metrics and isinstance(metrics[k], dict) and metrics[k].get("value") is not None:
            f[k] = float(metrics[k]["value"])
    return f


class PreferenceMemory:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url

    def record_ranking(self, ranking: list[str], *, reasons: list[str], annotator: str,
                       features: dict[str, dict[str, float]] | None = None, job_id: str | None = None,
                       page_id: str | None = None) -> list[APEXPreferencePair]:
        if len(ranking) < 2:
            raise ValueError("a ranking needs at least two candidates")
        features = features or {}
        pairs = []
        with session_scope(self.db_url) as s:
            for w, l in combinations(ranking, 2):     # ranking order: best first
                p = APEXPreferencePair(job_id=job_id, page_id=page_id, winner=w, loser=l, reasons=reasons,
                                       annotator=annotator, winner_features=features.get(w, {}),
                                       loser_features=features.get(l, {}))
                s.add(PreferencePairRow(**p.model_dump()))
                pairs.append(p)
        return pairs

    def pairs(self) -> list[APEXPreferencePair]:
        with session_scope(self.db_url) as s:
            rows = s.execute(select(PreferencePairRow)).scalars().all()
            return [APEXPreferencePair(job_id=r.job_id, page_id=r.page_id, winner=r.winner, loser=r.loser,
                                       reasons=r.reasons, annotator=r.annotator, winner_features=r.winner_features,
                                       loser_features=r.loser_features) for r in rows]

    def export_jsonl(self, path: Path) -> int:
        ps = self.pairs()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(p.model_dump_json() for p in ps), encoding="utf-8")
        return len(ps)


class PreferenceScorer:
    """Bradley-Terry / logistic model on feature differences. Small, local, inspectable."""

    def __init__(self, weights: dict[str, float] | None = None, means: dict[str, float] | None = None,
                 scales: dict[str, float] | None = None, meta: dict[str, Any] | None = None):
        self.weights = weights or {}
        self.means = means or {}
        self.scales = scales or {}
        self.meta = meta or {}

    @classmethod
    def train(cls, pairs: list[APEXPreferencePair], *, approved_by: str | None, epochs: int = 400,
              lr: float = 0.1, l2: float = 0.01) -> "PreferenceScorer":
        if not approved_by:
            raise PermissionError("training a preference scorer requires explicit human workflow approval")
        usable = [p for p in pairs if p.winner_features and p.loser_features]
        if len(usable) < 3:
            raise ValueError(f"need at least 3 pairs with features, have {len(usable)}")
        keys = sorted(set.intersection(*[set(p.winner_features) & set(p.loser_features) for p in usable]))
        allv = np.array([[p.winner_features[k] for k in keys] for p in usable] +
                        [[p.loser_features[k] for k in keys] for p in usable])
        mu, sd = allv.mean(0), allv.std(0) + 1e-6
        X = np.array([[(p.winner_features[k] - p.loser_features[k]) / sd[i] for i, k in enumerate(keys)]
                      for p in usable])
        X = np.vstack([X, -X])
        y = np.array([1.0] * len(usable) + [0.0] * len(usable))
        w = np.zeros(len(keys))
        for _ in range(epochs):
            z = 1 / (1 + np.exp(-(X @ w)))
            w -= lr * (X.T @ (z - y) / len(y) + l2 * w)
        acc = float(((X @ w > 0) == (y == 1)).mean())
        return cls(dict(zip(keys, w.tolist())), dict(zip(keys, mu.tolist())), dict(zip(keys, sd.tolist())),
                   {"status": "CANDIDATE", "trained_by": approved_by, "pairs": len(usable), "train_accuracy": acc,
                    "trained_at": datetime.now(UTC).isoformat()})

    def score(self, features: dict[str, float]) -> float | None:
        if not self.weights:
            return None
        s = sum(w * features[k] / self.scales[k] for k, w in self.weights.items() if k in features)
        return 100 / (1 + math.exp(-s / 3))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"weights": self.weights, "means": self.means, "scales": self.scales,
                                    "meta": self.meta}, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "PreferenceScorer":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d["weights"], d["means"], d["scales"], d["meta"])
