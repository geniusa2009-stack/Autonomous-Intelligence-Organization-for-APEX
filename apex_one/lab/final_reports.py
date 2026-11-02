"""Final evaluation reports: FINAL_MODEL_MATRIX, MODEL_SERVER_RELIABILITY, the frozen production routing policy and
the native-vs-model page comparison. Everything is read from measured artifacts; nothing is averaged across tasks,
and failed / unsupported / skipped results stay in their own states (never 0)."""

from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

# (registry model, display name, local artifact key) — the six models of the normalized comparison
COMPARED = [("gemma-multimodal", "Gemma 3 4B", "gemma3-4b-q4km"),
            ("gemma3-12b", "Gemma 3 12B", "gemma3-12b-q4km"),
            ("qwen-vl-current", "Qwen3-VL 4B", "qwen3-vl-4b-q4kxl"),
            ("qwen3-vl-8b", "Qwen3-VL 8B", "qwen3-vl-8b-q4kxl"),
            ("nemotron-nano-omni", "Nemotron 3 Nano 4B", "nemotron-3-nano-4b-q4km"),
            ("gpt-oss-20b", "gpt-oss 20B", "gpt-oss-20b-mxfp4")]
JUDGE_CANDIDATES = [("qwen3-vl-8b-q8", "Qwen3-VL 8B Q8_K_XL", "qwen3-vl-8b-q8kxl")]
# matrix column -> council task (one measured task per column; "date_reasoning" is the council `reasoning` task)
MATRIX_TASKS = [("structured_json", "structured_json"), ("english_writing", "english_factual_writing"),
                ("egyptian_arabic", "egyptian_arabic"), ("fact_preservation", "fact_preservation"),
                ("structured_editorial", "structured_editorial"), ("html_css", "html_css"),
                ("long_context", "long_context"), ("design_criticism", "design_criticism"),
                ("date_reasoning", "reasoning")]


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else None


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _stamp() -> str:
    from datetime import UTC, datetime

    return (f"_Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by `apex-one reports` at commit "
            f"`{_head()}` from measured artifacts._")


def latest_rows(runs: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Latest council row per (model, task): later runs replace earlier ones (the scores file does the same)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in runs:
        out[(r["model"], r["task"])] = r
    return out


def _task_budget(task: str) -> int | None:
    from apex_one.compute.benchmark.council import tasks

    return next((t.max_tokens for t in tasks(None) if t.name == task), None)


def _cell(mid: str, task: str, scores: dict[str, Any], rows: dict[tuple[str, str], dict[str, Any]]) -> str:
    v = (scores.get(mid) or {}).get(task)
    r = rows.get((mid, task))
    if v is not None:
        budget = r.get("max_tokens") if r else None    # flag only a budget OTHER than the task's contract budget
        return (f"{v:.0f}" + (" QUALITY_ZERO" if v == 0 else "")
                + (f" (re-run budget {budget})" if budget and budget != _task_budget(task) else ""))
    if r is None:
        return "NOT_MEASURED"
    if r.get("failure_kind"):
        return f"INFRASTRUCTURE_ERROR {r['failure_kind']}"
    if "empty output" in (r.get("detail") or ""):
        return "INFRASTRUCTURE_ERROR EMPTY_OUTPUT"
    return "NOT_MEASURED"


def vision_cell(mid: str, calib: dict[str, Any] | None, vision: bool = True) -> str:
    from apex_one.lab.benchmarks.vision_robustness import load, status

    if not vision:
        return "UNSUPPORTED (text-only artifact)"
    calib = calib or {}
    parts = []
    for section, label in (("models", "abs"), ("pairwise_models", "pair")):
        r = calib.get(section, {}).get(mid)
        if r and r.get("checks"):
            parts.append(f"{label} {sum(bool(v) for v in r['checks'].values())}/{len(r['checks'])}")
        else:
            parts.append(f"{label} NOT_RUN")
    pr = calib.get("pairwise_models", {}).get(mid)
    data = load(mid)
    if data:
        st = status(data)[0]
    elif pr and pr.get("checks"):
        st = "UNQUALIFIED" if sum(bool(v) for v in pr["checks"].values()) < 4 else "INCOMPLETE"
    else:
        st = "NOT_RUN"
    return f"{', '.join(parts)} → **{st}**"


def gdb_cell(key: str, gdb_dir: Path, states: dict[str, dict[str, Any]]) -> str:
    rep = _load(gdb_dir / f"{key}-full" / "report.json")
    if rep is None:
        return "NOT_RUN"
    res = rep.get("results", {})
    failed = sum(r.get("failure_count", 0) for pm in res.values() for r in pm.values())
    unsup = sum(1 for s in states.values() if s["state"] == "UNSUPPORTED")
    skipped = sum(1 for s in states.values() if s["state"] == "SKIPPED")
    return (f"{len(res)} measured (n=2 each){f', {failed} ERROR samples' if failed else ''}; "
            f"{unsup} UNSUPPORTED; {skipped} SKIPPED")


def ram_cell(key: str, qstate: dict[str, Any]) -> str:
    r = ((qstate.get("done") or {}).get(f"{key}:ram") or {}).get("info")
    if not r:
        return "NOT_MEASURED"
    loaded = f"{r['loaded_rss_gb']:.1f} loaded / " if r.get("loaded_rss_gb") else ""
    return f"{loaded}{r['peak_rss_gb']:.1f} peak GB"


def licence_cell(reg, mid: str) -> str:
    if mid not in reg.models:
        return "—"
    lic = reg.license_for(reg.models[mid])
    return lic.production_state.value + ("" if lic.production_state.value != "PRODUCTION_ALLOWED" else " (verified)")


def final_model_matrix_md(bench: Path, reg, specs: dict[str, Any]) -> str:
    from apex_one.lab.reports import gdb_task_states
    from apex_one.vision.council import model_digest

    runs_p = bench / "council_runs.jsonl"
    runs = [json.loads(x) for x in runs_p.read_text(encoding="utf-8").splitlines() if x.strip()] if runs_p.exists() else []
    rows = latest_rows(runs)
    scores = (_load(bench / "council_scores.json") or {}).get("models", {})
    calib = _load(bench / "vision_calibration" / "calibration_results.json")
    qstate = _load(bench / "queue_state.json") or {}
    gdb_runs = {}
    for k in (bench / "gdb").glob("*-full/report.json") if (bench / "gdb").exists() else []:
        gdb_runs[k.parent.name] = ((_load(k) or {}).get("results", {}), None)
    states = gdb_task_states(gdb_runs)
    common = [t for _, t in MATRIX_TASKS if all((scores.get(m) or {}).get(t) is not None for m, _, _ in COMPARED)]
    out = ["# Final model matrix", "", _stamp(), "",
           "One normalized table for the six local models. Every cell is ONE measured task under the same contract "
           "(same prompt, checker version, temperature 0, 500-token budget unless a cell says otherwise). "
           "**There is no overall score and no overall winner**: the models were not all measured on the same task "
           "set, and an average would hide a 0 behind unrelated 100s. Cells that did not measure say why "
           "(NOT_MEASURED / ERROR <kind>); none is ever counted as 0. GraphicDesignBench ran 2 samples per task — "
           "enough to show a model runs end to end, never enough to rank models.", "",
           f"**Identical measured-task set across all six models:** {', '.join(common) or 'none'} — the only tasks on "
           "which a side-by-side reading is fair.", "",
           "| model | " + " | ".join(c for c, _ in MATRIX_TASKS) +
           " | vision_calibration | gdb_tasks_supported | median_latency | ram | production_license_state |",
           "|---|" + "---|" * (len(MATRIX_TASKS) + 5)]
    for mid, name, key in COMPARED:
        cells = [_cell(mid, t, scores, rows) for _, t in MATRIX_TASKS]
        lats = [rows[(mid, t)]["latency_s"] for t in common if (mid, t) in rows]
        med = f"{statistics.median(lats):.0f} s (common set)" if lats else "NOT_MEASURED"
        out.append(f"| {name} | " + " | ".join(cells) + f" | {vision_cell(mid, calib, getattr(specs.get(key), 'vision', True))} | "
                   f"{gdb_cell(key, bench / 'gdb', states)} | {med} | {ram_cell(key, qstate)} | "
                   f"{licence_cell(reg, mid)} |")
    out += ["", "Scores are 0–100 per deterministic checker (checker version "
            f"{(_load(bench / 'council_scores.json') or {}).get('checker_version', '?')}). `abs` = absolute "
            "calibration, `pair` = order-swapped pairwise calibration (≥ 4/5 needed for either), the bold state is "
            "the resolution-robustness status (VISION_JUDGE_ROBUSTNESS.md). Median latency is over the identical "
            "task set only, so it is comparable. RAM = llama-server resident memory (`/proc`), recorded from "
            "2026-10-30; earlier runs did not record it.", ""]
    # per-model provenance
    out += ["## Provenance per model", "",
            "| model | artifact (quantization) | model fingerprint (GGUF sha256) | council token budget | outputs "
            "complete | failures by kind | evaluation commits |", "|---|---|---|---|---|---|---|"]
    for mid, name, key in COMPARED + JUDGE_CANDIDATES:
        spec = specs.get(key)
        mine = [r for (m, _), r in rows.items() if m == mid]
        done = sum(1 for r in mine if r.get("score") is not None)
        kinds = Counter(r.get("failure_kind") or ("EMPTY_OUTPUT" if "empty output" in (r.get("detail") or "") else None)
                        for r in mine if r.get("score") is None)
        kinds.pop(None, None)
        budgets = sorted({r.get("max_tokens") for r in mine if r.get("max_tokens")})
        commits = sorted({v.get("commit") for k, v in (qstate.get("done") or {}).items()
                          if k.startswith(f"{key}:") and v.get("commit")})
        out.append(f"| {name} | {spec.tag if spec else '—'} | `{(model_digest(mid) or 'weights not on disk')[:19]}` | "
                   f"{', '.join(map(str, budgets)) or '—'} | {done}/{len(mine)} tasks scored | "
                   f"{', '.join(f'{k}×{n}' for k, n in kinds.items()) or 'none'} | {', '.join(commits) or 'before commit tracking'} |")
    out += [""] + cycles_md(qstate)
    out += ["", "## Gemma 3 12B — full results", ""]
    out += model_detail(bench, "gemma3-12b", "gemma3-12b-q4km", rows, scores, calib, qstate, reg)
    for mid, name, key in JUDGE_CANDIDATES:
        out += ["", f"## {name} — stronger-judge candidate", ""]
        out += model_detail(bench, mid, key, rows, scores, calib, qstate, reg)
    return "\n".join(out) + "\n"


def model_detail(bench: Path, mid: str, key: str, rows, scores, calib, qstate, reg) -> list[str]:
    from apex_one.lab.benchmarks.vision_robustness import load, status, summarize_width

    done = qstate.get("done") or {}
    failed = qstate.get("failed") or {}
    step = lambda s: (done.get(f"{key}:{s}") or {}).get("info")  # noqa: E731
    out = ["| item | result |", "|---|---|"]
    live = step("live")
    out.append("| live structured-output test | " + (f"{live.get('status')}, structured answer correct={live.get('correct')}"
                                                       if live else str(failed.get(f"{key}:live") or "NOT_RUN")) + " |")
    a = (calib or {}).get("models", {}).get(mid)
    out.append("| absolute vision calibration | " + (
        f"{sum(bool(v) for v in a['checks'].values())}/5 (ties on target {step('calib').get('ties_on_target') if step('calib') else '?'}, "
        f"inversions {step('calib').get('inversions_on_target') if step('calib') else '?'}) → "
        f"{'passes 4/5' if sum(bool(v) for v in a['checks'].values()) >= 4 else 'FAILS the 4/5 bar'}" if a and a.get("checks")
        else "NOT_RUN") + " |")
    p = (calib or {}).get("pairwise_models", {}).get(mid)
    out.append("| pairwise calibration (both orders) | " + (
        f"{p.get('correct')}/5; cases {', '.join(f'{k}={v}' for k, v in p['checks'].items())}" if p and p.get("checks")
        else "NOT_RUN") + " |")
    data = load(mid)
    if data:
        st, why = status(data)
        for w, v in data.get("widths", {}).items():
            s = summarize_width(v)
            out.append(f"| robustness {w} px (pair-order + {s.get('repeats')} repeats) | correct per repeat "
                       f"{s.get('correct_per_repeat')}, order sensitivity {s.get('order_sensitivity')}, run variance "
                       f"{s.get('run_variance')}, legible {s.get('legible')} |")
        out.append(f"| **vision judge status** | **{st}** ({why}) |")
    else:
        notrun = [k for k, v in done.items() if k.startswith(f"{key}:robust:") and (v.get("info") or {}).get("not_run")]
        out.append(f"| **vision judge status** | **{'UNQUALIFIED' if p and (p.get('correct') or 0) < 4 else 'NOT_RUN'}** "
                   f"{'(pairwise calibration below 4/5)' if p and (p.get('correct') or 0) < 4 else ''}"
                   f"{'; sweep not run: ' + str(len(notrun)) + ' widths' if notrun else ''} |")
    inv = step("invest")
    if inv:
        out.append(f"| calibration investigation | {inv} |")
    for col, t in MATRIX_TASKS + [("visual_hierarchy (1 pair)", "visual_hierarchy"), ("en_ar_mixing", "en_ar_mixing")]:
        if (mid, t) in rows or (scores.get(mid) or {}).get(t) is not None:
            r = rows.get((mid, t), {})
            out.append(f"| {col} | {_cell(mid, t, scores, rows)} — {r.get('state', '')} {r.get('latency_s', '')} s; "
                       f"{(r.get('detail') or '')[:90]} |")
    g = _load(bench / "gdb" / f"{key}-full" / "report.json")
    if g:
        for tid, pm in g.get("results", {}).items():
            for _, r in pm.items():
                sc = {k: v for k, v in (r.get("scores") or r).items() if isinstance(v, (int, float))
                      and k not in ("failure_count", "n", "count")}
                out.append(f"| GDB {tid} | {', '.join(f'{k}={v:.2f}' for k, v in list(sc.items())[:3]) or '—'}"
                           f"{'; ' + str(r.get('failure_count')) + ' ERROR samples (not scored)' if r.get('failure_count') else ''} |")
    elif f"{key}:gdb" in failed:
        out.append(f"| GraphicDesignBench | ERROR — {failed[f'{key}:gdb'].get('info')} |")
    pages = step("pages")
    if pages:
        out.append(f"| model-written pages (5 types) | produced {pages.get('produced')}/{pages.get('pages')}, critical "
                   f"pages {pages.get('critical_pages')}, contract violations {pages.get('contract_violations')}, "
                   f"median latency {pages.get('median_latency_s')} s |")
    out.append(f"| RAM | {ram_cell(key, qstate)} |")
    out.append(f"| licence | {licence_cell(reg, mid)} — evaluation use only unless PRODUCTION_ALLOWED |")
    errs = [f"{k.split(':', 1)[1]}: {str(v.get('info'))[:80]}" for k, v in failed.items() if k.startswith(f"{key}:")]
    if errs:
        out.append(f"| failed steps | {'; '.join(errs)} |")
    return out


# ---------------------------------------------------------------- MODEL_SERVER_RELIABILITY

def reliability_md(bench: Path) -> str:
    from apex_one.compute.local.supervisor import RESTART_ON, RETRY_AFTER_RECOVERY, FailureKind, SupervisorPolicy

    drill = _load(bench / "server_reliability" / "fault_drill.json")
    pol = SupervisorPolicy()
    out = ["# Model server reliability", "", _stamp(), "",
           "A local model server can crash, hang, run out of memory, return nothing or return garbage. None of these "
           "is a wrong answer. `apex_one/compute/local/supervisor.py` classifies every failed call into exactly one "
           "failure kind, recovers the server when that is safe, and the benchmark records the sample as **ERROR** "
           "(never a score). Result states are kept separate: PASSED · FAILED (measured) · UNSUPPORTED · SKIPPED · "
           "ERROR.", "",
           "## Why this exists", "",
           "On 2026-10-30 the Qwen3-VL 8B llama-server died in the middle of a GraphicDesignBench run. The harness "
           "of that time turned the resulting empty answers into 0 scores (12/12 samples \"ok\"). That run is "
           "quarantined (`artifacts/bench/gdb/_invalid_qwen3-vl-8b-q4kxl-full_20261030`), the valid re-run replaced "
           "it, and the supervision below makes the same failure an ERROR with a kind.", "",
           "## Supervision policy", "",
           f"* pre-call health probe (`/health`, {pol.health_timeout_s:.0f} s) before every model call",
           "* timeout detection: the call timeout raises MODEL_TIMEOUT; a hung server is restarted (it holds the only slot)",
           f"* restart: at most {pol.max_restarts} per server per run, backoff {', '.join(f'{b:.0f} s' for b in pol.backoff_s)}; "
           "each restart must pass `/health` AND a 1-token warm-up completion",
           f"* restart on: {', '.join(sorted(k.value for k in RESTART_ON))}",
           f"* the SAME request is retried once, only after a verified recovery, only for: "
           f"{', '.join(sorted(k.value for k in RETRY_AFTER_RECOVERY))} — a chat completion is side-effect free; "
           "pipeline stages and jobs are never re-run by the supervisor, so no side effect can be duplicated",
           "* EMPTY_OUTPUT and MALFORMED_OUTPUT are never retried (at temperature 0 they would only repeat); "
           "RESOURCE_BLOCKED is never retried (waiting does not create RAM)",
           "* every incident is a JSON line: `artifacts/bench/server_reliability/events.jsonl` (benchmarks), "
           "`artifacts/logs/model_server_events.jsonl` (production)",
           "* production brokers supervise only servers that are already running; supervision recovers a crash, "
           "it never starts a model nobody asked for", "",
           "## Failure kinds (infrastructure — never a quality score)", "",
           "| kind | detected from |", "|---|---|",
           f"| {FailureKind.MODEL_SERVER_CRASH} | process no longer alive after the failed call (any transport symptom) |",
           f"| {FailureKind.OOM} | process dead by SIGKILL, or an allocator failure in the server log |",
           f"| {FailureKind.MODEL_TIMEOUT} | no response within the call timeout, process alive |",
           f"| {FailureKind.EMPTY_OUTPUT} | HTTP 200, valid shape, empty / whitespace content |",
           f"| {FailureKind.MALFORMED_OUTPUT} | the response body is not an OpenAI chat response (a well-formed answer "
           "with wrong content is QUALITY, scored by the checker) |",
           f"| {FailureKind.CONNECTION_REFUSED} | nothing listening on the port and restarts did not bring it up |",
           f"| {FailureKind.STREAM_INTERRUPTED} | connection closed mid-response, process alive |",
           f"| {FailureKind.HEALTHCHECK_FAILED} | process running but `/health` not OK and the restart budget is spent |",
           f"| {FailureKind.RESOURCE_BLOCKED} | the resource scheduler refused the load (expected peak + reserves > available) |",
           f"| {FailureKind.UNKNOWN_FAILURE} | anything else (e.g. HTTP 500) |", "",
           "## Outcome classes (persisted separately on every council sample, never collapsed)", "",
           "| class | meaning | example |", "|---|---|---|",
           "| MEASURED | the model answered; the checker scored it > 0 | Qwen3-VL 8B English writing = 100 |",
           "| QUALITY_ZERO | the model answered; the answer is wrong (score 0) | Qwen3-VL 8B Egyptian Arabic = 0 |",
           "| INFRASTRUCTURE_ERROR | a failure kind above: there was no answer to judge | server crash mid-GDB |",
           "| NOT_MEASURED | unsupported, skipped or never run | GDB image-generation tasks |", "",
           "## Resource scheduler", "",
           "Before a model loads: expected peak (measured, else weights + KV + compute) + reserves must fit in "
           "MemAvailable, or the load is refused with RESOURCE_BLOCKED. While loaded, each stage is admitted again "
           "(a stage that starts Chromium needs 0.8 GB more). After every model: stop the server, confirm the "
           "process exited, wait until MemAvailable is stable, assert no llama-server still holds ≥ 1 GB (a model "
           "marked finished while its server holds memory is a scheduler bug and stops the queue), and only then "
           "load the next model. The scheduler never kills a process it did not start. Full matrix: "
           "LOCAL_MODEL_RESOURCE_MATRIX.md.", "",
           "## Fault-injection drill (fake model server, real broker + council path)", ""]
    if drill:
        out += [f"Result: **{'ALL PASS' if drill['all_pass'] else 'FAILURES'}** — "
                f"{sum(r['pass'] for r in drill['rows'])}/{len(drill['rows'])} modes classified as expected.", "",
                "| fake server mode | sample state | failure kind | in score table | restarts | supervisor events | expected | pass |",
                "|---|---|---|---|---|---|---|---|"]
        for r in drill["rows"]:
            e = r["expected"]
            out.append(f"| {r['mode']} | {r['state']} | {r['failure_kind'] or '—'} | {'yes' if r['in_score_table'] else 'no'} | "
                       f"{r['restarts']} | {', '.join(r['events']) or '—'} | {e['state']}/{e['failure_kind'] or '—'} | "
                       f"{'PASS' if r['pass'] else 'FAIL'} |")
        out += ["", "Every row also carries its outcome class: persistent faults are INFRASTRUCTURE_ERROR. "
                "`ok` and the `*_once` modes are real measurements of the fake server's fixed answer (the checker "
                "scores it FAILED because the fake answer is not the task's answer) — the point is that they were "
                "MEASURED after recovery, while every persistent fault is ERROR and never enters the score table.", ""]
    else:
        out += ["NOT_RUN — `python -c 'from apex_one.lab.benchmarks.server_fault_drill import run_drill; ...'`", ""]
    ev_p = bench / "server_reliability" / "events.jsonl"
    events = [json.loads(x) for x in ev_p.read_text(encoding="utf-8").splitlines() if x.strip()] if ev_p.exists() else []
    out += ["## Incidents in real benchmark runs (since supervision)", ""]
    if events:
        c = Counter((e["server"], e["event"] + (f":{e['kind']}" if e.get("kind") else "")) for e in events)
        out += ["| server | event | count |", "|---|---|---|"] + [f"| {s} | {ev} | {n} |" for (s, ev), n in sorted(c.items())]
    else:
        out.append("No supervisor event (restart, crash, timeout, empty output) was recorded in a real run.")
    incidents = _load(bench / "server_reliability" / "queue_incidents.json") or []
    if incidents:
        out += ["", "**Queue / scheduler incidents** (before a server was under supervision):", "",
                "| at | server | what happened | outcome | fix | regression tests |", "|---|---|---|---|---|---|"]
        out += [f"| {i['at']} | {i['server']} | {i['what']} | {i['outcome']} | {i['fix']} | `{i['regression_tests']}` |"
                for i in incidents]
    qstate = _load(bench / "queue_state.json") or {}
    out += [""] + load_test_md(_load(bench / "load_test" / "report.json"))
    out += [""] + cycles_md(qstate)
    tests = "tests/test_server_reliability.py"
    out += ["", f"Regression tests: `{tests}` (classification, bounded restart with backoff, the full drill, GDB "
            "failures carry their kind).", ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- frozen production routing policy

ROUTE_ABSTAIN = {
    True: "primary unavailable or its output fails validation → fallback model; both fail → APEX native engine "
          "(deterministic); never a silent empty section",
    False: "primary unavailable or its output fails validation → fallback model; both fail → the stage pauses "
           "AWAITING_HUMAN (no native engine for this task); never a guessed answer",
}


def _contract(row: dict[str, Any] | None) -> tuple[Any, Any] | None:
    """(token budget, checker version) a council row was measured under; None = not recorded (pre-contract run)."""
    if not row or row.get("max_tokens") is None or row.get("checker_version") is None:
        return None
    return row["max_tokens"], row["checker_version"]


def route_candidates(reg, task: str, rows: dict[tuple[str, str], dict[str, Any]], qstate: dict[str, Any],
                     specs: dict[str, Any], installed: set[str]) -> list[dict[str, Any]]:
    """Every measured, installed model that passes the task's floor on EVERY mandatory capability, with the exact
    measurements behind it (score, contract, latency), its RAM, licence, reliability and production admission."""
    from apex_one.compute.local.resources import PRODUCTION_MODE, admit, baseline_capacity_gb, measured_peak
    from apex_one.compute.router.capability import rejection, required_scores, routing_config, task_evidence_score

    caps = routing_config().get("capabilities", {})
    by_model = {s.registry_model: s for s in specs.values()}
    out = []
    for m in reg.models.values():
        if not m.benchmark_scores or m.id not in installed or not reg.research_allowed(m):
            continue
        sc = task_evidence_score(m, task)
        if sc is None or rejection(m, task):
            continue
        ev = {}
        for cap in required_scores(m, task):
            t = caps.get(cap, cap)
            r = rows.get((m.id, t))
            ev[t] = {"score": None if r is None else r.get("score"), "contract": _contract(r),
                     "latency_s": None if r is None else r.get("latency_s")}
        spec = by_model.get(m.id)
        ram = (((qstate.get("done") or {}).get(f"{spec.key}:ram") or {}).get("info") or {}) if spec else {}
        mrows = [r for (mid, _), r in rows.items() if mid == m.id]
        infra = sum(1 for r in mrows if r.get("outcome_class") == "INFRASTRUCTURE_ERROR")
        cycles = ram.get("cycles") or []
        prod = admit(spec, "live", qstate, mode=PRODUCTION_MODE, available=baseline_capacity_gb(), others=[]) \
            if spec else None
        lats = [e["latency_s"] for e in ev.values() if e["latency_s"] is not None]
        out.append({"model": m.id, "score": sc, "evidence": ev, "licensed": reg.production_allowed(m),
                    "licence_state": _licence_state(reg, m), "peak_gb": measured_peak(spec, qstate) if spec else None,
                    "latency_s": round(sum(lats) / len(lats), 1) if lats else None,
                    "reliability": f"{infra} infrastructure errors in {len(mrows)} council samples; "
                                   f"{sum(1 for c in cycles if not c.get('flags'))}/{len(cycles)} scheduled cycles clean",
                    "production_admission": prod.decision if prod else "NOT_MEASURED"})
    return out


def _licence_state(reg, m) -> str:
    st = reg.license_for(m).production_state.value
    return st + " (verified)" if reg.production_allowed(m) else st


def comparable(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two candidates may be ranked against each other only on identical measurements: the same council tasks, each
    measured under the same recorded contract (token budget + checker version)."""
    if set(a["evidence"]) != set(b["evidence"]):
        return False
    return all(a["evidence"][t]["contract"] is not None and a["evidence"][t]["contract"] == b["evidence"][t]["contract"]
               for t in a["evidence"])


def rank_route(cands: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Higher measured score first; an exact tie goes to the cheaper model (lower measured peak RAM, then lower
    latency); a model the machine would not admit in PRODUCTION_MODE never ranks above one it would."""
    def key(c):
        return (c["production_admission"] != "ADMIT", -c["score"], c["peak_gb"] or 99.0, c["latency_s"] or 9e9,
                c["model"])
    ranked = sorted(cands, key=key)
    if len(ranked) < 2:
        return ranked, "single qualified candidate"
    a, b = ranked[0], ranked[1]
    if not comparable(a, b):
        return ranked, (f"{a['model']} vs {b['model']}: NOT on identical measurements (contract differs or not "
                        "recorded) — order is provisional")
    if a["score"] == b["score"]:
        return ranked, f"tie at {a['score']:.0f} on identical measurements → the cheaper model ({a['model']})"
    return ranked, f"{a['model']} measured higher ({a['score']:.0f} vs {b['score']:.0f}) on identical measurements"


def production_policy(reg, runs: list[dict[str, Any]], bench: Path) -> dict[str, Any]:
    """PRIMARY / FALLBACK / NO_QUALIFIED_MODEL / DETERMINISTIC_ENGINE / HUMAN_REQUIRED / EVALUATION_ONLY per task,
    from evidence. Every row records: task, primary, fallback, minimum requirement, measured evidence, licence state,
    reason and abstention behaviour."""
    from apex_one.compute.local import load_catalogue
    from apex_one.compute.router.capability import routing_config
    from apex_one.compute.router.fallback import has_native_fallback
    from apex_one.lab.benchmarks.page_compare import verdicts
    from apex_one.vision.council import judge_status, reliable_judges

    cfg = routing_config()
    floor = cfg.get("default_min_score", 50)
    _, specs = load_catalogue()
    installed = {s.registry_model for s in specs.values() if (s.dir / "apex_manifest.json").exists()}
    rows_by = latest_rows(runs)
    qstate = _load(bench / "queue_state.json") or {}
    rows: list[dict[str, Any]] = []

    def add(task: str, decision: str, primary: str | None = None, fallback: str | None = None, why: str = "", *,
            minimum: str = "—", evidence: str = "—", licence: str = "n/a", abstain: str = "—",
            deployment: str = "n/a", comparison: list[dict[str, Any]] | None = None) -> None:
        rows.append({"task": task, "decision": decision, "primary": primary, "fallback": fallback, "why": why,
                     "minimum_requirement": minimum, "measured_evidence": evidence, "licence_state": licence,
                     "abstention": abstain, "deployment": deployment, "candidates": comparison or []})

    add("critical date arithmetic (date.*)", "DETERMINISTIC_ENGINE", "apex_one.core.dates", None,
        "permanently outside model reasoning; the $0 firewall refuses date.* for every model",
        minimum="exact calendar arithmetic", evidence="tests/test_dates.py; every model's date task is irrelevant here",
        abstain="no model fallback exists by design", deployment="PRODUCTION")
    add("critical locked facts (deadline, eligibility, funding)", "DETERMINISTIC_ENGINE", "evidence system + fact locks",
        "HUMAN_REQUIRED for single-source critical claims", "models may phrase a locked fact, never change it",
        minimum="≥ 2 independent sources or human confirmation", evidence="Fact Lock + deterministic QA",
        abstain="unlockable fact → AWAITING_HUMAN", deployment="PRODUCTION")
    for task, rule in cfg.get("tasks", {}).items():
        if "requires" not in rule:
            continue
        minimum = f"≥ {rule.get('min_score', floor)} on each of {', '.join(rule['requires'])}"
        native = has_native_fallback(task)
        cands = route_candidates(reg, task, rows_by, qstate, specs, installed)
        lic, why = rank_route([c for c in cands if c["licensed"]])
        unlic, uwhy = rank_route([c for c in cands if not c["licensed"]])
        ranked = lic + unlic

        def ev(c):
            return "; ".join(f"{c['model']} {t}={e['score']:.0f}" + (f" @{e['contract'][0]} tok/checker v{e['contract'][1]}"
                                                                    if e["contract"] else " (contract not recorded)")
                             for t, e in c["evidence"].items() if e["score"] is not None)
        if lic:
            p, f = lic[0], lic[1] if len(lic) > 1 else None
            add(task, "PRIMARY", f"{p['model']} ({p['score']:.0f})", f"{f['model']} ({f['score']:.0f})" if f else
                ("APEX native engine" if native else None), why, minimum=minimum,
                evidence=" | ".join(ev(c) for c in lic[:2]),
                licence=" / ".join(f"{c['model']}: {c['licence_state']}" for c in lic[:2]),
                abstain=ROUTE_ABSTAIN[native], deployment="PRODUCTION", comparison=ranked)
            if unlic and unlic[0]["score"] > p["score"]:
                rows[-1]["why"] += (f"; evaluation-only {unlic[0]['model']} measured higher ({unlic[0]['score']:.0f}) "
                                    f"but is {unlic[0]['licence_state']} — not deployable")
        elif unlic:
            p = unlic[0]
            add(task, "EVALUATION_ONLY", f"{p['model']} ({p['score']:.0f})",
                "APEX native engine" if native else None,
                f"{p['model']} passes the floor but its licence is {p['licence_state']}: NOT deployable ({uwhy}). "
                "In production " + ("the APEX native engine runs this task." if native else "no model runs this task."),
                minimum=minimum, evidence=ev(p), licence=f"{p['model']}: {p['licence_state']}",
                abstain=ROUTE_ABSTAIN[native], deployment="EVALUATION_ONLY", comparison=ranked)
        else:
            add(task, "NO_QUALIFIED_MODEL", "APEX native engine" if native else None, None,
                f"no installed model passes {', '.join(rule['requires'])} at the floor", minimum=minimum,
                abstain=ROUTE_ABSTAIN[native], deployment="PRODUCTION" if native else "n/a")
    pw = reliable_judges(mode="pairwise")[0]
    add("visual finalist comparison (A/B)", "PRIMARY" if pw else "NO_QUALIFIED_MODEL",
        f"{pw[0]} as SECONDARY_FINALIST_PAIRWISE_JUDGE ({judge_status(pw[0])[0]})" if pw else None,
        "deterministic tournament order",
        "advisory only; canonical 640 px A4 renders of QA-passed finalists; never facts, dates, Arabic quality",
        minimum="pairwise ≥ 4/5, position bias ≤ 0.2, legible, stable repeats — at the canonical width",
        evidence="VISION_JUDGE_ROBUSTNESS.md", licence="Apache-2.0 (PRODUCTION_ALLOWED)" if pw else "n/a",
        abstain="judge unavailable or disagrees with itself across orders → deterministic tournament order",
        deployment="PRODUCTION (advisory)" if pw else "n/a")
    ab = reliable_judges()[0]
    add("visual quality scores (absolute council)", "PRIMARY" if ab else "NO_QUALIFIED_MODEL", ab[0] if ab else None,
        None, "needs absolute calibration ≥ 4/5 AND ROBUSTLY_CALIBRATED; otherwise Vision Quality = NOT_MEASURED",
        minimum="absolute ≥ 4/5 + ROBUSTLY_CALIBRATED", evidence="VISION_JUDGE_ROBUSTNESS.md",
        abstain="Vision Quality = NOT_MEASURED (never a guessed score)", deployment="PRODUCTION" if ab else "n/a")
    add("SVG / vector assets", "NO_QUALIFIED_MODEL", "native SVG assets", None,
        "specialist vector models (StarVector / OmniSVG) not activated: weights host egress-denied",
        minimum="GDB svg tasks at n ≥ 20", abstain="native SVG assets", deployment="PRODUCTION")
    add("document layout", "DETERMINISTIC_ENGINE", "APEX native layout engine + tournament", None,
        "specialist layout models not activated", minimum="—", evidence="golden ULTRA (deterministic)",
        abstain="—", deployment="PRODUCTION")
    cmp_ = _load(bench / "apex_design" / "page_compare.json")
    v = verdicts(cmp_) if cmp_ else {}
    winners = [s for s, d in v.items() if not d["safety_losses"] and d["wins"]]
    add("page design (HTML writing)", "DETERMINISTIC_ENGINE", "APEX native engine",
        None, "no model page beat native without a safety loss" if not winners else
        f"model ahead without a safety loss: {winners} — not a win and not promoted: run-to-run stability "
        "NOT_MEASURED",
        minimum="win without a safety loss AND measured stability", evidence="APEX_DESIGN_BENCH.md",
        abstain="—", deployment="PRODUCTION")
    add("release approval", "HUMAN_REQUIRED", "authenticated approver (token)", None, "hash-chained approval ledger",
        minimum="token-authenticated approver bound to job id + artifact hash", abstain="job stays RELEASE_CANDIDATE",
        deployment="PRODUCTION")
    add("brand assets", "HUMAN_REQUIRED", "apex-one brand import", None, "original APEX package; placeholders fail",
        minimum="`apex-one brand validate` = VALID", abstain="Brand Production Gate FAIL", deployment="PRODUCTION")
    evidence = {p.name: _sha(p) for p in (bench / "council_scores.json",
                                          bench / "vision_calibration" / "calibration_results.json",
                                          bench / "apex_design" / "page_compare.json")}
    for p in sorted((bench / "vision_robustness").glob("*.json")) if (bench / "vision_robustness").exists() else []:
        evidence[f"vision_robustness/{p.name}"] = _sha(p)
    return {"frozen_at_commit": _head(), "evidence_sha256_12": evidence, "rows": rows,
            "rule": "no global best model; per-task evidence on identical measurements; ties go to the cheaper "
                    "model; licence + installation + production admission required for deployment"}


def policy_md(policy: dict[str, Any]) -> list[str]:
    out = ["## Frozen production routing policy", "",
           f"Frozen at commit `{policy['frozen_at_commit']}` against evidence "
           + ", ".join(f"`{k}`={v}" for k, v in policy["evidence_sha256_12"].items())
           + " (`docs/evidence/production_routing_policy.json`). Any change to that evidence requires regenerating "
           "and re-reviewing this table. A model is never routed to merely because it is installed. There is no "
           "global best model: every route is decided on that task's mandatory capabilities only. "
           "**EVALUATION_ONLY** = the best measured model is not production-licensed; production runs the native engine "
           "(or nothing) instead.", "",
           "| task | decision | primary | fallback | minimum requirement | licence state | deployment | reason |",
           "|---|---|---|---|---|---|---|---|"]
    for r in policy["rows"]:
        out.append(f"| {r['task']} | **{r['decision']}** | {r['primary'] or '—'} | {r['fallback'] or '—'} | "
                   f"{r.get('minimum_requirement', '—')} | {r.get('licence_state', 'n/a')} | "
                   f"{r.get('deployment', 'n/a')} | {r['why']} |")
    out += ["", "### Measured evidence and abstention per route", "",
            "| task | measured evidence (task=score @ token budget / checker) | abstention behaviour |", "|---|---|---|"]
    out += [f"| {r['task']} | {r.get('measured_evidence', '—')} | {r.get('abstention', '—')} |" for r in policy["rows"]]
    out += ["", *qwen_4b_vs_8b_md(policy)]
    return out + [""]


def qwen_4b_vs_8b_md(policy: dict[str, Any], a: str = "qwen-vl-current", b: str = "qwen3-vl-8b") -> list[str]:
    """Every route where both Qwen3-VL builds qualify: identical-measurement comparison and the decision."""
    out = ["### Qwen3-VL 4B vs Qwen3-VL 8B, per route (identical measurements only)", "",
           "Rule: a higher measured score wins; an exact tie goes to the cheaper model (lower measured peak RAM, then "
           "latency); a model the machine would not admit in PRODUCTION_MODE never ranks above one it would; scores "
           "measured under different or unrecorded contracts are NOT compared (order provisional).", "",
           "| task | 4B score | 8B score | identical measurements | 4B latency | 8B latency | 4B peak RAM | 8B peak RAM | "
           "4B licence | 8B licence | 4B reliability | 8B reliability | production admission 4B / 8B | decision |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    n = 0
    for r in policy["rows"]:
        c = {x["model"]: x for x in r.get("candidates", [])}
        if a not in c or b not in c:
            continue
        n += 1
        x, y = c[a], c[b]
        same = comparable(x, y)
        prim = (r["primary"] or "").split(" ")[0]
        dec = (f"{'4B' if prim == a else '8B' if prim == b else prim} primary"
               + ("" if same else " (PROVISIONAL: not identical measurements)"))
        out.append(f"| {r['task']} | {x['score']:.0f} | {y['score']:.0f} | {'yes' if same else 'NO'} | "
                   f"{x['latency_s']} s | {y['latency_s']} s | {x['peak_gb']} GB | {y['peak_gb']} GB | "
                   f"{x['licence_state']} | {y['licence_state']} | {x['reliability']} | {y['reliability']} | "
                   f"{x['production_admission']} / {y['production_admission']} | {dec} |")
    if not n:
        out.append("| — | no route where both qualify |" + " |" * 12)
    return out + [""]


# ---------------------------------------------------------------- native vs model pages

DIMENSIONS = [("reader comprehension", "reader_comprehension", False), ("geometry: overflow issues", "overflow_issues", True),
              ("RTL", "rtl", False), ("brand fit (APEX similarity)", "apex_similarity", False),
              ("editability", "editability", False), ("fact preservation", "fact_preservation", False),
              ("text fidelity", "text_fidelity", False)]


def native_vs_model_md(cmp_: dict[str, Any] | None, golden_deterministic: Path | None = None) -> list[str]:
    out = ["## Native APEX engine vs best model candidate, per page type", ""]
    if not cmp_:
        return out + ["NOT_MEASURED — run `page_compare.remeasure`.", ""]
    by: dict[str, dict[str, dict[str, Any]]] = {}
    for r in cmp_["rows"]:
        by.setdefault(r["page_type"], {})[r["system"]] = r
    out += ["Best candidate = the model page with the fewest losses to native on these dimensions (ties: more wins). "
            "Stability: the native engine is deterministic (same inputs → byte-identical pages, "
            "`docs/evidence/golden_ultra_deterministic.json`); a model page is ONE sample, so its run-to-run stability "
            "is NOT_MEASURED and counts against promotion. Native stays primary unless the model wins without a loss.", "",
            "| page type | best model | " + " | ".join(d for d, _, _ in DIMENSIONS) + " | stability | decision |",
            "|---|---|" + "---|" * (len(DIMENSIONS) + 2)]
    for ptype, systems in sorted(by.items()):
        nat = systems.get("native-tournament")
        models = {s: r for s, r in systems.items() if s.startswith("llm:")}
        if not nat or not models:
            continue

        def tally(r):
            w = l = 0
            for _, k, low in DIMENSIONS:
                a, b = r.get(k), nat.get(k)
                if a is None or b is None or not r.get("produced") or "text_fidelity" not in r:
                    l += 0 if a is not None else 1
                    continue
                if (a < b) if low else (a > b):
                    w += 1
                elif (a > b) if low else (a < b):
                    l += 1
            return l, -w

        best_s, best = min(models.items(), key=lambda kv: tally(kv[1]))
        cells = []
        for _, k, low in DIMENSIONS:
            a, b = best.get(k), nat.get(k)
            fa = "—" if a is None else f"{a:.0f}" if isinstance(a, (int, float)) else str(a)
            fb = "—" if b is None else f"{b:.0f}" if isinstance(b, (int, float)) else str(b)
            cells.append(f"{fa} vs {fb}")
        losses, negwins = tally(best)
        # a tie is not a win: the native page is deterministic, the model page one unrepeated sample
        decision = ("KEEP NATIVE" if losses or not best.get("produced")
                    else "KEEP NATIVE (tie; model stability NOT_MEASURED)" if not negwins
                    else "KEEP NATIVE (model ahead without a loss; stability NOT_MEASURED — repeat samples first)")
        out.append(f"| {ptype} | {best_s} | " + " | ".join(cells) + f" | NOT_MEASURED vs deterministic | **{decision}** |")
    return out + ["", "Cells read `model vs native`. Page types without a model-written page are native by construction.", ""]


# ---------------------------------------------------------------- LOCAL_MODEL_RESOURCE_MATRIX

def _ram(key: str, qstate: dict[str, Any]) -> dict[str, Any]:
    return ((qstate.get("done") or {}).get(f"{key}:ram") or {}).get("info") or {}


def _disk_gb(spec) -> str:
    man = spec.dir / "apex_manifest.json"
    if man.exists():
        files = json.loads(man.read_text(encoding="utf-8")).get("files", [])
        tot = sum(f.get("size", 0) for f in files)
        if tot:
            return f"{tot / 1e9:.1f}"
    freed = spec.dir / "apex_manifest.freed.json"
    if freed.exists():
        files = json.loads(freed.read_text(encoding="utf-8")).get("files", [])
        return f"{sum(f.get('size', 0) for f in files) / 1e9:.1f} (weights freed)"
    return f"~{spec.approx_gb} (registry)"


def _roles(mid: str, policy: dict[str, Any]) -> list[str]:
    out = []
    for r in policy["rows"]:
        if r["primary"] and r["primary"].startswith(mid + " "):
            out.append(f"PRIMARY {r['task']}")
        elif r["fallback"] and r["fallback"].startswith(mid + " "):
            out.append(f"FALLBACK {r['task']}")
    return out


def resource_matrix_md(bench: Path, reg, specs: dict[str, Any], policy: dict[str, Any]) -> str:
    from apex_one.compute.local.resources import (BASE_RESERVES_GB, CHROMIUM_MEASURED_PEAK_GB, EVALUATION_MODE,
                                                  MODE_RULES, PRODUCTION_MODE, PRODUCTION_OVER_EVALUATION_GB,
                                                  PROFILES, admit, baseline_capacity_gb, load_estimates, meminfo,
                                                  prediction_error_bound, raw_estimate, required_headroom)
    from apex_one.compute.router.capability import routing_config

    qstate = _load(bench / "queue_state.json") or {}
    runs_p = bench / "council_runs.jsonl"
    runs = [json.loads(x) for x in runs_p.read_text(encoding="utf-8").splitlines() if x.strip()] if runs_p.exists() else []
    rows = latest_rows(runs)
    scores = (_load(bench / "council_scores.json") or {}).get("models", {})
    calib = _load(bench / "vision_calibration" / "calibration_results.json")
    floor = float(routing_config().get("default_min_score", 50))
    total = meminfo().get("MemTotal", 0.0)
    cap = baseline_capacity_gb()
    est = load_estimates()
    bound = prediction_error_bound()
    out = ["# Local model resource matrix", "", _stamp(), "",
           f"Machine: {total:.1f} GB RAM (10^9 bytes), no swap, 4 CPU threads, no GPU; memory available with no model "
           f"loaded: **{cap:.1f} GB**. On this machine compute scheduling is part of correctness: every stage is "
           "admitted BEFORE it starts (`apex_one/compute/local/resources.py`) with ADMIT / DEFER / RESOURCE_BLOCKED "
           "and an explicit reason; a clean RESOURCE_BLOCKED is a successful scheduler decision.", "",
           "**Modes.** EVALUATION_MODE (one controlled benchmark process) needs ≥ "
           f"**{required_headroom(EVALUATION_MODE, total, bound):.1f} GB** headroom after every reserve, DERIVED from "
           f"measurement: {bound['formula']}. Evidence: worst miss {bound['miss_bound_gb']:.2f} GB "
           f"({bound['miss_model']}: measured peak above the expected peak it was admitted with) + run-to-run peak "
           f"spread {bound['margin_gb']:.2f} GB ({bound['margin_model']}) = {bound['derived_gb']:.1f} GB. "
           f"PRODUCTION_MODE needs ≥ **{required_headroom(PRODUCTION_MODE, total, bound):.2f} GB** = max("
           f"{MODE_RULES[PRODUCTION_MODE]['min_headroom_gb']} GB, {MODE_RULES[PRODUCTION_MODE]['min_headroom_pct']:.0%} of "
           f"MemTotal, evaluation + {PRODUCTION_OVER_EVALUATION_GB} GB) — a second job's worker, long uptimes and real "
           "pages are what evaluation never sees. Base reserves: "
           + ", ".join(f"{k} {v} GB" for k, v in BASE_RESERVES_GB.items()) + ".", "",
           "**Stage profiles** (what runs beside the model): " + "; ".join(
               f"{p.name} = " + " + ".join(f"{k} {v:g}" for k, v in p.reserves().items()) + " GB"
               for p in PROFILES.values())
           + f". Chromium reserve = 2 × its measured peak ({CHROMIUM_MEASURED_PEAK_GB} GB, design-bench memory trace).",
           "",
           "**Expected peak** = the measured peak RSS when this artifact has run before; otherwise the raw estimate "
           "(weights + GGUF-derived KV cache + 0.6 GB) × a safety multiplier: a same-family measured ratio if one "
           "exists, else max(1.25, worst observed ratio).", "",
           "| model | quantization | disk GB | estimated peak GB | measured peak GB | prediction error | load time | "
           "warm-up | median inference latency | swap used (peak) | memory recovery ratio | safe in EVALUATION_MODE | "
           "safe in PRODUCTION_MODE | recommended concurrency | recommended role |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for mid, name, key in COMPARED + JUDGE_CANDIDATES:
        spec = specs.get(key)
        if spec is None:
            continue
        r = _ram(key, qstate)
        cyc = r.get("last_cycle") or {}
        e = est.get(key) or {}
        raw, _ = raw_estimate(spec)
        measured = e.get("measured_peak_gb") or r.get("peak_rss_gb")
        err = (f"{measured - raw:+.1f} GB ({measured / raw:.2f}×)" if measured and raw else "—")
        lats = [rows[(mid, t)]["latency_s"] for _, t in MATRIX_TASKS if (mid, t) in rows and rows[(mid, t)].get("score") is not None]
        roles = _roles(mid, policy)
        lic = licence_cell(reg, mid)
        vis = vision_cell(mid, calib, getattr(spec, "vision", True))
        if "CANONICAL_640_ONLY" in vis and any("visual finalist" in x for x in roles):
            roles = [x for x in roles if "visual finalist" not in x] + ["SECONDARY_FINALIST_PAIRWISE_JUDGE (640 px only)"]
        if not roles:
            roles = (["research / evaluation only (licence " + lic + ")"] if "ALLOWED" not in lic
                     else ["no production role (no task where it is the best qualified)"])

        def safe(mode: str) -> str:
            stages = {"text": "TEXT_ONLY_MODEL_CALL", "vision": "VISION_PAGE_JUDGING", "+Chromium": "MODEL_PLUS_CHROMIUM"}
            got = []
            for label, prof in stages.items():
                step = {"TEXT_ONLY_MODEL_CALL": "vector", "VISION_PAGE_JUDGING": "council",
                        "MODEL_PLUS_CHROMIUM": "pages"}[prof]
                d = admit(spec, step, qstate, available=cap, others=[], mode=mode, capacity=cap)
                got.append(f"{label} {'✓' if d.decision == 'ADMIT' else '✗'}")
            return ", ".join(got)

        ev, pr = safe(EVALUATION_MODE), safe(PRODUCTION_MODE)
        conc = ("model + Chromium together" if "+Chromium ✓" in ev else
                "sequential only: model, unload, then Chromium" if "text ✓" in ev else "does not fit this machine")
        out.append(f"| {name} | {spec.tag} | {_disk_gb(spec)} | {raw:.1f} raw | {measured or 'NOT_MEASURED'} | {err} | "
                   f"{str(cyc.get('load_time_s')) + ' s' if cyc.get('load_time_s') is not None else '—'} | "
                   f"{str(cyc.get('warmup_time_s')) + ' s' if cyc.get('warmup_time_s') is not None else '—'} | "
                   f"{f'{statistics.median(lats):.0f} s' if lats else 'NOT_MEASURED'} | "
                   f"{cyc.get('swap_used_peak_gb', '—')} | {cyc.get('memory_recovery_ratio', '—')} | {ev} | {pr} | "
                   f"{conc}; never two large models | {'; '.join(roles)} |")
    out += ["", "✓/✗ = the scheduler's decision for that stage profile on an idle machine (text = text-only model "
            "calls; vision = page judging with image buffers; +Chromium = model and renderer resident together). "
            "Median inference latency = median wall time of the model's measured council calls (CPU only, one request "
            "at a time). Swap / recovery come from the last scheduled load-unload cycle (recorded from 2026-10-31); "
            "'—' = no cycle under the scheduler yet. A model may legitimately end with no production role — that is a "
            "benchmark result.", ""]
    out += cycles_md(qstate)
    return "\n".join(out) + "\n"


def load_test_md(rep: dict[str, Any] | None) -> list[str]:
    """PRODUCTION_MODE under controlled concurrent load (apex_one/lab/load_test.py)."""
    out = ["## Production load test (PRODUCTION_MODE, real model, real Chromium)", ""]
    if not rep:
        return out + ["NOT_RUN — `python -m apex_one.lab.load_test --model qwen3-vl-4b-q4kxl`", ""]
    if rep.get("verdict") == "RESOURCE_BLOCKED":
        return out + [f"RESOURCE_BLOCKED — {rep.get('reason')}", ""]
    out += [f"**Verdict: {rep['verdict']}** — model `{rep['model']}` (real: {rep['real_model']}), run {rep.get('at')} "
            f"at commit `{rep.get('commit')}`. A job = one supervised production model call + one memory-admitted "
            "Chromium render to PDF + one idempotent SQLite write, through a bounded journalled queue. Required "
            f"production headroom {rep['scenarios'][0]['required_production_headroom_gb'] if rep['scenarios'] else '?'} GB."
            + (f" Provenance: {rep['provenance_note']}" if rep.get("provenance_note") else ""),
            "", "| scenario | verdict | jobs (done / failed / rejected) | failure rate | throughput (jobs/min) | queue "
            "delay p50 / p95 s | latency p50 / p95 s | model p50 s | render p50 s | min free RAM GB | server peak "
            "RSS GB | CPU avg / max % | swap GB | render admissions (ADMIT / DEFER) | recovery | commit | notes |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["scenarios"]:
        notes = "; ".join(f"{k}={v}" for k, v in r.items() if k in (
            "server_killed", "restarts", "recovery_events", "db_rows", "duplicate_side_effects", "ballast_gb",
            "failures_by_kind") and v not in (None, {}, []))
        rec = r.get("recovery_time_s")
        out.append(f"| {r['scenario']} | **{r['verdict']}** | {r['done']} / {r['failed']} / "
                   f"{r['rejected_backpressure']} | {r['failure_rate']} | {r['throughput_jobs_per_min']} | "
                   f"{r['queue_delay_s']['p50']} / {r['queue_delay_s']['p95']} | {r['latency_s']['p50']} / "
                   f"{r['latency_s']['p95']} | {r['model_s_p50']} | {r['render_s_p50']} | {r['min_available_gb']} | "
                   f"{r['server_peak_rss_gb']} | {r['cpu_avg_pct']} / {r['cpu_max_pct']} | {r['swap_peak_gb']} | "
                   f"{r['admissions'].get('ADMIT', 0)} / {r['admissions'].get('DEFER', 0)} | "
                   f"{'—' if rec is None else f'{rec} s'} | `{r.get('commit', '?')}` | {notes or '—'} |")
    out += ["", "Rejected = back-pressure (queue full: the caller retries later), never a failure. Failures are "
            "classified by kind and are INFRASTRUCTURE_ERROR, never a quality score. DEFER = the render waited for "
            "memory instead of starting (throttle, not OOM).", ""]
    return out


def cycles_md(qstate: dict[str, Any]) -> list[str]:
    """Measured memory lifecycle of every scheduled load/unload cycle + every RESOURCE_BLOCKED decision."""
    out = ["## Memory lifecycle per load / unload cycle (resource scheduler)", "",
           "Available memory (GB) at each point; recovery = available after stabilisation / available before load "
           "(< 0.95 → MEMORY_LEAK_OR_RESIDUAL, and no next large model loads).", "",
           "| model | mode | before load | after load | after warm-up | min while loaded | before unload | after exit | "
           "after stabilisation | recovery | server peak RSS | swap before / peak | major faults | load / warm-up / "
           "unload | latency degradation | flags |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    n = 0
    for mid, name, key in COMPARED + JUDGE_CANDIDATES:
        for c in _ram(key, qstate).get("cycles", []):
            n += 1
            g = lambda k: c.get(k, "—")  # noqa: E731
            # cycles recorded before the mode-aware scheduler (or by a run that failed mid-load) carry no mode
            mode = c.get("mode") or "pre-scheduler record (partial)"
            out.append(f"| {name} | {mode} | {g('available_before_load_gb')} | {g('available_after_load_gb')} | "
                       f"{g('available_after_warmup_gb')} | {g('min_available_while_loaded_gb')} | "
                       f"{g('available_before_unload_gb')} | {g('available_after_exit_gb')} | "
                       f"{g('available_after_unload_gb')} | {g('memory_recovery_ratio')} | {g('peak_rss_gb')} | "
                       f"{g('swap_used_before_gb')} / {g('swap_used_peak_gb')} | {g('server_major_faults')} | "
                       f"{g('load_time_s')} / {g('warmup_time_s')} / {g('unload_time_s')} s | "
                       f"{g('latency_degradation_ratio')} | {', '.join(c.get('flags') or []) or '—'} |")
    if not n:
        out.append("| — | no cycle recorded yet under the scheduler |" + " |" * 14)
    blocked = [(k, v.get("info")) for k, v in (qstate.get("failed") or {}).items()
               if str(v.get("info", "")).startswith("RESOURCE_BLOCKED")]
    out += ["", "**RESOURCE_BLOCKED decisions** (a refusal is recorded, never an OOM):", ""]
    by_model: dict[str, tuple[list[str], str]] = {}
    for k, i in blocked:
        model, _, step = k.partition(":")
        by_model.setdefault(model, ([], str(i)))[0].append(step)
    out += [f"* `{m}` ({len(steps)} steps: {', '.join(steps)}) — {i}" for m, (steps, i) in by_model.items()] \
        or ["* none"]
    return out + [""]
