"""ONE Quality Court: independent judges + DisagreementResolver. No majority voting on critical matters."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from apex_one.core.schemas.common import Metric, MetricStatus
from apex_one.core.schemas.quality import GateResult, JudgeVerdict, QualityReport

CRITICAL_JUDGES = {"FactJudge", "RTLJudge", "PrintJudge", "LicenseJudge"}


def verdict_from_metric(judge: str, metric: Metric, threshold: float | None, *, critical: bool = False,
                        lower_is_better: bool = False, engine: str = "deterministic") -> JudgeVerdict:
    if metric.status != MetricStatus.MEASURED or metric.value is None:
        return JudgeVerdict(judge=judge, metric=metric, passed=None, critical=critical, engine=engine,
                            rationale=[metric.reason or "not measured"])
    passed = (metric.value <= threshold) if lower_is_better else (threshold is None or metric.value >= threshold)
    return JudgeVerdict(judge=judge, metric=metric, passed=passed, critical=critical, engine=engine,
                        rationale=[f"{metric.name}={metric.value:.1f} vs {threshold}", metric.method])


class DisagreementResolver:
    """When independent judges of the same criterion disagree strongly, investigate with a targeted test.

    `targeted_tests` maps a criterion to a callable returning a fresh measured Metric (e.g. re-run the
    deterministic check on the specific page). The re-measurement decides; votes never do.
    """

    SPREAD = 25.0

    def __init__(self, targeted_tests: dict[str, Callable[[], Metric]] | None = None):
        self.tests = targeted_tests or {}

    def resolve(self, verdicts: list[JudgeVerdict]) -> tuple[list[JudgeVerdict], list[dict]]:
        by: dict[str, list[JudgeVerdict]] = defaultdict(list)
        for v in verdicts:
            by[v.metric.name].append(v)
        records, resolved = [], list(verdicts)
        for name, vs in by.items():
            measured = [v for v in vs if v.metric.value is not None]
            if len(measured) < 2:
                continue
            vals = [v.metric.value for v in measured]  # type: ignore[misc]
            if max(vals) - min(vals) < self.SPREAD and len({v.passed for v in measured}) == 1:
                continue
            rec = {"criterion": name, "judges": {v.judge: v.metric.value for v in measured}, "action": "investigate"}
            test = self.tests.get(name)
            if test is not None:
                m = test()
                rec["targeted_test"] = {"value": m.value, "method": m.method}
                resolved.append(JudgeVerdict(judge="DisagreementResolver", metric=m,
                                             passed=None if m.value is None else m.value >= min(vals),
                                             critical=any(v.critical for v in measured),
                                             rationale=["targeted re-measurement after judge disagreement"]))
                rec["action"] = "re-measured"
            else:
                rec["action"] = "escalated to human review (no targeted test available)"
            records.append(rec)
        return resolved, records


def evaluate_gates(job_id: str, metrics: dict[str, Metric], gates_cfg: dict, verdicts: list[JudgeVerdict],
                   disagreements: list[dict]) -> QualityReport:
    rep = QualityReport(job_id=job_id, verdicts=verdicts, disagreements=disagreements)
    for name, spec in gates_cfg.get("critical", {}).items():
        m = metrics.get(spec["metric"]) or Metric.not_measured(spec["metric"], "metric not produced")
        if m.status != MetricStatus.MEASURED or m.value is None:
            status = "NOT_MEASURED"
            rep.release_blockers.append(f"critical gate {name} NOT_MEASURED ({m.reason})")
        elif "max" in spec:
            status = "PASS" if m.value <= spec["max"] else "FAIL"
        else:
            status = "PASS" if m.value >= spec["threshold"] else "FAIL"
        if status == "FAIL":
            rep.release_blockers.append(f"critical gate {name} FAILED ({m.value} vs {spec.get('threshold', spec.get('max'))})")
        rep.gates.append(GateResult(gate=name, kind="critical", threshold=spec.get("threshold", spec.get("max")),
                                    metric=m, status=status))
    for name, spec in gates_cfg.get("targets", {}).items():
        m = metrics.get(spec["metric"]) or Metric.not_measured(spec["metric"], "metric not produced")
        if m.status != MetricStatus.MEASURED or m.value is None:
            status = "NOT_MEASURED"
            rep.warnings.append(f"target {name} NOT_MEASURED: {m.reason}")
        else:
            status = "PASS" if m.value >= spec["threshold"] else "FAIL"
            if status == "FAIL":
                rep.warnings.append(f"target {name} below threshold: {m.value:.1f} < {spec['threshold']}")
        rep.gates.append(GateResult(gate=name, kind="target", threshold=spec["threshold"], metric=m, status=status))
    for v in verdicts:
        if v.critical and v.passed is False:
            rep.release_blockers.append(f"critical judge {v.judge} failed on {v.metric.name}")
    rep.release_candidate = not rep.release_blockers
    return rep
