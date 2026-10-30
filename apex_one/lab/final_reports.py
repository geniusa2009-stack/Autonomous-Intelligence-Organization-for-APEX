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
        out.append("none recorded")
    qstate = _load(bench / "queue_state.json") or {}
    out += [""] + cycles_md(qstate)
    tests = "tests/test_server_reliability.py"
    out += ["", f"Regression tests: `{tests}` (classification, bounded restart with backoff, the full drill, GDB "
            "failures carry their kind).", ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- frozen production routing policy

def production_policy(reg, runs: list[dict[str, Any]], bench: Path) -> dict[str, Any]:
    """PRIMARY / FALLBACK / NO_QUALIFIED_MODEL / DETERMINISTIC_ENGINE / HUMAN_REQUIRED per task, from evidence."""
    from apex_one.compute.local import load_catalogue
    from apex_one.compute.router.capability import rejection, routing_config, task_evidence_score
    from apex_one.compute.router.fallback import has_native_fallback
    from apex_one.lab.benchmarks.page_compare import verdicts
    from apex_one.vision.council import judge_status, reliable_judges

    cfg = routing_config()
    _, specs = load_catalogue()
    installed = {s.registry_model for s in specs.values() if (s.dir / "apex_manifest.json").exists()}
    measured = [m for m in reg.models.values() if m.benchmark_scores]
    rows: list[dict[str, Any]] = []

    def add(task: str, decision: str, primary: str | None = None, fallback: str | None = None, why: str = "") -> None:
        rows.append({"task": task, "decision": decision, "primary": primary, "fallback": fallback, "why": why})

    add("critical date arithmetic (date.*)", "DETERMINISTIC_ENGINE", "apex_one.core.dates", None,
        "permanently outside model reasoning; the $0 firewall refuses date.* for every model")
    add("critical locked facts (deadline, eligibility, funding)", "DETERMINISTIC_ENGINE", "evidence system + fact locks",
        "HUMAN_REQUIRED for single-source critical claims", "models may phrase a locked fact, never change it")
    for task, rule in cfg.get("tasks", {}).items():
        if "requires" not in rule:
            continue
        ok = []
        for m in measured:
            sc = task_evidence_score(m, task)
            if sc is None or rejection(m, task) or not reg.production_allowed(m) or m.id not in installed:
                continue
            ok.append((sc, m.id))
        ok.sort(key=lambda x: (-x[0], x[1]))
        if ok:
            add(task, "PRIMARY", f"{ok[0][1]} ({ok[0][0]:.0f})", f"{ok[1][1]} ({ok[1][0]:.0f})" if len(ok) > 1 else None,
                f"requires {', '.join(rule['requires'])}; production-licensed, installed, ≥ floor")
        else:
            add(task, "NO_QUALIFIED_MODEL", "APEX native engine" if has_native_fallback(task) else None, None,
                f"no production-licensed model passes {', '.join(rule['requires'])} at the floor")
    pw = reliable_judges(mode="pairwise")[0]
    add("visual finalist comparison (A/B)", "PRIMARY" if pw else "NO_QUALIFIED_MODEL",
        f"{pw[0]} as SECONDARY_FINALIST_PAIRWISE_JUDGE ({judge_status(pw[0])[0]})" if pw else None,
        "deterministic tournament order",
        "advisory only; canonical 640 px A4 renders of QA-passed finalists; never facts, dates, Arabic quality")
    ab = reliable_judges()[0]
    add("visual quality scores (absolute council)", "PRIMARY" if ab else "NO_QUALIFIED_MODEL", ab[0] if ab else None,
        None, "needs absolute calibration ≥ 4/5 AND ROBUSTLY_CALIBRATED; otherwise Vision Quality = NOT_MEASURED")
    add("SVG / vector assets", "NO_QUALIFIED_MODEL", "native SVG assets", None,
        "specialist vector models (StarVector / OmniSVG) not activated: weights host egress-denied")
    add("document layout", "DETERMINISTIC_ENGINE", "APEX native layout engine + tournament", None,
        "specialist layout models not activated")
    cmp_ = _load(bench / "apex_design" / "page_compare.json")
    v = verdicts(cmp_) if cmp_ else {}
    winners = [s for s, d in v.items() if not d["safety_losses"] and d["wins"]]
    add("page design (HTML writing)", "DETERMINISTIC_ENGINE", "APEX native engine",
        None, "no model page beat native without a safety loss" if not winners else
        f"model wins without safety loss: {winners} (not yet promoted; needs the per-page-type comparison)")
    add("release approval", "HUMAN_REQUIRED", "authenticated approver (token)", None, "hash-chained approval ledger")
    add("brand assets", "HUMAN_REQUIRED", "apex-one brand import", None, "original APEX package; placeholders fail")
    evidence = {p.name: _sha(p) for p in (bench / "council_scores.json",
                                          bench / "vision_calibration" / "calibration_results.json",
                                          bench / "apex_design" / "page_compare.json")}
    for p in sorted((bench / "vision_robustness").glob("*.json")) if (bench / "vision_robustness").exists() else []:
        evidence[f"vision_robustness/{p.name}"] = _sha(p)
    return {"frozen_at_commit": _head(), "evidence_sha256_12": evidence, "rows": rows,
            "rule": "no global best model; per-task evidence; licence + installation required for production"}


def policy_md(policy: dict[str, Any]) -> list[str]:
    out = ["## Frozen production routing policy", "",
           f"Frozen at commit `{policy['frozen_at_commit']}` against evidence "
           + ", ".join(f"`{k}`={v}" for k, v in policy["evidence_sha256_12"].items())
           + " (`docs/evidence/production_routing_policy.json`). Any change to that evidence requires regenerating "
           "and re-reviewing this table. A model is never routed to merely because it is installed.", "",
           "| task | decision | primary | fallback | why |", "|---|---|---|---|---|"]
    for r in policy["rows"]:
        out.append(f"| {r['task']} | **{r['decision']}** | {r['primary'] or '—'} | {r['fallback'] or '—'} | {r['why']} |")
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
        decision = "KEEP NATIVE" if losses or not best.get("produced") else "model wins, review for promotion"
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
    from apex_one.compute.local.resources import (RENDERER_RESERVE_GB, RESERVES_GB, SAFETY_MARGIN_GB, admit,
                                                  meminfo)
    from apex_one.compute.router.capability import routing_config

    qstate = _load(bench / "queue_state.json") or {}
    runs_p = bench / "council_runs.jsonl"
    runs = [json.loads(x) for x in runs_p.read_text(encoding="utf-8").splitlines() if x.strip()] if runs_p.exists() else []
    rows = latest_rows(runs)
    scores = (_load(bench / "council_scores.json") or {}).get("models", {})
    calib = _load(bench / "vision_calibration" / "calibration_results.json")
    floor = float(routing_config().get("default_min_score", 50))
    total = meminfo().get("MemTotal", 0.0)
    cycles = [c for v in (qstate.get("done") or {}).values() if isinstance(v, dict)
              for c in ((v.get("info") or {}).get("cycles") or []) if isinstance(v.get("info"), dict)]
    measured_idle = max((c.get("available_before_load_gb", 0.0) for c in cycles), default=0.0)
    idle = measured_idle or round(total * 0.95, 1)
    idle_src = ("highest MemAvailable recorded before a load" if measured_idle
                else "ESTIMATE 95% of MemTotal — no load recorded under the scheduler yet")
    out = ["# Local model resource matrix", "", _stamp(), "",
           f"Machine: {total:.1f} GB RAM, no swap, 4 CPU threads, no GPU. Memory available with no model loaded: "
           f"**{idle:.1f} GB** ({idle_src}). On this machine compute scheduling is "
           "part of correctness: the resource scheduler (`apex_one/compute/local/resources.py`) refuses a load "
           "with RESOURCE_BLOCKED when `expected_peak + reserves > available`, never runs two large models at once, "
           "and asserts after every unload that the server process is gone and its memory has returned.", "",
           "Reserves (headroom beside the model, GB): " + ", ".join(f"{k} {v}" for k, v in RESERVES_GB.items())
           + f", safety margin {SAFETY_MARGIN_GB}; + renderer {RENDERER_RESERVE_GB} for stages that start Chromium "
           "(model-written pages, golden runs). Expected peak = the MEASURED peak RSS of the artifact when it has run "
           "before, else weights + KV cache (from GGUF metadata, configured context) + 0.6 GB compute.", "",
           "| model | quantization | disk GB | loaded RAM GB | peak RAM GB | load time | unload time | median inference "
           "latency | vision capability | text capability (≥ floor) | production status | recommended role | safe "
           "concurrent services |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for mid, name, key in COMPARED + JUDGE_CANDIDATES:
        spec = specs.get(key)
        if spec is None:
            continue
        r = _ram(key, qstate)
        cyc = r.get("last_cycle") or {}
        lats = [rows[(mid, t)]["latency_s"] for _, t in MATRIX_TASKS if (mid, t) in rows and rows[(mid, t)].get("score") is not None]
        good = [c for c, t in MATRIX_TASKS if (scores.get(mid) or {}).get(t) is not None and scores[mid][t] >= floor]
        bad = [c for c, t in MATRIX_TASKS if (scores.get(mid) or {}).get(t) is not None and scores[mid][t] < floor]
        roles = _roles(mid, policy)
        lic = licence_cell(reg, mid)
        vis = vision_cell(mid, calib, getattr(spec, "vision", True))
        if "CANONICAL_640_ONLY" in vis and any("visual finalist" in x for x in roles):
            roles = [x for x in roles if "visual finalist" not in x] + ["SECONDARY_FINALIST_PAIRWISE_JUDGE (640 px only)"]
        if not roles:
            roles = (["research / evaluation only (licence " + lic + ")"] if "ALLOWED" not in lic
                     else ["no production role (no task where it is the best qualified)"])
        peak = r.get("peak_rss_gb")
        if peak:
            renderer = admit(spec, "pages", qstate, available=idle, others=[]).admitted
            safe = f"Chromium renderer: {'yes' if renderer else 'NO (RESOURCE_BLOCKED)'}; second model: never"
        else:
            safe = "NOT_MEASURED (no recorded peak)"
        out.append(f"| {name} | {spec.tag} | {_disk_gb(spec)} | {r.get('loaded_rss_gb', 'NOT_MEASURED')} | "
                   f"{peak or 'NOT_MEASURED'} | {str(cyc.get('load_time_s', '—')) + ' s' if cyc else '—'} | "
                   f"{str(cyc.get('unload_time_s', '—')) + ' s' if cyc else '—'} | "
                   f"{f'{statistics.median(lats):.0f} s' if lats else 'NOT_MEASURED'} | {vis} | "
                   f"strong: {', '.join(good) or '—'}; weak: {', '.join(bad) or '—'} | {lic} | {'; '.join(roles)} | {safe} |")
    out += ["", "Median inference latency = median wall time of the model's measured council calls (CPU only, "
            "one request at a time). Loaded / peak RAM = llama-server resident memory after the warm-up request and "
            "its high-water mark; recorded from 2026-10-30 — models measured earlier show NOT_MEASURED until they "
            "run again. A model may legitimately end with no production role: that is a benchmark result, not a "
            "failure of the benchmark.", ""]
    out += cycles_md(qstate)
    return "\n".join(out) + "\n"


def cycles_md(qstate: dict[str, Any]) -> list[str]:
    """Scheduler accounting of every recorded load/unload cycle + every RESOURCE_BLOCKED decision."""
    out = ["## Load / unload cycles (resource scheduler accounting)", "",
           "| model | rss before load (system) | rss after warm-up (server) | peak rss (server) | rss after unload "
           "(system) | swap used | load time | unload time |", "|---|---|---|---|---|---|---|---|"]
    n = 0
    for mid, name, key in COMPARED + JUDGE_CANDIDATES:
        for c in _ram(key, qstate).get("cycles", []):
            n += 1
            out.append(f"| {name} | {c.get('rss_before_load_gb')} GB | {c.get('rss_after_warmup_gb', '—')} GB | "
                       f"{c.get('peak_rss_gb', '—')} GB | {c.get('rss_after_unload_gb')} GB | {c.get('swap_used_gb')} GB | "
                       f"{c.get('load_time_s')} s | {c.get('unload_time_s')} s |")
    if not n:
        out.append("| — | no cycle recorded yet under the scheduler | | | | | | |")
    blocked = [(k, v.get("info")) for k, v in (qstate.get("failed") or {}).items()
               if str(v.get("info", "")).startswith("RESOURCE_BLOCKED")]
    out += ["", "**RESOURCE_BLOCKED decisions** (a refusal is recorded, never an OOM):", ""]
    out += [f"* `{k}` — {i}" for k, i in blocked] or ["* none"]
    return out + [""]
