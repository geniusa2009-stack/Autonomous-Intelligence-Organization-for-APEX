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


# ---------------------------------------------------------------- Phase 25: A/B/C preference dataset

TAGS = ["hierarchy", "typography", "arabic-shaping", "rhythm", "whitespace", "density", "brand", "premium",
        "generic", "card-like", "numbers", "contrast", "novelty", "too-similar", "calm", "busy"]
LABELS = "ABCDEF"


class APEXPreferenceRecord(ApexModel):
    """One human judgement over an A/B/C sheet. Stored as a dataset row; NEVER used for training automatically."""

    job_id: str
    page_id: str
    labels: dict[str, str]          # A -> candidate_id
    ranking: list[str]              # labels best-first, e.g. ["B", "A", "C"]
    winner: str                     # label
    reason: str
    tags: list[str] = []
    annotator: str
    at: str = ""


def validate_record(rec: APEXPreferenceRecord) -> list[str]:
    probs = []
    if sorted(rec.ranking) != sorted(rec.labels):
        probs.append(f"ranking {rec.ranking} must order exactly the labels {sorted(rec.labels)}")
    if rec.ranking and rec.winner != rec.ranking[0]:
        probs.append("winner must be the first label of the ranking")
    bad = [t for t in rec.tags if t not in TAGS]
    if bad:
        probs.append(f"unknown tags {bad}; allowed: {TAGS}")
    if not rec.reason.strip():
        probs.append("a reason is required")
    return probs


def build_abc_sheet(runner, page_id: str, out_dir: Path | None = None) -> dict[str, Any]:
    """Render the page's tournament finalists and write an A/B/C sheet (HTML) with SEPARATE metrics per option."""
    from apex_one.design.genome import load_genome
    from apex_one.document.compiler import compile_document, compile_page
    from apex_one.core.schemas.design import LayoutCandidate
    from apex_one.vision.render import Renderer, ensure_fonts

    search = {r["page_id"]: r for r in runner.ws.read_json("layout_search.json")}
    if page_id not in search:
        raise KeyError(f"page {page_id} not in layout_search.json")
    cands = [LayoutCandidate.model_validate(c) for c in search[page_id]["top"]][: len(LABELS)]
    pages = runner._ast().pages()
    node = next(n for n in pages if n.node_id == page_id)
    page_no = pages.index(node) + 1
    out = out_dir or runner.ws.root / "preference"
    out.mkdir(parents=True, exist_ok=True)
    ensure_fonts(out)
    genome = load_genome()
    locks = {lk.slot: lk for lk in runner.locks}
    compiled = [compile_page(node, c.genes, genome, locks, page_no=page_no, total_pages=len(pages),
                             synthetic=runner.synthetic, seed=runner.job.policy.seed + page_no,
                             scope=f"c-{c.candidate_id}") for c in cands]
    html = out / f"finalists-{page_id}.html"
    html.write_text(compile_document(compiled, genome, title="finalists", synthetic=runner.synthetic), encoding="utf-8")
    with Renderer() as r:
        res = r.measure(html, float(genome.invariants["page"]["min_margin_mm"]), screenshot_dir=out,
                        screenshot_prefix=f"abc-{page_id}")
    labels = {LABELS[i]: c.candidate_id for i, c in enumerate(cands)}
    shown = ["design.hierarchy", "design.typography", "design.brand_fit", "density_fit", "novelty", "ink"]
    cells = []
    for i, (c, shot) in enumerate(zip(cands, res.page_screenshots)):
        rows = "".join(f"<tr><td>{m}</td><td>{'' if c.metrics.get(m) is None or c.metrics[m].value is None else round(c.metrics[m].value, 1)}</td></tr>"
                       for m in shown)
        cells.append(f'<figure><figcaption>{LABELS[i]}</figcaption><img src="{shot.name}" alt="option {LABELS[i]}">'
                     f"<table>{rows}</table><p>{c.genes.archetype} · {c.genes.tone}</p></figure>")
    sheet = out / f"abc-{page_id}.html"
    sheet.write_text(
        "<!doctype html><meta charset='utf-8'><title>A/B/C</title><style>body{font-family:sans-serif;background:#ECEFF3;"
        "margin:16px}main{display:flex;gap:16px;flex-wrap:wrap}figure{background:#fff;margin:0;padding:12px;width:300px}"
        "img{width:100%;border:1px solid #A9B3C1}figcaption{font-size:28px;font-weight:700;color:#0A1A33}"
        "td{font-size:12px;padding:2px 6px}</style>"
        f"<h1>{node.semantic_type.value} · {page_id}</h1><p>Rank the options (e.g. B > A > C), give one reason and tags "
        f"from: {', '.join(TAGS)}. Metrics are shown separately on purpose — there is no single score.</p>"
        f"<main>{''.join(cells)}</main>", encoding="utf-8")
    (out / f"abc-{page_id}.json").write_text(json.dumps({"labels": labels}, indent=2), encoding="utf-8")
    return {"sheet": str(sheet), "labels": labels}


def record_abc(runner, page_id: str, ranking: list[str], reason: str, tags: list[str], annotator: str,
               dataset: Path | None = None, db_url: str | None = None) -> APEXPreferenceRecord:
    """Store one A/B/C judgement: a dataset row (JSONL) + the implied pairwise preferences (DB)."""
    from apex_one.settings import get_settings

    lab = runner.ws.root / "preference" / f"abc-{page_id}.json"
    if not lab.exists():
        raise FileNotFoundError("build the A/B/C sheet first (apex-one preference sheet)")
    labels = json.loads(lab.read_text(encoding="utf-8"))["labels"]
    rec = APEXPreferenceRecord(job_id=runner.job.job_id, page_id=page_id, labels=labels, ranking=ranking,
                               winner=ranking[0] if ranking else "", reason=reason, tags=tags, annotator=annotator,
                               at=datetime.now(UTC).isoformat())
    probs = validate_record(rec)
    if probs:
        raise ValueError("; ".join(probs))
    search = {r["page_id"]: r for r in runner.ws.read_json("layout_search.json")}
    feats = {c["candidate_id"]: candidate_features(c["genes"], c["metrics"]) for c in search[page_id]["top"]}
    PreferenceMemory(db_url).record_ranking([labels[x] for x in ranking], reasons=[reason, *(f"tag:{t}" for t in tags)],
                                            annotator=annotator, features=feats, job_id=runner.job.job_id,
                                            page_id=page_id)
    path = dataset or get_settings().artifacts_dir / "preference" / "abc_dataset.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(rec.model_dump_json() + "\n")
    return rec
