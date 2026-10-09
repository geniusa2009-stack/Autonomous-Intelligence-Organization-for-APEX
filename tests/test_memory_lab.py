import pytest

from apex_one.memory import (
    DesignMemory,
    EpisodicMemory,
    FailureMemory,
    PreferenceMemory,
    PreferenceScorer,
    SemanticMemory,
    VoiceMemory,
)
from apex_one.persistence import init_db


@pytest.fixture(autouse=True)
def db():
    init_db()


def test_separate_memories():
    SemanticMemory().add("Uni:deadline.application", "1 November 2026", {"cycle": "Fall 2027"})
    EpisodicMemory().add("J-1", "mission", {"states": ["NEW"]})
    DesignMemory().add("sig123", "ledger", verdict="rejected")
    VoiceMemory().add("v1", "فرصة لا تعوض", verdict="rejected")
    FailureMemory().add("RENDER", "overflow", failure_kind="GEOMETRY")
    assert SemanticMemory().search("deadline Uni")[0].text == "1 November 2026"
    assert DesignMemory().signature_verdicts()["sig123"] == "rejected"
    assert "فرصة لا تعوض" in VoiceMemory().rejected_phrases()
    assert FailureMemory().frequent()["GEOMETRY"] == 1
    assert not EpisodicMemory().search("deadline")   # memories do not leak into each other


def test_preference_pairs_and_scorer_requires_approval(tmp_path):
    pm = PreferenceMemory()
    feats = {"B": {"density": 0.4, "design.hierarchy": 95}, "A": {"density": 0.7, "design.hierarchy": 80},
             "C": {"density": 0.9, "design.hierarchy": 60}}
    pairs = pm.record_ranking(["B", "A", "C"], reasons=["less card-like", "stronger hierarchy"], annotator="Human",
                              features=feats)
    assert [(p.winner, p.loser) for p in pairs] == [("B", "A"), ("B", "C"), ("A", "C")]
    assert pm.export_jsonl(tmp_path / "pairs.jsonl") == 3
    with pytest.raises(PermissionError):
        PreferenceScorer.train(pm.pairs(), approved_by=None)
    s = PreferenceScorer.train(pm.pairs(), approved_by="Human")
    assert s.meta["status"] == "CANDIDATE"
    assert s.score(feats["B"]) > s.score(feats["C"])
    s.save(tmp_path / "s.json")
    assert PreferenceScorer.load(tmp_path / "s.json").weights == s.weights


def test_lab_requires_evaluation_before_promotion():
    from apex_one.lab.experiments import decide, propose

    p = propose("hierarchy weak on snapshot pages", {"tournament.weights": {"design.hierarchy": 0.3}}, "apex-one")
    with pytest.raises(RuntimeError):
        decide(p["proposal_id"], "Human", approve=True)
    with pytest.raises(ValueError):
        propose("x", {"cost.max_api_cost_usd": 5}, "apex-one")


def test_research_only_inventory(registry):
    from apex_one.lab.research_only_models import research_only_inventory

    inv = {r["model"]: r for r in research_only_inventory(registry)}
    assert inv["aya-expanse-32b"]["licence_state"] == "NON_COMMERCIAL" and inv["aya-expanse-32b"]["lab_usable"]
    assert "PosterCopilot-7B" in inv


def test_license_guard_blocks_research_only_output(registry):
    from apex_one.release import license_guard

    report, metric = license_guard(registry, ["apex-native-layout", "PosterCopilot-7B"], [])
    assert metric.value == 1 and report["prohibited_in_output"] == ["PosterCopilot-7B"]
    report, metric = license_guard(registry, ["apex-native-layout", "apex-native-compiler"],
                                   [{"model_id": "mock-llm", "outcome": "ok"}])
    assert "mock-llm" in report["prohibited_in_output"]


def test_quality_court_never_imputes_and_resolves_disagreement():
    from apex_one.core.schemas.common import Metric
    from apex_one.qa.court import DisagreementResolver, evaluate_gates, verdict_from_metric

    v1 = verdict_from_metric("DesignJudgeA", Metric.measured("vision.hierarchy", 95, "a"), 85)
    v2 = verdict_from_metric("DesignJudgeB", Metric.measured("vision.hierarchy", 40, "b"), 85)
    resolved, recs = DisagreementResolver({"vision.hierarchy": lambda: Metric.measured("vision.hierarchy", 88, "re-measure")}
                                          ).resolve([v1, v2])
    assert recs[0]["action"] == "re-measured" and resolved[-1].metric.value == 88
    gates = {"critical": {"critical_fact_accuracy": {"threshold": 100, "metric": "fact.critical_accuracy"}},
             "targets": {"novelty": {"threshold": 90, "metric": "design.novelty"}}}
    rep = evaluate_gates("J", {}, gates, [], [])
    assert not rep.release_candidate and "NOT_MEASURED" in rep.release_blockers[0]
    assert rep.gates[1].status == "NOT_MEASURED"
