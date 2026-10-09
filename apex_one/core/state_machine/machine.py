"""State machine engine: validates transitions and recovery budgets."""

from __future__ import annotations

from dataclasses import dataclass, field

from apex_one.core.state_machine.definition import (
    HUMAN_ONLY_TRANSITIONS,
    RECOVERY,
    TRANSITIONS,
    FailureKind,
    S,
)


class IllegalTransition(Exception):
    pass


class RecoveryBudgetExhausted(Exception):
    pass


@dataclass
class StateMachine:
    state: S = S.NEW
    max_recovery_loops: int = 4
    recovery_counts: dict[str, int] = field(default_factory=dict)
    trail: list[tuple[str, str, str]] = field(default_factory=list)

    def can(self, target: S) -> bool:
        return target in TRANSITIONS[self.state]

    def advance(self, target: S, *, reason: str = "", human: bool = False) -> S:
        if (self.state, target) in HUMAN_ONLY_TRANSITIONS and not human:
            raise IllegalTransition(f"{self.state} -> {target} requires a human decision")
        if (self.state, target) in HUMAN_ONLY_TRANSITIONS and human:
            pass
        elif not self.can(target):
            raise IllegalTransition(f"{self.state} -> {target} is not an allowed transition")
        self.trail.append((self.state.value, target.value, reason))
        self.state = target
        return target

    def recover(self, kind: FailureKind, *, reason: str = "") -> S | None:
        """Jump to the failure-specific recovery state. Returns None when the job must wait/block."""
        target = RECOVERY[kind]
        if target is None:
            return None
        used = self.recovery_counts.get(kind.value, 0)
        if used >= self.max_recovery_loops:
            raise RecoveryBudgetExhausted(f"recovery budget for {kind} exhausted ({used})")
        self.recovery_counts[kind.value] = used + 1
        self.trail.append((self.state.value, target.value, f"recover:{kind.value}:{reason}"))
        self.state = target
        return target
