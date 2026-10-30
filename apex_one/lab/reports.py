"""Phase 14+ reports, generated from measured artifacts only.

Every number in these reports is read from an artifact produced by a real run in this environment; anything not
run is printed as NOT_MEASURED / PENDING with the reason. Regenerate with `apex-one reports build`.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from apex_one.settings import get_settings


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _fmt(v: Any, nd: int = 1) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _stamp() -> str:
    return f"_Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `apex-one reports build` from measured artifacts._\n"


# ---------------------------------------------------------------- LIVE_PROVIDER_REPORT


def live_provider_md(rows: list[dict[str, Any]] | None) -> str:
    out = ["# Live Provider Report (Phase 14)", "", _stamp(),
           "Statuses: LIVE_TESTED (a real structured task ran through the $0 firewall and returned output), "
           "LIVE_FAILED, CREDENTIALS_REQUIRED, NO_FREE_ROUTE, NETWORK_BLOCKED (egress proxy denied CONNECT), "
           "LICENSE_BLOCKED, UNKNOWN. A status is never inferred: rows without an executed call are not LIVE_TESTED.",
           ""]
    if not rows:
        return "\n".join(out + ["NOT_MEASURED: no live report yet (`apex-one providers live-test`)."]) + "\n"
    out += ["| provider | model | status | structured task correct | latency | measured at | evidence |",
            "|---|---|---|---|---|---|---|"]
    for r in rows:
        ev = r.get("network") or r.get("detail") or r.get("credentials") or r.get("error") or ""
        if r.get("status") == "LIVE_TESTED":
            ev = f"{r.get('structured_output', '')} · {r.get('cost_basis', '')}"
        lat = f"{r['structured_ms'] / 1000:.1f} s" if r.get("structured_ms") else "—"
        at = str(r.get("at", ""))[:16].replace("T", " ") or "—"
        out.append(f"| {r.get('provider', '')} | {r.get('model', '')} | **{r.get('status')}** | "
                   f"{_fmt(r.get('structured_correct'))} | {lat} | {at} | {str(ev).replace('|', '/')[:140]} |")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    by = {s: sorted({r.get("provider", "") for r in rows if r["status"] == s}) for s in counts}
    live = sorted({r.get("model", "") for r in rows if r["status"] == "LIVE_TESTED"})
    out += ["", "**Totals:** " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), "",
            "## What this means (derived from the rows above)", ""]
    for status in sorted(by):
        out.append(f"* **{status}**: {', '.join(p for p in by[status] if p) or '—'}")
    out += ["", f"* Executable $0 routes with a correct live structured answer: {', '.join(live) or 'NONE'}.",
            "* NETWORK_BLOCKED rows are not routed around; CREDENTIALS_REQUIRED rows were not given accounts.",
            "* Local models whose licence is not verified in the licence registry are used for EVALUATION only.", ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- MODEL_ACTIVATION_REPORT


def model_activation_md(catalogue: dict[str, Any], scores: dict[str, Any] | None, calibration: dict[str, Any] | None,
                        live: dict[str, Any] | None, registry) -> str:
    out = ["# Model Activation Report (Phases 14–15)", "", _stamp(),
           "Real local inference: llama.cpp `llama-server` (built from source in this container) serving GGUF "
           "models pulled from the Docker Hub `ai/` OCI catalogue, each blob sha256-verified. One model in RAM at a "
           "time (4 vCPU, 15.7 GB RAM, no GPU).", "",
           "## Acquired models", "",
           "| key | registry model | source | size | vision | live structured test | licence state |",
           "|---|---|---|---|---|---|---|"]
    for key, spec in catalogue.items():
        man = _load(spec.dir / "apex_manifest.json")
        size = sum(f["size"] for f in man["files"]) / 1e9 if man else None
        lv = (live or {}).get(key, {})
        try:
            lic = registry.license_for(spec.registry_model)
            lic_s = f"{lic.production_state.value} ({lic.id})"
        except Exception:  # noqa: BLE001
            lic_s = "not in registry"
        lic_files = ", ".join(man.get("licence_files", [])) if man else ""
        if lic_files:
            lic_s += f"; artifact ships `{lic_files}`"
        out.append(f"| {key} | {spec.registry_model} | `{spec.repository}:{spec.tag}` | "
                   f"{_fmt(size, 2) + ' GB' if size else 'NOT ACQUIRED'} | {spec.vision} | "
                   f"{lv.get('status', 'PENDING')}{' (correct)' if lv.get('structured_correct') else ''} | {lic_s} |")
    out += ["", "## General council benchmark (Phase 15)", "",
            "Tasks are scored by deterministic checkers (no model grades another model): date reasoning, Egyptian "
            "Arabic register, EN/AR term mixing, structured JSON extraction (exact fields), fact preservation through "
            "rewriting, RTL HTML/CSS contract, design criticism coverage, long-context needle, and (vision models) "
            "order-swapped pairwise visual hierarchy.", ""]
    tasks = ["reasoning", "egyptian_arabic", "en_ar_mixing", "english_factual_writing", "structured_editorial",
             "structured_json", "fact_preservation", "html_css", "design_criticism", "long_context", "visual_hierarchy"]
    if not scores or not scores.get("models"):
        out.append("PENDING: the council benchmark has not produced scores yet.")
    else:
        out += ["| model | " + " | ".join(tasks) + " | measured tasks |", "|---|" + "---|" * (len(tasks) + 1)]
        for mid, e in scores["models"].items():
            n = sum(1 for t in tasks if e.get(t) is not None)
            out.append(f"| {mid} | " + " | ".join(_fmt(e.get(t), 0) for t in tasks) + f" | {n}/{len(tasks)} |")
        out += ["", "`—` = NOT_MEASURED (not run, not applicable, or empty output because a reasoning model spent its "
                "token budget on hidden reasoning; re-run with a larger budget). **No overall mean is shown**: the "
                "rows cover different task sets, and an average would hide a 0 (e.g. Egyptian Arabic or date "
                "reasoning) behind unrelated 100s. Compare per task; routing uses the capability vector in "
                "PRODUCTION_ROUTING_MATRIX.md. "
                + (f"Checker version {scores.get('checker_version')}: scores recomputed from stored outputs."
                   if scores.get("checker_version") else "")]
        out += ["", "These measured scores overwrite the registry's prior estimates (`capability_source: "
                "apex-benchmark`), so the CapabilityRouter now ranks local models by what they actually did here."]
    out += ["", "## Vision judge calibration (Phase 18)", "",
            "Each vision model reviews a known-good page and five deliberately broken variants (low contrast, card "
            "overuse, gradient, cramped, no hierarchy). A judge is RELIABLE only if it scores the good page above "
            "the broken one on the targeted role in ≥ 60 % of cases. Unreliable judges never influence gates.", ""]
    if not calibration or not calibration.get("models"):
        out.append("PENDING: calibration has not completed.")
    else:
        out += ["| model | low_contrast | card_overuse | gradient | cramped | no_hierarchy | discrimination | reliable |",
                "|---|---|---|---|---|---|---|---|"]
        for mid, r in calibration["models"].items():
            c = r.get("checks", {})
            out.append(f"| {mid} | " + " | ".join(_fmt(c.get(k)) for k in
                                                   ("low_contrast", "card_overuse", "gradient", "cramped", "no_hierarchy"))
                       + f" | {_fmt(r.get('discrimination_rate'), 2)} | **{r.get('reliable')}** |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- DESIGN_MODEL_ACTIVATION


def design_activation_md(systems: dict[str, Any], gdb_runs: dict[str, Any], reliable: list[str] | None = None) -> str:
    out = ["# Design Model Activation (Phases 16, 19, 26)", "", _stamp(),
           "Every design system named in the APEX spec, with the evidence actually gathered here. Statuses: "
           "ACTIVATED, PROTOCOL_REIMPLEMENTED, PACKAGE_INSTALLABLE, WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED, "
           "ARCHITECTURE_REFERENCE, NOT_RELEASED_OR_UNFOUND, LICENSE_BLOCKED, RESEARCH_ONLY. Nothing is marked "
           "ACTIVATED without a stored smoke-test artifact.", "",
           "Environment facts behind most rows: huggingface.co / GitHub releases / arXiv are denied by the egress "
           "policy (weights unreachable); 4 vCPU + 15.7 GB RAM + no GPU (7B+ VLMs blocked without GGUF builds).", "",
           "| system | **final state** | source (evidence) | reported licence | checkpoint host | hardware | local | "
           "$0 remote | adapter | smoke test / artifacts | detail statuses |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in systems.items():
        src = s.get("source", {})
        src_s = "; ".join(f"{k}: {v}" for k, v in src.items() if k != "evidence")[:90] + f" ({src.get('evidence', '?')})"
        lic = s.get("reported_license", {})
        host = s.get("checkpoint", {}).get("host", "")
        status = list(s.get("status", []))
        smoke = "—"
        adapter = "registry entry (UNAVAILABLE)"
        local = "no"
        if name == "PosterReward":
            adapter = "apex_one/vision/pairwise.py (protocol)"
            smoke = ("pairwise unit tests; live judges: " + (", ".join(reliable) if reliable else
                     "NONE yet (no calibrated-reliable vision judge) — the protocol does not run in jobs"))
        if name == "GraphicDesignBench":
            adapter = "apex_one/lab/benchmarks/gdb_provider.py"
            local = "yes (package)"
            done = {k: v for k, v in gdb_runs.items() if v.get("valid")}
            if done:
                smoke = "; ".join(f"{k}: {v['summary']}" for k, v in done.items())[:160]
                status = ["ACTIVATED (smoke bundle)" if x == "PACKAGE_INSTALLABLE" else x for x in status]
            else:
                smoke = "`gdb verify` (stub) passed; local-model run pending"
        fs = s.get("final_state", "NOT_IMPLEMENTED")
        if name == "GraphicDesignBench" and not any(v.get("valid") for v in gdb_runs.values()):
            fs = "ADAPTER_TESTED_ONLY"   # LIVE_TESTED only while a real run's scores are on disk
        out.append(f"| {name} | **{fs}** | {src_s} | {lic.get('value', '—')} | {host} | {s.get('hardware', '—')[:60]} | "
                   f"{local} | no | {adapter} | {smoke} | {', '.join(status)} |")
        notes = "; ".join(x for x in (s.get("final_note"), s.get("apex_use")) if x)
        if notes:
            out.append(f"| ↳ | {notes} | | | | | | | | | |")
    counts: dict[str, int] = {}
    for s_ in systems.values():
        counts[s_.get("final_state", "NOT_IMPLEMENTED")] = counts.get(s_.get("final_state", "NOT_IMPLEMENTED"), 0) + 1
    out += ["", "**Final states:** " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), ""]
    out += ["", "## What actually runs", "",
            "* **Design generation:** the native APEX engines (layout genome, compiler, tournament) — licence-clean.",
            ("* **Design judging:** calibrated-reliable local vision judges: " + (", ".join(reliable) if reliable else
             "NONE — no judge has passed calibration, so the Vision Council and the pairwise protocol report "
             "NOT_MEASURED in jobs") + "."),
            "* **Design benchmarking:** APEX Design Bench (15 page types) and the GraphicDesignBench smoke bundle "
            "through the $0 broker.",
            "* **Not running:** every specialist checkpoint above whose weights are unreachable or too large; their "
            "roles are filled by native engines and recorded as such in each job's `design_routes.json`.", ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- APEX_DESIGN_BENCH


def page_compare_md(cmp: dict[str, Any] | None) -> list[str]:
    from apex_one.lab.benchmarks.page_compare import METRICS, verdicts

    if not cmp:
        return ["## Model-written pages vs native", "", "NOT_MEASURED: run the page comparison "
                "(apex_one.lab.benchmarks.page_compare.remeasure).", ""]
    systems = sorted({r["system"] for r in cmp["rows"]})
    out = ["## Model-written pages vs native (separate metrics)", "",
           "Same content, same renderer, same checks. Means over the page types each system produced; "
           "`overflow` = issue count (lower is better); `repetition` = mean pairwise layout similarity between a "
           "system's own pages (lower = less repetitive).", "",
           "| system | pages produced | " + " | ".join(METRICS) + " | repetition |",
           "|---|---|" + "---|" * (len(METRICS) + 1)]
    for sysn in systems:
        rows = [r for r in cmp["rows"] if r["system"] == sysn]
        cells = []
        for m in METRICS:
            vals = [r[m] for r in rows if r.get(m) is not None]
            cells.append(_fmt(sum(vals) / len(vals)) if vals else "—")
        produced = sum(1 for r in rows if r.get("produced") and "text_fidelity" in r)
        out.append(f"| {sysn} | {produced}/{len(rows)} | " + " | ".join(cells)
                   + f" | {_fmt(cmp['layout_repetition'].get(sysn))} |")
    v = verdicts(cmp)
    if v:
        out += ["", "### Decision per model system (vs native-tournament, same page types)", ""]
        for sysn, d in v.items():
            out.append(f"* **{sysn}** — {d['decision']}. Wins: {len(d['wins'])}; safety losses "
                       f"(facts/RTL/text/overflow): {len(d['safety_losses'])}; other losses: {len(d['losses'])}."
                       + (f" Examples of safety losses: {d['safety_losses'][:3]}" if d['safety_losses'] else ""))
    else:
        out += ["", "No model-written pages measured yet: native stays the page designer by default."]
    return out + [""]


def design_bench_md(bench: dict[str, Any] | None, rows: list[dict[str, Any]], unit_bench: dict[str, Any] | None,
                    cmp: dict[str, Any] | None = None) -> str:
    out = ["# APEX Design Bench (Phase 17)", "", _stamp(),
           "Fifteen page types (every semantic page type of the Document AST), content from a real pipeline run "
           "(golden job AST + fact locks). Each system produces one page per type; all pages are rendered by the same "
           "Chromium and measured by the same deterministic page QA. **No single score is reported by design.**", "",
           "Systems: `native-baseline` (fixed editorial-column genes, no search), `native-tournament` (layout "
           "search, ULTRA-like budget), `llm:<model>` (a local model writes the page HTML itself under the APEX DOM "
           "contract; evaluation only).", ""]
    if not bench:
        return "\n".join(out + ["NOT_MEASURED: run the bench first."]) + "\n"
    metrics = ["design.hierarchy", "design.typography", "design.brand_fit", "rtl.quality", "accessibility.contrast",
               "fact.critical_accuracy", "geometry.alignment"]
    out += ["## Per-system summary (mean / min over pages)", "",
            "| system | pages | produced | critical pages | contract violations | median latency | "
            + " | ".join(m.split(".")[-1] for m in metrics) + " |",
            "|---|---|---|---|---|---|" + "---|" * len(metrics)]
    for name, e in bench["systems"].items():
        cells = []
        for m in metrics:
            x = e["metrics"].get(m, {})
            cells.append(f"{_fmt(x.get('mean'))} / {_fmt(x.get('min'))}" if x.get("mean") is not None else "—")
        out.append(f"| {name} | {e['pages']} | {e['produced']} | {e['critical_pages']} | {e['contract_violations']} | "
                   f"{_fmt(e['median_latency_s'])} s | " + " | ".join(cells) + " |")
    out += ["", "## Per page type", "", "| page type | system | critical | hierarchy | typography | brand | alignment | "
            "whitespace (descriptive) | detail |", "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["page_type"], r["system"])):
        m = r["metrics"]
        out.append(f"| {r['page_type']} | {r['system']} | {r['critical']} | {_fmt(m.get('design.hierarchy'), 0)} | "
                   f"{_fmt(m.get('design.typography'), 0)} | {_fmt(m.get('design.brand_fit'), 0)} | "
                   f"{_fmt(m.get('geometry.alignment'), 0)} | {_fmt(m.get('geometry.whitespace_ratio'), 0)} | "
                   f"{(str(r.get('detail', '')) + ('; ' + '; '.join(r['contract']) if r['contract'] else '')).replace('|', '/')[:90]} |")
    out += ["", "## Reading the results", "",
            "* The deterministic metrics are a **correctness floor**, not a beauty ranking: both native systems "
            "saturate most of them, so they cannot tell a good page from a great one. Ranking among valid pages needs "
            "the calibrated Vision Council and human A/B/C preferences.",
            "* `whitespace` is 100×(1 − ink coverage): descriptive, not a quality score. The tournament deliberately "
            "fills pages closer to each page's density target.",
            "* LLM page writers are measured under the same contract; content they produce never ships (licence "
            "UNKNOWN → evaluation only).", ""]
    out += page_compare_md(cmp)
    if unit_bench:
        out += ["## Targeted design risk cases", "",
                f"{unit_bench['passed']}/{unit_bench['measured']} measured cases pass; {unit_bench['not_measured']} "
                "NOT_MEASURED.", "", "| case | expectation | status | detail |", "|---|---|---|---|"]
        for c in unit_bench["cases"]:
            out.append(f"| {c['case']} | {c['expectation'][:60]} | {c['status']} | {str(c['detail'])[:80]} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- build


def gdb_report_valid(rep: Any) -> bool:
    """A GDB run counts only if it produced at least one numeric score, no top-level error and NO failed sample
    (GDB folds failed samples into its scores as empty predictions, i.e. as wrong answers)."""
    if not isinstance(rep, dict) or rep.get("error"):
        return False
    if any(r.get("failure_count") for pm in (rep.get("results") or {}).values() if isinstance(pm, dict)
           for r in pm.values() if isinstance(r, dict)):
        return False

    def nums(x: Any) -> bool:
        if isinstance(x, bool):
            return False
        if isinstance(x, (int, float)):
            return True
        if isinstance(x, dict):
            return any(nums(v) for k, v in x.items() if "score" in str(k).lower() or "acc" in str(k).lower()
                       or isinstance(v, (dict, list)))
        if isinstance(x, list):
            return any(nums(v) for v in x)
        return False

    return nums(rep)


def build_reports(repo: Path | None = None) -> dict[str, str]:
    from apex_one.compute.local import load_catalogue
    from apex_one.compute.registry import load_registry
    from apex_one.vision.council import reliable_judges

    s = get_settings()
    repo = repo or s.home
    art = s.artifacts_dir
    bench = art / "bench"
    evidence = repo / "docs" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for src in (bench / "council_scores.json", bench / "vision_calibration" / "calibration_results.json",
                bench / "apex_design" / "page_compare.json", bench / "queue_state.json",
                bench / "apex_design" / "apex_design_bench.json", bench / "apex_design" / "apex_design_bench_rows.jsonl",
                bench / "design" / "design_bench.json", art / "live" / "provider_live_report.json",
                art / "live" / "local_live_results.json"):
        if src.exists():
            shutil.copy(src, evidence / src.name)
    gdb_runs: dict[str, Any] = {}
    for d in (bench / "gdb").glob("*/report.json") if (bench / "gdb").exists() else []:
        rep = _load(d) or {}
        gdb_runs[d.parent.name] = {"scores": rep, "valid": gdb_report_valid(rep), "summary": json.dumps(rep)[:120]}
        shutil.copy(d, evidence / f"gdb_{d.parent.name}.json")
    _, specs = load_catalogue()
    reg = load_registry()
    rows_path = bench / "apex_design" / "apex_design_bench_rows.jsonl"
    rows = [json.loads(x) for x in rows_path.read_text(encoding="utf-8").splitlines() if x.strip()] if rows_path.exists() else []
    files = {
        "LIVE_PROVIDER_REPORT.md": live_provider_md(_load(art / "live" / "provider_live_report.json")),
        "MODEL_ACTIVATION_REPORT.md": model_activation_md(specs, _load(bench / "council_scores.json"),
                                                          _load(bench / "vision_calibration" / "calibration_results.json"),
                                                          _load(art / "live" / "local_live_results.json"), reg),
        "DESIGN_MODEL_ACTIVATION.md": design_activation_md(
            yaml.safe_load((s.config_dir / "design_activation.yaml").read_text(encoding="utf-8"))["systems"], gdb_runs,
            reliable_judges()[0]) + "\n".join(gdb_md(bench / "gdb")) + "\n",
        "APEX_DESIGN_BENCH.md": design_bench_md(_load(bench / "apex_design" / "apex_design_bench.json"),
                                                list({(r["system"], r["page_type"]): r for r in rows}.values()),
                                                _load(bench / "design" / "design_bench.json"),
                                                _load(bench / "apex_design" / "page_compare.json")),
    }
    runs_path = bench / "council_runs.jsonl"
    runs = [json.loads(x) for x in runs_path.read_text(encoding="utf-8").splitlines() if x.strip()] if runs_path.exists() else []
    files["MODEL_COMPARISON_MATRIX.md"] = model_comparison_md(
        runs, _load(bench / "council_scores.json"), _load(bench / "vision_calibration" / "calibration_results.json"))
    inv_dir = bench / "vision_investigation"
    inv = {p.stem: _load(p) for p in sorted(inv_dir.glob("*.json"))} if inv_dir.exists() else {}
    files["VISION_CALIBRATION_ANALYSIS.md"] = vision_analysis_md(
        inv, _load(bench / "vision_calibration" / "calibration_results.json"), runs)
    robust_dir = bench / "vision_robustness"
    for f in robust_dir.glob("*.json") if robust_dir.exists() else []:
        shutil.copy(f, evidence / f"vision_robustness_{f.name}")
    files["VISION_JUDGE_ROBUSTNESS.md"] = robustness_md(robust_dir, bench / "vision_calibration")
    files["PRODUCTION_ROUTING_MATRIX.md"] = routing_matrix_md(reg, runs)
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    return {k: str(repo / k) for k in files}


# ---------------------------------------------------------------- MODEL_COMPARISON_MATRIX

WINNER_TASKS = [("structured_json", "best structured output"), ("fact_preservation", "best fact preservation"),
                ("egyptian_arabic", "best Egyptian Arabic"), ("html_css", "best HTML/CSS"),
                ("long_context", "best long-context retrieval"), ("design_criticism", "best design criticism"),
                ("visual_hierarchy", "best vision hierarchy (pairwise, single pair)"),
                ("reasoning", "best date reasoning")]


def _hardware() -> str:
    import os

    try:
        mem = int(open("/proc/meminfo").read().split()[1]) / 1e6
    except OSError:
        mem = 0
    return f"{os.cpu_count()} vCPU x86-64, {mem:.1f} GB RAM, no GPU, llama.cpp CPU"


def model_comparison_md(runs: list[dict[str, Any]], scores: dict[str, Any] | None,
                        calibration: dict[str, Any] | None) -> str:
    from apex_one.compute.benchmark.council import STORED_OUTPUT_CHARS, tasks

    defaults = {t.name: (None if t.vision else t.max_tokens) for t in tasks(Path("."))}
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in runs:
        latest[(r["model"], r["task"])] = r
    final = (scores or {}).get("models", {})
    models = sorted({m for m, _ in latest})
    task_names = [t for t, _ in WINNER_TASKS]
    hw = _hardware()
    out = ["# Model Comparison Matrix", "", _stamp(),
           "One row per (model, task). **No overall ranking**: models were measured on different task sets (text-only "
           "models cannot run the vision task; some outputs were empty because the token budget ran out inside hidden "
           "reasoning), so averages across tasks are not comparable. Winners are declared per task, only among models "
           "measured on that same task.", "",
           f"Hardware for every row: {hw}. Checker version: {(scores or {}).get('checker_version', 1)}.", "",
           "| model | task | measured? | score | latency | output complete? | checker | token budget | notes |",
           "|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        for t in task_names:
            r = latest.get((m, t))
            if r is None:
                why = "text-only model: vision task not applicable" if t == "visual_hierarchy" else "not run"
                out.append(f"| {m} | {t} | no | — | — | — | — | — | {why} |")
                continue
            score = final.get(m, {}).get(t, r.get("score"))
            text = r.get("output") or ""
            complete = ("n/a (vision A/B)" if t == "visual_hierarchy" else "EMPTY" if not text.strip() else
                        "truncated in log" if len(text) >= STORED_OUTPUT_CHARS else "yes")
            budget = r.get("max_tokens") or (f"{defaults.get(t)} (task default)" if defaults.get(t) else "60 (A/B)")
            out.append(f"| {m} | {t} | {'yes' if score is not None else 'no'} | {_fmt(score, 0)} | "
                       f"{_fmt(r.get('latency_s'))} s | {complete} | v{r.get('checker_version', 1)} | {budget} | "
                       f"{str(r.get('detail', '')).replace('|', '/')[:90]} |")
    out += ["", "## Task-specific winners (same task, measured models only)", "",
            "| task | winner(s) | score | measured models | not measured |", "|---|---|---|---|---|"]
    for t, label in WINNER_TASKS:
        measured = {m: final.get(m, {}).get(t) for m in models if final.get(m, {}).get(t) is not None}
        missing = [m for m in models if m not in measured]
        if not measured:
            out.append(f"| {label} | none measured | — | — | {', '.join(missing)} |")
            continue
        best = max(measured.values())
        wins = sorted(m for m, v in measured.items() if v == best)
        verdict = ", ".join(wins) if best > 0 else "NO WINNER (every measured model failed)"
        if t == "reasoning":
            verdict += " — production date arithmetic is deterministic (apex_one/core/dates.py) regardless"
        if t == "visual_hierarchy":
            verdict += " — NOT a judge qualification; see calibration below"
        out.append(f"| {label} | {verdict} | {_fmt(best, 0)} | {len(measured)} | {', '.join(missing) or '—'} |")
    out += ["", "## Vision judge qualification (calibration, not benchmark)", ""]
    for section, title in (("models", "absolute six-role council"), ("pairwise_models", "pairwise A/B (both orders)")):
        rows = (calibration or {}).get(section, {})
        if not rows:
            out.append(f"* {title}: not run yet")
            continue
        for mid, r in rows.items():
            n_ok = sum(1 for v in r.get("checks", {}).values() if v)
            out.append(f"* {title} — **{mid}**: {n_ok}/{len(r.get('checks', {}))} cases passed "
                       f"(valid {r.get('valid_checks')}); qualified: **{bool(r.get('reliable'))}**")
    out += ["", "A model enters a quality gate only by passing calibration (≥ 4/5, all cases valid). Benchmark wins "
            "never qualify a judge."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- VISION_CALIBRATION_ANALYSIS

HYPOTHESES = [
    ("different prompting / role-rubric overload", "E0 (six roles, one call) vs E3 (only the targeted role)"),
    ("pair order sensitivity / position bias", "E1 good-as-A vs good-as-B answers"),
    ("scoring schema (absolute scores tie)", "E0 ties_on_target, distinct_scores"),
    ("image scaling", "E1 (640 px) vs E2 (native 794 px; requested 1024, never upscaled)"),
    ("model instability", "E3 vs E4 (identical prompts, temperature 0)"),
    ("output parser", "E0 reviews: parse errors / dropped roles vs raw text"),
    ("context truncation", "E0 raw text ends mid-JSON / missing roles"),
    ("single easy pair vs five cases", "benchmark pair = good vs no_hierarchy only"),
]


def hypothesis_verdicts(rep: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Each suspected cause, judged only from the experiments that isolate it (absent experiment -> NOT TESTED)."""
    def ok(k: str) -> int | None:
        e = rep.get(k)
        return None if not e else e.get("correct")

    rows = []
    e0 = rep.get("E0")
    if e0:
        a0 = sum(1 for v in e0["result"]["checks"].values() if v)
        rows.append(("scoring schema: absolute scores tie", f"ties on targeted role {e0['ties_on_target']}/5, "
                     f"inversions {e0['inversions_on_target']}/5",
                     "CONFIRMED" if e0["ties_on_target"] >= 2 else "not the main cause"))
        rows.append(("model ranks broken pages HIGHER", f"inversions {e0['inversions_on_target']}/5",
                     "CONFIRMED" if e0["inversions_on_target"] >= 2 else "no"))
        errs = sum(1 for r in e0.get("reviews", {}).values() if r.get("errors"))
        rows.append(("output parser / truncation", f"{errs} review(s) with parse/execution errors",
                     "RULED OUT" if errs == 0 else "CONTRIBUTES"))
        if ok("E3") is not None:
            rows.append(("rubric overload (six roles in one call)", f"six-role {a0}/5 vs single-role {ok('E3')}/5",
                         "CONFIRMED (partial)" if ok("E3") > a0 else "RULED OUT"))
    if rep.get("E1"):
        bias = sum(1 for d in rep["E1"]["detail"].values() if d["position_bias"])
        rows.append(("pair-order sensitivity / position bias", f"{bias}/5 cases picked the same POSITION in both orders",
                     "CONFIRMED" if bias >= 3 else "minor" if bias else "RULED OUT"))
        if rep.get("E2"):
            rows.append(("image scaling", f"pairwise 640 px {ok('E1')}/5 vs native 794 px {ok('E2')}/5",
                         "CONFIRMED (helps)" if ok("E2") > ok("E1") else "RULED OUT"))
    if rep.get("E3") and rep.get("E4"):
        same = sum(1 for k in rep["E3"]["cases"] if rep["E3"]["cases"][k]["good"]["score"] ==
                   rep["E4"]["cases"][k]["good"]["score"] and rep["E3"]["cases"][k]["broken"]["score"] ==
                   rep["E4"]["cases"][k]["broken"]["score"])
        rows.append(("model instability (temperature 0)", f"{same}/5 cases identical on repeat",
                     "RULED OUT" if same >= 4 else "CONFIRMED"))
    rows.append(("prompt leakage", "rubric text never contains the case name or the expected answer",
                 "RULED OUT by construction"))
    best = max([v for v in (ok("E1"), ok("E2"), ok("E3"), ok("E4")) if v is not None] +
               [sum(1 for v in e0["result"]["checks"].values() if v)] if e0 else [0])
    rows.append(("qualifies as a judge in ANY tested mode (>= 4/5)", f"best mode {best}/5",
                 "YES" if best >= 4 else "NO — stays out of every gate"))
    return rows


def vision_analysis_md(inv: dict[str, dict[str, Any]], calibration: dict[str, Any] | None,
                       runs: list[dict[str, Any]]) -> str:
    out = ["# Vision Calibration Analysis", "", _stamp(),
           "**Question.** Qwen3-VL 4B scored 100 on the council's visual-hierarchy benchmark but passed only 1/5 "
           "absolute calibration cases. Which is right, and why do they disagree?", "",
           "**Rule kept throughout:** a vision model enters a quality gate only if it passes calibration (≥ 4/5, every "
           "case valid). No bar was lowered; absolute (six-role scoring) and pairwise (A/B) are separate "
           "qualifications measured on the same five cases.", ""]
    bench = [r for r in runs if r["task"] == "visual_hierarchy"]
    if bench:
        out += ["## The benchmark result being questioned", ""]
        for r in bench:
            out.append(f"* {r['model']}: score {r['score']} — {r.get('detail')} (one pair: good vs no_hierarchy)")
        out.append("")
    if not inv:
        return "\n".join(out + ["PENDING: investigation experiments have not run yet "
                                "(scripts/validation_queue.py steps calib/pcalib/invest)."]) + "\n"
    for mid, rep in inv.items():
        out += [f"## {mid}", ""]
        e0 = rep.get("E0")
        if e0:
            res = e0["result"]
            out += [f"**E0 absolute (production protocol):** {sum(1 for v in res['checks'].values() if v)}/5 passed; "
                    f"ties on targeted role: {e0['ties_on_target']}; inversions: {e0['inversions_on_target']}; "
                    f"distinct scores used across all pages/roles: {e0['distinct_scores']}", "",
                    "| case | role | good | broken | pass |", "|---|---|---|---|---|"]
            for k, v in res.get("scores", {}).items():
                out.append(f"| {k} | {v['role']} | {_fmt(v['good'], 0)} | {_fmt(v['broken'], 0)} | {res['checks'][k]} |")
            parse_errors = {p: r.get("errors") for p, r in e0.get("reviews", {}).items() if r.get("errors")}
            out += ["", f"Parser/execution errors: {parse_errors or 'none'}", ""]
        for key, label in (("E1", "pairwise 640 px"), ("E2", "pairwise native 794 px (labelled 1024; never upscaled)")):
            e = rep.get(key)
            if e:
                bias = sum(1 for d in e["detail"].values() if d["position_bias"])
                out += [f"**{key} {label}:** {e['correct']}/5 order-consistent wins; position-biased cases: {bias}",
                        "", "| case | good shown as A → pick | good shown as B → pick | pass |", "|---|---|---|---|"]
                for k, d in e["detail"].items():
                    out.append(f"| {k} | {d['good_as_A']} | {d['good_as_B']} | {e['checks'][k]} |")
                out.append("")
        for key, label in (("E3", "single-role absolute"), ("E4", "single-role repeat")):
            e = rep.get(key)
            if e:
                out += [f"**{key} {label}:** {e['correct']}/{e['valid']} passed", "",
                        "| case | role | good | broken | pass |", "|---|---|---|---|---|"]
                for k, c in e["cases"].items():
                    out.append(f"| {k} | {c['role']} | {_fmt(c['good']['score'], 0)} | {_fmt(c['broken']['score'], 0)} "
                               f"| {c['pass']} |")
                out.append("")
        if rep.get("E3") and rep.get("E4"):
            same = sum(1 for k in rep["E3"]["cases"] if rep["E3"]["cases"][k]["good"]["score"] ==
                       rep["E4"]["cases"][k]["good"]["score"] and rep["E3"]["cases"][k]["broken"]["score"] ==
                       rep["E4"]["cases"][k]["broken"]["score"])
            out += [f"Stability: {same}/5 cases gave identical scores on repeat.", ""]
    out += ["## Hypotheses — verdicts derived from the experiments", "",
            "| model | hypothesis | evidence | verdict |", "|---|---|---|---|"]
    for mid, rep in inv.items():
        for row in hypothesis_verdicts(rep):
            out.append(f"| {mid} | {row[0]} | {row[1]} | **{row[2]}** |")
    out += ["", "| hypothesis | evidence used |", "|---|---|"]
    out += [f"| {h} | {e} |" for h, e in HYPOTHESES]
    out += ["", "## Qualification status", ""]
    for section, title in (("models", "absolute"), ("pairwise_models", "pairwise")):
        for mid, r in ((calibration or {}).get(section) or {}).items():
            out.append(f"* {title} — {mid}: {sum(1 for v in r.get('checks', {}).values() if v)}/5 → "
                       f"**{'QUALIFIED' if r.get('reliable') else 'NOT QUALIFIED'}**")
    from apex_one.vision.council import reliable_judges

    absolute, pairwise = reliable_judges()[0], reliable_judges(mode="pairwise")[0]
    out += ["", "## What the gates may use (re-checked: bar, timestamp, model digest)", "",
            f"* six-role scoring council (absolute): {', '.join(absolute) if absolute else 'none'} → "
            + ("Vision Council scores ACTIVE" if absolute else "**Vision Quality scores = NOT_MEASURED**"),
            f"* finalist A/B judging (pairwise, both orders): {', '.join(pairwise) if pairwise else 'none'} → "
            + ("pairwise finalist votes ACTIVE (a vote counts only when both orders agree)" if pairwise
               else "pairwise judging NOT_MEASURED"),
            "* a pass in one mode never qualifies the other; deterministic DOM gates remain authoritative"]
    return "\n".join(out) + "\n"


# A text-output vision model (text + image in -> text out) cannot produce image/video outputs or read video input.
_GDB_UNSUPPORTED_OUT = re.compile(r"^(rendered layout image|composited layout|generated video|generated image|"
                                  r"layout image with)", re.I)
_GDB_UNSUPPORTED_IN = re.compile(r"\bvideo\b|\bMP4\b", re.I)


def gdb_task_states(runs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every registered GDB task -> MEASURED (ran here) / UNSUPPORTED (modality) / SKIPPED (data unreachable).
    Unsupported and skipped tasks are never scored, never zero, never a pass."""
    try:
        from gdb.registry import BenchmarkRegistry

        reg = BenchmarkRegistry()
        reg.discover()
        metas = {b.meta.id: b.meta for b in (reg.list() if hasattr(reg, "list") else reg.all())}
    except Exception:  # noqa: BLE001
        metas = {}
    ran = {t for res, _ in runs.values() for t in res}
    out = {}
    for tid, m in sorted(metas.items()):
        if tid in ran:
            st, why = "MEASURED", "ran on the offline verification bundle"
        elif _GDB_UNSUPPORTED_OUT.search(m.output_spec.strip()) or _GDB_UNSUPPORTED_IN.search(m.input_spec):
            st, why = "UNSUPPORTED", f"needs {'video input' if _GDB_UNSUPPORTED_IN.search(m.input_spec) else 'image/video output'} — the local models are text-output VLMs"
        else:
            st, why = "SKIPPED", "data lives on the Hugging Face Hub (egress-denied); model support NOT determined"
        out[tid] = {"state": st, "why": why, "type": getattr(m.task_type, "value", str(m.task_type)),
                    "in": m.input_spec, "out": m.output_spec}
    return out


def gdb_md(gdb_dir: Path) -> list[str]:
    """What GraphicDesignBench actually ran — per model, per task — and what was unsupported or skipped and why."""
    import importlib.metadata

    from apex_one.lab.benchmarks.gdb_provider import GDB_PREPROCESS
    from apex_one.vision.council import model_digest

    runs = {}
    for rep in sorted(gdb_dir.glob("*/report.json")) if gdb_dir.exists() else []:
        if rep.parent.name.startswith("_"):
            continue
        runs[rep.parent.name] = ((_load(rep) or {}).get("results", {}), _load(rep.parent / "run_meta.json") or {})
    states = gdb_task_states(runs)
    try:
        version = importlib.metadata.version("lica-gdb")
    except Exception:  # noqa: BLE001
        version = "unknown"
    count = lambda st: sum(1 for v in states.values() if v["state"] == st)  # noqa: E731
    out = ["## GraphicDesignBench (lica-gdb) — real runs", "",
           f"`lica-gdb` {version}, suite `v0-smoke` (GDB's definitions are still `v0`, i.e. not frozen). Image inputs: "
           f"{GDB_PREPROCESS}. Registered tasks: {len(states)} → **MEASURED {count('MEASURED')}**, "
           f"**UNSUPPORTED {count('UNSUPPORTED')}** (modality), **SKIPPED {count('SKIPPED')}** (data unreachable). "
           "Unsupported and skipped tasks are NOT scored — not zero, not a pass.", "",
           "The offline verification bundle ships **2 samples per task**, so every score below is an n=2 smoke "
           "measurement — it proves a real model runs end-to-end; it is far too small to rank models.", "",
           "| run | model | model digest | exit | runtime | task | n | ok | failed | scores |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for name, (res, meta) in runs.items():
        mid = meta.get("model", "—")
        dig = meta.get("model_digest") or (model_digest(mid) and f"{model_digest(mid)[:19]}… (read at report time)") or "—"
        for task, per_model in sorted(res.items()):
            for _, r in per_model.items():
                sc = ", ".join(f"{k}={v:.2f}" for k, v in (r.get("scores") or {}).items() if isinstance(v, (int, float)))
                if r.get("failure_count"):     # failed samples were scored by GDB as empty answers: not a measurement
                    sc = f"NOT_MEASURED — {r['failure_count']}/{r.get('count')} samples failed (GDB's score withheld)"
                out.append(f"| {name} | {mid} | {dig} | {meta.get('exit_code', '—')} | {meta.get('runtime_s', '—')} s | "
                           f"{task} | {r.get('count')} | {r.get('success_count')} | {r.get('failure_count')} | {sc or '—'} |")
    out += ["", "Raw per-sample outputs: `artifacts/bench/gdb/<run>/` (GDB `outputs/`, `gdb.log`, `report.json`); "
            "reports copied to `docs/evidence/gdb_<run>.json`.", "",
            "### Every registered task", "", "| task | type | state | why | input | output |", "|---|---|---|---|---|---|"]
    for tid, v in states.items():
        out.append(f"| {tid} | {v['type']} | {v['state']} | {v['why']} | {v['in'][:60]} | {v['out'][:60]} |")
    return out + [""]


# ---------------------------------------------------------------- VISION_JUDGE_ROBUSTNESS

def robustness_md(robust_dir: Path, calib_dir: Path) -> str:
    from apex_one.lab.benchmarks.vision_robustness import REPEATS, WIDTHS, load, status, summarize_width
    from apex_one.vision.council import PREPROCESS_VERSION
    from apex_one.vision.pairwise import CALIBRATED_MAX_W

    try:
        from apex_one.lab.benchmarks.vision_robustness import min_font_px, native_width

        native, min_font = native_width(calib_dir), min_font_px(calib_dir)
    except Exception:  # noqa: BLE001
        native, min_font = 794, None
    out = ["# Vision judge robustness", "", _stamp(),
           "Does a pairwise judge's calibration survive a change of input resolution? Same five calibration cases "
           f"(good page vs each deliberately broken variant), both orders, {REPEATS} repeats per width.", "",
           "## Judge-input contract (canonical normalized input)", "",
           f"* **canonical judge width: {CALIBRATED_MAX_W} px** — `PairwiseJudge` default (`CALIBRATED_MAX_W`); "
           "production finalist judging and calibration call the SAME `PairwiseJudge.compare` → `encode_png` → "
           "`normalize_for_judge` path",
           f"* preprocessing `{PREPROCESS_VERSION}`: width-bound (every candidate scaled to the same width, so two "
           "pages of different heights share one scale), aspect ratio preserved, never capped by height, Pillow "
           "default bicubic resampling; each input's sha256 is stored with every result",
           f"* native render: {native} px wide (A4 at device scale 1). Widths above native are RE-RENDERED at "
           "device scale width/native — never upscaled",
           f"* smallest text on the calibration page: {_fmt(min_font, 0)} CSS px → effective "
           + ", ".join(f"{w} px: {min_font * w / native:.1f} px" for w in (320, 480, 640, 768) if min_font)
           + " (legibility is measured directly by the probe below, not assumed)",
           "* confidence = consistency across the 2 × repeats answers per case, |2p − 1| (the judge is not asked to "
           "self-report confidence, so the calibrated prompt is unchanged)",
           "* judging runs at temperature 0 (as in production), so repeats measure DETERMINISM of the serving stack, "
           "not sampling variance: identical repeats (variance 0, confidence 1.0) mean the verdict is reproducible, "
           "not that it is right — accuracy and the per-case results carry that",
           "* correction: the earlier investigation experiment labelled “E2 1024 px” actually ran at the native "
           f"{native} px — `thumbnail()` never upscales. The sweep below renders a real 1024 px input.", "",
           "Pre-registered rules (`apex_one/lab/benchmarks/vision_robustness.py`, fixed before results): reliable at a "
           "width = every repeat all-valid and ≥ 4/5; legible = both probe facts read exactly; ROBUSTLY_CALIBRATED = "
           "reliable at every legible width and legible at canonical, native and 1024; CANONICAL_640_ONLY = reliable "
           "and legible at 640 only; UNQUALIFIED = not reliable or not legible at 640.", ""]
    models = sorted(p.stem for p in robust_dir.glob("*.json")) if robust_dir.exists() else []
    if not models:
        out += ["_No robustness results yet._", ""]
    for mid in models:
        data = load(mid, robust_dir) or {}
        st, why = status(data)
        out += [f"## {mid} — **{st}**", "", f"{why}. Model digest `{(data.get('model_digest') or '—')[:19]}…`.", "",
                "| width | input | repeats | correct per repeat | accuracy | order sensitivity | run variance | "
                "cases flipping | always wrong | confidence | median call latency | legible (deadline / tuition) | reliable | input hash (good) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for wkey in WIDTHS:
            w = data.get("widths", {}).get(wkey)
            if not w:
                out.append(f"| {wkey} | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |")
                continue
            s = summarize_width(w)
            if not s.get("repeats"):
                out.append(f"| {wkey} | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |")
                continue
            rd = s.get("legibility_read") or {}
            leg = "—" if s["legible"] is None else (f"{'yes' if s['legible'] else 'NO'} "
                                                   f"({rd.get('application_deadline')} / {rd.get('tuition_coverage')})")
            out.append(f"| {wkey} ({s['width']} px) | {s['inputs']} | {s['repeats']} | {s['correct_per_repeat']} | "
                       f"{s['accuracy']:.2f} | {s['order_sensitivity']:.2f} ({s['position_bias_cases']} case-runs) | "
                       f"{s['run_variance']} | {', '.join(s['cases_flipping_across_repeats']) or '—'} | "
                       f"{', '.join(s['cases_failed_every_repeat']) or '—'} | "
                       f"{_fmt(s['confidence_mean'], 2)} | {_fmt(s['median_call_latency_s'])} s | {leg} | "
                       f"{'yes' if s['reliable_all_repeats'] else 'NO'} | `{(s['input_hash_good'] or '')[:12]}` |")
        out += ["", "Raw answers, per-call latency and every input hash: `docs/evidence/vision_robustness_"
                f"{mid}.json`.", ""]
        if st == "CANONICAL_640_ONLY":
            out += [f"**Limitation (stays visible):** {mid} is calibrated ONLY for the canonical {CALIBRATED_MAX_W} px "
                    "normalized input. It is not a general-purpose vision judge; at other resolutions its verdicts are "
                    "not trusted. Production uses it only for order-swapped finalist A/B judging at "
                    f"{CALIBRATED_MAX_W} px, and the deterministic DOM gates stay authoritative.", ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- PRODUCTION_ROUTING_MATRIX

def routing_matrix_md(reg, runs: list[dict[str, Any]]) -> str:
    from apex_one.compute.local import load_catalogue
    from apex_one.compute.router.capability import (
        rejection,
        required_scores,
        routing_config,
        task_evidence_score,
    )
    from apex_one.vision.council import judge_status, reliable_judges

    cfg = routing_config()
    caps, rules = cfg.get("capabilities", {}), cfg.get("tasks", {})
    floor = cfg.get("default_min_score", 50)
    measured = sorted((m for m in reg.models.values() if m.benchmark_scores), key=lambda m: m.id)
    _, specs = load_catalogue()
    installed = {s.registry_model for s in specs.values() if (s.dir / "apex_manifest.json").exists()}
    lat: dict[tuple[str, str], float] = {}
    for r in runs:
        if r.get("latency_s") is not None:
            lat[(r["model"], r["task"])] = r["latency_s"]
    out = ["# Production routing matrix", "", _stamp(),
           "Built ONLY from measured evidence (`artifacts/bench/council_scores.json`, checker v2) and licence records. "
           "No global best model, no cross-task average. A task's score is the weakest of the capabilities it "
           f"REQUIRES; a model measured below the floor ({floor}, pre-registered) on any of them is rejected. "
           "**Primary / fallback must also be production-licensed and installed**; the best evaluation-only model is "
           "shown separately. Ties are broken by measured latency on the same evidence tasks (lower first).", "",
           "## Rules", "",
           "* **date arithmetic: DETERMINISTIC ENGINE ONLY** (`apex_one/core/dates.py`). The $0 firewall refuses "
           "every `date.*` task for every model. A model may EXPLAIN a date that code computed; it never computes "
           "one. Regression case: latest Saturday before a 1 Nov 2026 deadline with 10-day results = 2026-10-17.",
           "* layout: APEX native engines; repair: native failure-specific repair; SVG: vector specialist when "
           "reachable, else native SVG assets",
           "* vision: only judges that passed calibration in that mode (see below)", "",
           "## Capability vector (measured, per model — bad results stay visible)", "",
           "| capability | evidence task | " + " | ".join(m.id for m in measured) + " |",
           "|---|---|" + "---|" * len(measured)]
    for cap, ev in caps.items():
        out.append(f"| {cap} | {ev} | " + " | ".join(_fmt(m.benchmark_scores.get(ev), 0) if m.benchmark_scores.get(ev)
                                                     is not None else "NOT_MEASURED" for m in measured) + " |")
    out += ["", "| model | production licence | weights installed |", "|---|---|---|"]
    for m in measured:
        out.append(f"| {m.id} | {'ALLOWED' if reg.production_allowed(m) else 'BLOCKED'} | "
                   f"{'yes' if m.id in installed else 'no'} |")
    out += ["", "## Per-task routing", "",
            "| task | requires (mandatory) | primary | fallback | best evaluation-only (licence-blocked) | rejected (below floor) | unmeasured |",
            "|---|---|---|---|---|---|---|"]
    for task, rule in rules.items():
        if "requires" not in rule:
            continue
        scored, rejected, unmeasured = [], [], []
        for m in measured:
            sc = task_evidence_score(m, task)
            if rejection(m, task):
                low = {c: v for c, v in required_scores(m, task).items() if v is not None and v < floor}
                rejected.append(f"{m.id} ({', '.join(f'{caps.get(c, c)}={_fmt(v, 0)}' for c, v in low.items())})")
            elif sc is None:
                unmeasured.append(m.id)
            else:
                t = sum(lat.get((m.id, caps.get(c, c)), 0.0) for c in rule["requires"])
                scored.append((sc, t, m))
        scored.sort(key=lambda x: (-x[0], x[1], x[2].id))
        prod = [x for x in scored if reg.production_allowed(x[2]) and x[2].id in installed]
        evalonly = [x for x in scored if x not in prod]
        cell = lambda x: f"{x[2].id} ({_fmt(x[0], 0)}, {x[1]:.0f} s)" if x else "—"  # noqa: E731
        from apex_one.compute.router.fallback import has_native_fallback

        none = "NONE passes → APEX native engine" if has_native_fallback(task) else "NONE passes → task blocked"
        out.append(f"| {task} | {', '.join(rule['requires'])} | {cell(prod[0]) if prod else none} | "
                   f"{cell(prod[1] if len(prod) > 1 else None)} | {cell(evalonly[0] if evalonly else None)} | "
                   f"{'; '.join(rejected) or '—'} | {', '.join(unmeasured) or '—'} |")
    pw = reliable_judges(mode="pairwise")
    ab = reliable_judges()[0]
    out += ["", "## Vision", "",
            f"* scoring council (absolute): {', '.join(ab) or 'none qualified'} → "
            + ("ACTIVE" if ab else "**Vision Quality scores = NOT_MEASURED**"),
            f"* finalist A/B (pairwise, canonical input only): {', '.join(pw[0]) or 'none admitted'}"]
    for mid, r in (pw[1] or {}).items():
        st, why = judge_status(mid)
        out.append(f"  * {mid}: robustness **{st}** ({why}); "
                   + ("ADMITTED" if mid in pw[0] else f"not admitted — {r.get('rejected', 'calibration not reliable')}"))
    out += ["", "## Remote models", "",
            "Remote free-tier routes were never measured here (provider hosts are network-blocked from this "
            "environment), so they appear in no primary/fallback cell. They stay routable only through the runtime "
            "prior, below every measured model, and are reported as unmeasured.", ""]
    return "\n".join(out) + "\n"
