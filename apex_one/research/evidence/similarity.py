"""Semantic grouping of claim values (text values are compared by token-set similarity)."""

from __future__ import annotations

import re

from apex_one.core.schemas.evidence import Claim, ValueType

_STOP = {"the", "a", "an", "is", "are", "be", "of", "and", "form", "to", "for", "will", "must", "all", "by"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9؀-ۿ\-]+", s.lower()) if t not in _STOP}


def text_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def group_values(claims: list[Claim], threshold: float = 0.75) -> dict[str, list[Claim]]:
    """Group claims whose values mean the same thing. Non-text values group by exact canonical key."""
    groups: dict[str, list[Claim]] = {}
    reps: dict[str, str] = {}
    for c in claims:
        key = c.value.key()
        if c.value.type == ValueType.TEXT:
            for gkey, rep in reps.items():
                if text_similarity(rep, c.value.canonical) >= threshold:
                    key = gkey
                    break
            else:
                reps[key] = c.value.canonical
        groups.setdefault(key, []).append(c)
    return groups
