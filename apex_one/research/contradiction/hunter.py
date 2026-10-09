"""ContradictionHunter: groups claims by slot and classifies disagreements."""

from __future__ import annotations

from collections import defaultdict

from apex_one.research.evidence.similarity import group_values
from apex_one.core.schemas.evidence import (
    Claim,
    Contradiction,
    ContradictionKind,
    Criticality,
    Source,
)


def slot_of(claim: Claim) -> str:
    return claim.slot


class ContradictionHunter:
    def __init__(self, target_cycle_year: int | None):
        self.target = target_cycle_year

    def find(self, claims: list[Claim], sources: dict[str, Source]) -> list[Contradiction]:
        by_slot: dict[str, list[Claim]] = defaultdict(list)
        for c in claims:
            by_slot[c.slot].append(c)
        out: list[Contradiction] = []
        for slot, group in sorted(by_slot.items()):
            values = set(group_values(group))
            if len(values) < 2:
                continue
            critical = any(c.criticality == Criticality.CRITICAL for c in group)
            fresh = [c for c in group if sources[c.source_ids[0]].cycle_year in (None, self.target)]
            fresh_values = set(group_values(fresh)) if fresh else set()
            years = {sources[c.source_ids[0]].cycle_year for c in group if c.source_ids}
            currencies = {c.value.currency for c in group if c.value.currency}
            if self.target and len(fresh_values) < 2:
                kind = ContradictionKind.STALE_CYCLE
                desc = f"values differ across cycles {sorted(y for y in years if y)} (target {self.target})"
            elif len(currencies) > 1:
                kind, desc = ContradictionKind.UNIT_DIFFERENCE, f"currencies differ: {sorted(currencies)}"
            else:
                kind, desc = ContradictionKind.VALUE_CONFLICT, f"{len(values)} different values: {sorted(values)}"
            x = Contradiction(slot=slot, claim_ids=[c.claim_id for c in group], kind=kind, description=desc,
                              critical=critical)
            for c in group:
                c.contradiction_ids.append(x.contradiction_id)
            out.append(x)
        # scope differences: same predicate, qualifiers differ only by scope word, values differ
        by_pred: dict[str, list[Claim]] = defaultdict(list)
        for c in claims:
            by_pred[c.predicate].append(c)
        for pred, group in by_pred.items():
            base = {c.qualifier.replace(" domestic", "") for c in group}
            scoped = [c for c in group if c.qualifier.endswith("domestic")]
            if scoped and len(base) < len({c.qualifier for c in group}):
                out.append(Contradiction(slot=f"{pred}.*", claim_ids=[c.claim_id for c in scoped],
                                         kind=ContradictionKind.SCOPE_DIFFERENCE,
                                         description="domestic-only values present; kept as separate scope",
                                         resolved=True, resolution="different scopes; international scope used",
                                         critical=False))
        return out
