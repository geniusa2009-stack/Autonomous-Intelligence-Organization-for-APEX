"""Deterministic date arithmetic — the ONLY place critical dates are calculated.

Rule (enforced by the broker): critical date arithmetic never relies on free-form model reasoning. Tasks named
``date.*`` cannot be routed to any model. Models may EXPLAIN a result computed here; if a model states a different
date, the computed date wins and the disagreement is recorded (``reconcile``).

Regression anchor: on 2026-10-10, with a 2026-11-01 deadline, results taking 10 days and tests only on Saturdays,
the latest test date is 2026-10-17 (local models answered 2026-10-26 and 2026-10-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

SATURDAY = 5


def latest_weekday_on_or_before(d: date, weekday: int) -> date:
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def latest_test_date(deadline: date, result_days: int, test_weekdays: set[int] | frozenset[int] = frozenset({SATURDAY}),
                     today: date | None = None) -> date | None:
    """Latest test day whose results (taking `result_days`) arrive ON OR BEFORE `deadline`. None if impossible."""
    last = deadline - timedelta(days=result_days)
    for back in range(7):
        d = last - timedelta(days=back)
        if d.weekday() in test_weekdays:
            return d if today is None or d >= today else None
    return None


def days_until(target: date, today: date) -> int:
    return (target - today).days


def plan_backwards(deadline: date, steps: list[tuple[str, int]]) -> list[tuple[str, date]]:
    """Each step needs `lead_days` before the NEXT milestone; returns the latest start date per step, last first."""
    out, cursor = [], deadline
    for name, lead in reversed(steps):
        cursor = cursor - timedelta(days=lead)
        out.append((name, cursor))
    return list(reversed(out))


@dataclass(frozen=True)
class Reconciled:
    value: date
    model_value: str | None
    agreed: bool
    note: str


def reconcile(computed: date, model_answer: str | None) -> Reconciled:
    """The deterministic value always wins; a differing model answer is surfaced, never silently used."""
    if model_answer is None:
        return Reconciled(computed, None, False, "no model answer; deterministic value used")
    agreed = model_answer.strip() == computed.isoformat()
    return Reconciled(computed, model_answer, agreed,
                      "model agrees with the deterministic engine" if agreed else
                      f"model said {model_answer}; deterministic engine says {computed.isoformat()} — engine wins")
