import pytest

from apex_one.core.state_machine import (
    CHECKS,
    MAIN_PATH,
    FailureKind,
    IllegalTransition,
    RecoveryBudgetExhausted,
    S,
    StateMachine,
)
from apex_one.core.state_machine.definition import TRANSITIONS, total_check_count


def test_main_path_is_walkable_until_human_gate():
    sm = StateMachine()
    for target in MAIN_PATH[1:]:
        if target == S.FINAL:
            with pytest.raises(IllegalTransition):
                sm.advance(target)
            sm.advance(target, human=True)
        else:
            sm.advance(target)
    assert sm.state == S.LEARN


def test_release_candidate_cannot_jump_to_final():
    sm = StateMachine(state=S.RELEASE_CANDIDATE)
    with pytest.raises(IllegalTransition):
        sm.advance(S.FINAL)
    with pytest.raises(IllegalTransition):
        sm.advance(S.FINAL, human=True)


def test_illegal_skip():
    sm = StateMachine()
    with pytest.raises(IllegalTransition):
        sm.advance(S.RENDER)


@pytest.mark.parametrize("kind,target", [
    (FailureKind.FACT, S.SOURCE_EXPANSION), (FailureKind.VOICE, S.DRAFT), (FailureKind.RTL, S.HTML_BUILD),
    (FailureKind.GEOMETRY, S.LAYOUT_SEARCH), (FailureKind.AESTHETIC, S.MUTATION),
    (FailureKind.READER, S.CONTENT_ARCHITECTURE), (FailureKind.RHYTHM, S.CREATIVE_DIRECTIONS),
])
def test_failure_specific_recovery(kind, target):
    sm = StateMachine(state=S.DOCUMENT_QA)
    assert sm.recover(kind) == target


def test_compute_failure_waits_instead_of_restarting():
    sm = StateMachine(state=S.DRAFT)
    assert sm.recover(FailureKind.COMPUTE) is None and sm.state == S.DRAFT


def test_recovery_budget():
    sm = StateMachine(state=S.DOCUMENT_QA, max_recovery_loops=2)
    sm.recover(FailureKind.AESTHETIC)
    sm.recover(FailureKind.AESTHETIC)
    with pytest.raises(RecoveryBudgetExhausted):
        sm.recover(FailureKind.AESTHETIC)


def test_every_state_has_transitions_and_checks():
    for st in S:
        assert st in TRANSITIONS
    assert total_check_count() >= 190
    assert all(CHECKS[s] for s in S if s not in (S.NEW,))
