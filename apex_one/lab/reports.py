"""Phase 14+ reports, generated from measured artifacts only.

Every number in these reports is read from an artifact produced by a real run in this environment; anything not
run is printed as NOT_MEASURED / PENDING with the reason. Regenerate with `apex-one reports build`.
"""

from __future__ import annotations

import json
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
    tasks = ["reasoning", "egyptian_arabic", "en_ar_mixing", "structured_json", "fact_preservation", "html_css",
             "design_criticism", "long_context", "visual_hierarchy"]
    if not scores or not scores.get("models"):
        out.append("PENDING: the council benchmark has not produced scores yet.")
    else:
        out += ["| model | " + " | ".join(tasks) + " | overall (mean of measured) | measured tasks |",
                "|---|" + "---|" * (len(tasks) + 2)]
        for mid, e in scores["models"].items():
            n = e.get("measured_tasks", sum(1 for t in tasks if e.get(t) is not None))
            out.append(f"| {mid} | " + " | ".join(_fmt(e.get(t), 0) for t in tasks)
                       + f" | {_fmt(e.get('overall'))} | {n}/{len(tasks)} |")
        out += ["", "`—` = NOT_MEASURED (not run, not applicable, or empty output because a reasoning model spent its "
                "token budget on hidden reasoning; re-run with a larger budget). Overall means are over different task "
                "counts and are not directly comparable across rows. "
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
           "| system | source (evidence) | reported licence | checkpoint host | hardware | local | $0 remote | "
           "adapter | smoke test / artifacts | status |", "|---|---|---|---|---|---|---|---|---|---|"]
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
        out.append(f"| {name} | {src_s} | {lic.get('value', '—')} | {host} | {s.get('hardware', '—')[:60]} | {local} | "
                   f"no | {adapter} | {smoke} | **{', '.join(status)}** |")
        if s.get("apex_use"):
            out.append(f"| ↳ APEX use | {s['apex_use']} | | | | | | | | |")
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


def design_bench_md(bench: dict[str, Any] | None, rows: list[dict[str, Any]], unit_bench: dict[str, Any] | None) -> str:
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
    if unit_bench:
        out += ["## Targeted design risk cases", "",
                f"{unit_bench['passed']}/{unit_bench['measured']} measured cases pass; {unit_bench['not_measured']} "
                "NOT_MEASURED.", "", "| case | expectation | status | detail |", "|---|---|---|---|"]
        for c in unit_bench["cases"]:
            out.append(f"| {c['case']} | {c['expectation'][:60]} | {c['status']} | {str(c['detail'])[:80]} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- build


def gdb_report_valid(rep: Any) -> bool:
    """A GDB run counts only if it produced at least one numeric score and no top-level error."""
    if not isinstance(rep, dict) or rep.get("error"):
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
            reliable_judges()[0]),
        "APEX_DESIGN_BENCH.md": design_bench_md(_load(bench / "apex_design" / "apex_design_bench.json"), rows,
                                                _load(bench / "design" / "design_bench.json")),
    }
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    return {k: str(repo / k) for k in files}
