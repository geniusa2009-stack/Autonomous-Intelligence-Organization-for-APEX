"""Phase 24 — Mixture of Design Experts with semantic routing.

Experts are whole design systems that can produce a page: the native APEX tournament, the native baseline, and any
model-backed page generator measured by the APEX design bench (``llm:<model_id>``). The GATE is semantic: it looks
at the page's meaning (semantic type → reading family) and routes to the experts with the best MEASURED evidence for
that type — falling back to evidence from the same reading family, then to the native tournament.

Rules:
* evidence only — an expert never benchmarked on a page family is never preferred over one that was;
* separate metrics stay visible in the rationale (no hidden single score);
* licence gate per purpose: model experts with an UNKNOWN licence may be routed for ``evaluation`` but never for
  ``production`` (content they write would ship);
* top-k: the gate returns up to k experts so the tournament / pairwise council can arbitrate between them.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apex_one.core.schemas.document import NodeType

FAMILY = {
    "glance": [NodeType.COVER, NodeType.HERO_FACT, NodeType.BREATH],
    "scan": [NodeType.OPPORTUNITY_SNAPSHOT, NodeType.TIMELINE, NodeType.CHECKLIST, NodeType.COMPARISON],
    "read": [NodeType.OPENING, NodeType.APEX_TAKE, NodeType.PROFILE_STORY, NodeType.CLOSING, NodeType.WARNING],
    "study": [NodeType.FUNDING_CHAPTER, NodeType.ELIGIBILITY_CHAPTER, NodeType.APPLICATION_JOURNEY],
}
FAMILY_OF = {t.value: fam for fam, ts in FAMILY.items() for t in ts}
QUALITY = ["design.hierarchy", "design.typography", "design.brand_fit", "rtl.quality", "accessibility.contrast"]
NATIVE = {"native-tournament", "native-baseline"}
DEFAULT = "native-tournament"
MARGIN = 2.0          # quality points another expert must gain over the default (same failure rate) to be preferred


@dataclass
class ExpertChoice:
    page_type: str
    experts: list[str]
    gate: str                                   # exact-type | family | default
    evidence: dict[str, Any] = field(default_factory=dict)
    excluded: dict[str, str] = field(default_factory=dict)


def bench_rows_path() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "bench" / "apex_design" / "apex_design_bench_rows.jsonl"


def load_evidence(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or bench_rows_path()
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _expert_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    produced = [r for r in rows if r["produced"]]
    per_metric = {m: round(statistics.mean(v), 1) for m in QUALITY
                  if (v := [r["metrics"][m] for r in produced if r["metrics"].get(m) is not None])}
    critical_rate = sum(1 for r in rows if r["critical"] or r["contract"]) / len(rows)
    quality = statistics.mean(per_metric.values()) if per_metric else 0.0
    return {"pages": len(rows), "produced": len(produced), "critical_or_contract_rate": round(critical_rate, 3),
            "metrics": per_metric,
            # gate key: failure rate first (a broken page is never "beautiful"), then mean quality
            "gate_key": (round(-critical_rate, 3), round(quality, 1))}


class DesignMoE:
    def __init__(self, registry=None, evidence: list[dict[str, Any]] | None = None, k: int = 2):
        self.registry, self.k = registry, k
        self.rows = load_evidence() if evidence is None else evidence

    def _eligible(self, expert: str, purpose: str) -> tuple[bool, str]:
        if expert in NATIVE:
            return True, "native engine (APEX licence)"
        if not expert.startswith("llm:"):
            return False, "unknown expert kind"
        if purpose == "evaluation":
            return True, "evaluation purpose: measured only, never shipped"
        if self.registry is None:
            return False, "no registry to verify the model licence"
        mid = expert.split(":", 1)[1]
        try:
            lic = self.registry.license_for(mid)
        except Exception:  # noqa: BLE001
            return False, f"model {mid} not in registry"
        return (lic.production_allowed, f"licence {lic.id}: {lic.production_state.value}")

    def route(self, page_type: str, purpose: str = "production") -> ExpertChoice:
        excluded: dict[str, str] = {}
        experts = sorted({r["system"] for r in self.rows})
        eligible = []
        for e in experts:
            ok, why = self._eligible(e, purpose)
            if ok:
                eligible.append(e)
            else:
                excluded[e] = why
        for gate, match in (("exact-type", lambda r: r["page_type"] == page_type),
                            ("family", lambda r: FAMILY_OF.get(r["page_type"]) == FAMILY_OF.get(page_type))):
            stats = {e: _expert_stats(rs) for e in eligible if (rs := [r for r in self.rows if r["system"] == e and match(r)])}
            if stats:
                ranked = sorted(stats, key=lambda e: stats[e]["gate_key"], reverse=True)
                if DEFAULT in stats and ranked[0] != DEFAULT:
                    top, dflt = stats[ranked[0]]["gate_key"], stats[DEFAULT]["gate_key"]
                    if top[0] == dflt[0] and top[1] - dflt[1] < MARGIN:
                        # saturated / near-equal evidence is not a reason to leave the default expert
                        ranked.remove(DEFAULT)
                        ranked.insert(0, DEFAULT)
                        gate += f"+default-held(margin<{MARGIN})"
                return ExpertChoice(page_type, ranked[: self.k], gate, {e: stats[e] for e in ranked}, excluded)
        return ExpertChoice(page_type, [DEFAULT], "default", {"reason": "no measured evidence for this page family"},
                            excluded)
