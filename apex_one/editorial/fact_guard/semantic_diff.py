"""Semantic-diff validation: every date, amount, percentage and number in copy must be bound to a FactLock.

Writers and designers cannot silently alter locked values: anything numeric that is not exactly a
locked value (or an explicitly allowed structural number) is a violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from apex_one.core.schemas.evidence import FactLock, ValueType
from apex_one.research.evidence.normalize import find_dates, find_money, find_percents, to_ascii_digits


@dataclass(frozen=True)
class FactViolation:
    kind: str          # unbound_date | unbound_money | altered_money | unbound_percent | unbound_number
    raw: str
    message: str


class LockRegistry:
    """Read-only view over locks. Mutation attempts raise."""

    def __init__(self, locks: list[FactLock]):
        self._locks = MappingProxyType({lk.slot: lk.model_copy(deep=True) for lk in locks})
        self._hashes = MappingProxyType({lk.slot: lk.lock_hash for lk in locks})

    def __getitem__(self, slot: str) -> FactLock:
        return self._locks[slot].model_copy(deep=True)   # callers get copies; originals cannot be altered

    def __contains__(self, slot: str) -> bool:
        return slot in self._locks

    def slots(self) -> list[str]:
        return list(self._locks)

    def all(self) -> list[FactLock]:
        return [lk.model_copy(deep=True) for lk in self._locks.values()]

    def intact(self) -> bool:
        return all(lk.verify_integrity() and lk.lock_hash == self._hashes[s] for s, lk in self._locks.items())


def semantic_diff(text: str, locks: list[FactLock], *, allowed_numbers: set[str] | None = None,
                  allowed_years: set[int] | None = None) -> list[FactViolation]:
    allowed_numbers = allowed_numbers or set()
    allowed_years = allowed_years or set()
    dates = {lk.value.canonical for lk in locks if lk.value.type == ValueType.DATE}
    money = {(lk.value.currency, lk.value.amount) for lk in locks if lk.value.type == ValueType.MONEY}
    pcts = {lk.value.amount for lk in locks if lk.value.type == ValueType.PERCENT}
    nums = {lk.value.canonical for lk in locks if lk.value.type == ValueType.NUMBER}
    t = to_ascii_digits(text)
    out: list[FactViolation] = []
    covered: list[tuple[int, int]] = []

    for d, raw, pos in find_dates(t):
        covered.append((pos, pos + len(raw)))
        if d.isoformat() not in dates:
            out.append(FactViolation("unbound_date", raw, f"date {d.isoformat()} is not a locked fact"))
    for amt, cur, raw, pos in find_money(t):
        covered.append((pos, pos + len(raw)))
        if (cur, amt) not in money:
            same_cur = [a for c, a in money if c == cur]
            kind = "altered_money" if same_cur else "unbound_money"
            out.append(FactViolation(kind, raw, f"amount {cur} {amt} does not match any locked amount {same_cur}"))
    for p, raw, pos in find_percents(t):
        covered.append((pos, pos + len(raw)))
        if p not in pcts:
            out.append(FactViolation("unbound_percent", raw, f"{p}% is not a locked fact"))
    for m in re.finditer(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w.]*\d)", t):
        if any(a <= m.start() < b for a, b in covered):
            continue
        val = m.group(1).replace(",", "")
        canon = str(int(float(val))) if float(val) == int(float(val)) else val
        if canon in nums or canon in allowed_numbers:
            continue
        if len(canon) == 4 and canon.isdigit() and int(canon) in allowed_years:
            continue
        out.append(FactViolation("unbound_number", m.group(1), f"number {m.group(1)} is not bound to a fact lock"))
    return out
