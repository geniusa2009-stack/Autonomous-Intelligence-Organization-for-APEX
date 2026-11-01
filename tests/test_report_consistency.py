"""Cross-check the committed reports against the machine-readable state, so no report can drift into a claim the
evidence does not support (stale counts, stale commits, unlicensed production routes, global winners, ...)."""

import json
import re
import subprocess
import sys

import pytest

from apex_one.settings import REPO_ROOT

REPORTS = sorted(REPO_ROOT.glob("*.md"))
EVIDENCE = REPO_ROOT / "docs" / "evidence"
NEGATION = re.compile(r"\b(no|never|not|without|nobody|none)\b", re.I)


def _lines(pattern: str):
    rx = re.compile(pattern, re.I)
    for p in REPORTS:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(line):
                yield p.name, i, line


def _json(name: str):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_no_global_or_overall_winner_anywhere():
    bad = [(f, i) for f, i, line in _lines(r"overall winner|best overall|overall best|global(ly)? best|best model overall")
           if not NEGATION.search(line)]
    assert not bad, bad


def test_qwen3_vl_8b_is_never_called_a_general_vision_judge():
    bad = []
    for f, i, line in _lines(r"qwen3-vl[- ]8b"):
        low = line.lower()
        if "judge" not in low or "q8" in low or "posterreward" in low or "reward weights" in low:
            continue
        if not re.search(r"640|canonical|secondary|never a general", low):
            bad.append((f, i, line[:120]))
    assert not bad, bad
    assert not [(f, i) for f, i, line in _lines(r"general vision judge") if not NEGATION.search(line)]


def test_no_production_route_rests_on_an_unverified_licence():
    pol = _json("production_routing_policy.json")
    for r in pol["rows"]:
        if r.get("decision") == "PRIMARY" and r.get("deployment") == "PRODUCTION" and r.get("candidates"):
            assert "(verified)" in r["licence_state"], r["task"]
        if "DECLARED_BUT_UNVERIFIED" in r.get("licence_state", "") or "UNKNOWN" in r.get("licence_state", ""):
            assert r["deployment"] != "PRODUCTION" or r["decision"] == "EVALUATION_ONLY", r["task"]


def test_infrastructure_errors_are_never_quality_zero():
    assert not list(_lines(r"INFRASTRUCTURE_ERROR[^|]*QUALITY_ZERO|QUALITY_ZERO[^|]*INFRASTRUCTURE_ERROR"))
    drill = _json("server_fault_drill.json")
    rows = drill.get("rows", drill) if isinstance(drill, dict) else drill
    for r in rows if isinstance(rows, list) else []:
        if r.get("failure_kind"):
            assert r.get("outcome_class") == "INFRASTRUCTURE_ERROR", r


def test_unsupported_gdb_tasks_are_never_called_failures():
    assert not [(f, i) for f, i, line in _lines(r"UNSUPPORTED[^|]*\bfail(ed|ures?)?\b")
                if not re.search(r"\b0 failures\b|PASSED / FAILED / UNSUPPORTED|never", line)]


def test_no_report_says_a_page_model_won_while_tied_or_unstable():
    assert not list(_lines(r"model wins|review for promotion|use only where it wins"))


def test_test_counts_are_one_number_and_current():
    state = json.loads((REPO_ROOT / "CURRENT_STATE.json").read_text(encoding="utf-8"))
    n = int(re.match(r"(\d+) passed", state["last_test_result"]).group(1))
    progress = re.findall(r"→ (\d+) passed", (REPO_ROOT / "PROGRESS.md").read_text(encoding="utf-8"))
    assert progress and int(progress[-1]) == n
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=REPO_ROOT, capture_output=True, text=True, timeout=300).stdout
    collected = int(re.search(r"(\d+) tests? collected", out).group(1))
    assert collected == n, f"CURRENT_STATE says {n} passed but {collected} tests exist: re-run the suite"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def test_generated_reports_come_from_one_commit_with_the_current_code():
    commits = {m for _, _, line in _lines(r"^_Generated .* at commit `")
               for m in re.findall(r"at commit `([0-9a-f]{7,40})`", line)}
    assert len(commits) == 1, f"reports generated at different commits: {commits}"
    c = commits.pop()
    assert _json("production_routing_policy.json")["frozen_at_commit"] == c
    if _git("rev-parse", "--verify", "HEAD").returncode or _git("cat-file", "-e", c).returncode:
        pytest.skip("not a git checkout with that history")
    assert _git("merge-base", "--is-ancestor", c, "HEAD").returncode == 0
    changed = _git("diff", "--name-only", c, "HEAD", "--", "apex_one", "config", "scripts").stdout.split()
    assert not changed, f"code changed after the reports were generated at {c}: {changed[:5]} — run apex-one reports"


def test_maturity_is_one_truth_and_production_ready_is_derived():
    from apex_one.lab.blockers import DIMENSIONS

    state = json.loads((REPO_ROOT / "CURRENT_STATE.json").read_text(encoding="utf-8"))["maturity"]
    machine = {d: v["status"] for d, v in _json("maturity.json")["maturity"].items()}
    assert state == machine
    unmet = [d for d, (mandatory, _) in DIMENSIONS.items() if mandatory and machine[d] != "YES"]
    assert machine["PRODUCTION_READY"] == ("NO" if unmet else "YES")
    assert f"PRODUCTION_READY is **{machine['PRODUCTION_READY']}**" in (REPO_ROOT / "PRODUCTION_BLOCKERS.md").read_text()
    ultra = (REPO_ROOT / "ULTRA_QUALITY_REPORT.md").read_text(encoding="utf-8")
    for d, st in machine.items():
        m = re.search(rf"^\| {d} \| \*\*([A-Z_ ]+?)\*\*", ultra, re.M)
        assert m and m.group(1).split()[0] == st, f"ULTRA_QUALITY_REPORT disagrees on {d}"


def test_blocker_source_is_valid_and_human_actions_are_only_human():
    from apex_one.lab.blockers import load_blockers, validate_blockers

    blockers = load_blockers()
    assert validate_blockers(blockers) == []
    human = (REPO_ROOT / "HUMAN_ACTIONS_REQUIRED.md").read_text(encoding="utf-8")
    for b in blockers:
        if not b["requires_human_action"]:
            assert b["blocker_id"] not in human, f"{b['blocker_id']} is autonomous work, not a human action"
    assert {"BRAND-ASSETS-MISSING", "APPROVER-MISSING", "GEMINI-KEY-MISSING", "REAL-OPPORTUNITY-UNVALIDATED",
            "LICENCE-VERIFICATION-PENDING", "REMOTE-PROVIDERS-EGRESS-DENIED", "NO-ROBUST-VISION-JUDGE",
            "GDB-DATASET-PARTIAL", "PRODUCTION-LOAD-UNVALIDATED"} <= {b["blocker_id"] for b in blockers}
