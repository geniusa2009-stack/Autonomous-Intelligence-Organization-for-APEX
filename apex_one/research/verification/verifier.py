"""Verification + semantic resolution + FACT_LOCK.

Critical claims must pass: primary-source search, independent verification, contradiction search,
freshness check and semantic resolution. Anything weaker is NEEDS_HUMAN, never silently locked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from apex_one.core.schemas.evidence import (
    Claim,
    ClaimStatus,
    Contradiction,
    ContradictionKind,
    Criticality,
    FactLock,
    Source,
    SourceKind,
    Verification,
)
from apex_one.research.evidence.normalize import display
from apex_one.research.evidence.similarity import group_values

OFFICIAL = {SourceKind.OFFICIAL, SourceKind.OFFICIAL_DOCUMENT, SourceKind.GOVERNMENT}
CYCLE_SENSITIVE = {"deadline", "decision_date", "test_minimum", "fee", "deposit", "funding", "scholarship_coverage"}
MIN_INDEPENDENT_CRITICAL = 2


@dataclass
class SlotResolution:
    slot: str
    winner: Claim | None
    losers: list[Claim] = field(default_factory=list)
    verification: Verification | None = None


class Verifier:
    def __init__(self, target_cycle_year: int | None):
        self.target = target_cycle_year

    def _fresh(self, src: Source) -> bool:
        return self.target is None or src.cycle_year is None or src.cycle_year == self.target

    def resolve(self, claims: list[Claim], sources: dict[str, Source],
                contradictions: list[Contradiction]) -> list[SlotResolution]:
        xmap = {x.contradiction_id: x for x in contradictions}
        by_slot: dict[str, list[Claim]] = defaultdict(list)
        for c in claims:
            by_slot[c.slot].append(c)
        results: list[SlotResolution] = []
        for slot, group in sorted(by_slot.items()):
            results.append(self._resolve_slot(slot, group, sources, xmap))
        return results

    def _resolve_slot(self, slot: str, group: list[Claim], sources: dict[str, Source],
                      xmap: dict[str, Contradiction]) -> SlotResolution:
        reasons: list[str] = []
        critical = any(c.criticality == Criticality.CRITICAL for c in group)
        predicate = group[0].predicate
        # 1. freshness: drop claims from other cycles (STALE_CYCLE resolution)
        fresh, stale = [], []
        for c in group:
            src = sources[c.source_ids[0]]
            (fresh if self._fresh(src) else stale).append(c)
        for c in stale:
            c.status = ClaimStatus.REJECTED
            c.freshness = "previous-cycle"
            c.notes.append(f"rejected: source describes cycle {sources[c.source_ids[0]].cycle_year}, target {self.target}")
        if stale:
            reasons.append(f"{len(stale)} stale-cycle claim(s) rejected")
        if not fresh:
            ver = Verification(claim_id=group[0].claim_id, primary_source_found=False, independent_sources=0,
                               official_sources=0, contradiction_search_done=True, freshness_ok=False,
                               semantic_resolution="only previous-cycle evidence", verdict=ClaimStatus.NEEDS_HUMAN,
                               reasons=reasons + ["no current-cycle evidence"])
            return SlotResolution(slot, None, stale, ver)

        # 2. group by value; authority-weighted semantic resolution
        # low-authority-only values (forums/rumours) are never facts
        rumours = [c for c in fresh if max(sources[s].authority for s in c.source_ids) < 0.3]
        credible = [c for c in fresh if c not in rumours]
        for c in rumours:
            c.status = ClaimStatus.REJECTED
            c.notes.append("rejected: only low-authority (forum/rumour) support")
        if rumours:
            reasons.append(f"{len(rumours)} low-authority claim(s) rejected")
        if not credible:
            ver = Verification(claim_id=group[0].claim_id, primary_source_found=False, independent_sources=0,
                               official_sources=0, contradiction_search_done=True, freshness_ok=False,
                               semantic_resolution="only low-authority evidence", verdict=ClaimStatus.REJECTED,
                               reasons=reasons)
            return SlotResolution(slot, None, stale + rumours, ver)
        by_value: dict[str, list[Claim]] = defaultdict(list, group_values(credible))

        def official_support(cs: list[Claim]) -> set[str]:
            return {s for c in cs for s in c.source_ids if sources[s].kind in OFFICIAL}

        official_values = {k for k, cs in by_value.items() if official_support(cs)}
        resolution = "single value"
        unresolved = False
        if len(by_value) == 1:
            win_key = next(iter(by_value))
        elif len(official_values) == 1:
            win_key = next(iter(official_values))
            resolution = "official primary source outranks third-party/forum sources"
        elif len(official_values) > 1:
            win_key = max(official_values, key=lambda k: len(official_support(by_value[k])))
            unresolved = True
            resolution = "OFFICIAL SOURCES DISAGREE — human decision required"
        else:
            win_key = max(by_value, key=lambda k: max(sources[s].authority for c in by_value[k] for s in c.source_ids))
            resolution = "no official source; highest-authority value provisionally selected"

        win_claims = by_value[win_key]
        losers = [c for k, cs in by_value.items() if k != win_key for c in cs]
        for c in losers:
            c.status = ClaimStatus.REJECTED
            c.notes.append(f"rejected by semantic resolution: {resolution}")
        for x_id in {x for c in group for x in c.contradiction_ids}:
            x = xmap.get(x_id)
            if x and x.kind in (ContradictionKind.STALE_CYCLE, ContradictionKind.VALUE_CONFLICT,
                                ContradictionKind.UNIT_DIFFERENCE):
                x.resolved = not unresolved
                x.resolution = resolution if not stale or x.kind != ContradictionKind.STALE_CYCLE else \
                    f"previous-cycle values rejected; {resolution}"
                x.winning_claim_id = win_claims[0].claim_id if not unresolved else None

        # 3. merge winner evidence
        winner = win_claims[0].model_copy(deep=True)
        for c in win_claims[1:]:
            winner.evidence_ids += [e for e in c.evidence_ids if e not in winner.evidence_ids]
            winner.source_ids += [s for s in c.source_ids if s not in winner.source_ids]
            winner.notes += [n for n in c.notes if n not in winner.notes]
        for c in win_claims[1:]:
            c.status = ClaimStatus.CORROBORATED
            c.notes.append(f"merged into {winner.claim_id}")

        # 4. verification
        win_sources = [sources[s] for s in winner.source_ids]
        officials = [s for s in win_sources if s.kind in OFFICIAL]
        independent = {(s.domain if s.kind not in OFFICIAL else s.url, s.content_hash) for s in win_sources
                       if s.authority >= 0.3}
        primary = bool(officials)
        cycle_matched = any(s.cycle_year == self.target for s in win_sources) if self.target else True
        freshness_ok = cycle_matched or predicate not in CYCLE_SENSITIVE
        winner.freshness = "current-cycle" if cycle_matched else "undated"
        winner.confidence = round(min(0.99, 0.4 + 0.25 * len(officials) + 0.1 * len(independent)), 2)

        if unresolved:
            verdict = ClaimStatus.NEEDS_HUMAN
            reasons.append("unresolved contradiction between official sources")
        elif critical:
            ok = primary and len(independent) >= MIN_INDEPENDENT_CRITICAL and freshness_ok
            verdict = ClaimStatus.VERIFIED if ok else ClaimStatus.NEEDS_HUMAN
            if not primary:
                reasons.append("no official primary source")
            if len(independent) < MIN_INDEPENDENT_CRITICAL:
                reasons.append(f"only {len(independent)} independent source(s); critical claims need "
                               f"{MIN_INDEPENDENT_CRITICAL}")
            if not freshness_ok:
                reasons.append("no source tied to the target cycle")
        else:
            verdict = ClaimStatus.VERIFIED if primary and freshness_ok else ClaimStatus.CORROBORATED
        winner.status = verdict
        ver = Verification(claim_id=winner.claim_id, primary_source_found=primary, independent_sources=len(independent),
                           official_sources=len(officials), contradiction_search_done=True, freshness_ok=freshness_ok,
                           semantic_resolution=resolution, verdict=verdict, reasons=reasons)
        return SlotResolution(slot, winner, losers + stale + rumours, ver)


class FactLocker:
    """Turns VERIFIED claims into immutable FactLocks."""

    @staticmethod
    def lock(resolutions: list[SlotResolution]) -> list[FactLock]:
        locks = []
        for r in resolutions:
            w = r.winner
            if w is None or w.status != ClaimStatus.VERIFIED:
                continue
            en, ar = display(w.value)
            hedge = "estimated" if any("hedged" in n for n in w.notes) else ""
            locks.append(FactLock(claim_id=w.claim_id, slot=w.slot, predicate=w.predicate, qualifier=w.qualifier,
                                  value=w.value, display_en=en, display_ar=ar, source_ids=list(w.source_ids),
                                  criticality=w.criticality, hedge=hedge))
            w.status = ClaimStatus.LOCKED
        return locks

    @staticmethod
    def human_lock(claim: Claim, by: str) -> FactLock:
        en, ar = display(claim.value)
        claim.status = ClaimStatus.LOCKED
        claim.notes.append(f"verified by human: {by}")
        return FactLock(claim_id=claim.claim_id, slot=claim.slot, predicate=claim.predicate, qualifier=claim.qualifier,
                        value=claim.value, display_en=en, display_ar=ar, source_ids=list(claim.source_ids),
                        criticality=claim.criticality, verified_by=f"human:{by}")
