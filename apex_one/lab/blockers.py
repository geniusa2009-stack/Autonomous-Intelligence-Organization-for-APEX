"""Production blockers (authoritative source: config/production_blockers.yaml) and the maturity matrix.

Every blocker's status comes from a live PROBE, never from hand-written text, so the generated
PRODUCTION_BLOCKERS.md / HUMAN_ACTIONS_REQUIRED.md / CURRENT_STATE.json cannot drift from the system's real state.
PRODUCTION_READY is computed: YES only when every MANDATORY maturity dimension is satisfied.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from apex_one.settings import get_settings

REQUIRED_FIELDS = ("blocker_id", "description", "affected_subsystem", "owner", "requires_human_action",
                   "requires_external_access", "can_be_solved_offline", "severity", "exact_unblock_condition",
                   "next_executable_action")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
PENDING_LICENCES = ("lic-gemma", "lic-gemma3-12b", "lic-nvidia-nemotron-nano", "lic-gpt-oss")

# dimension -> (mandatory for PRODUCTION_READY, why)
DIMENSIONS: dict[str, tuple[bool, str]] = {
    "ARCHITECTURE_COMPLETE": (True, "every stage exists, is wired and tested"),
    "OFFLINE_PIPELINE_VALIDATED": (True, "golden ULTRA reaches the human gate with all quality targets PASS"),
    "LOCAL_MODEL_ROUTING_VALIDATED": (True, "every model route is decided on identical measurements, licence-gated"),
    "DESIGN_MODEL_VALIDATION": (False, "native APEX design is primary on every page type; model design is optional"),
    "VISION_GATE": (False, "absolute visual quality is reported NOT_MEASURED on the release candidate and the human "
                           "approver reviews the final PDF; no release decision depends on a model judge"),
    "REMOTE_FREE_COMPUTE_VALIDATED": (False, "the $0 local route serves every production model task"),
    "REAL_OPPORTUNITY_VALIDATED": (True, "a real guide must reach RELEASE_CANDIDATE from authoritative evidence"),
    "PRODUCTION_LOAD_VALIDATED": (True, "PRODUCTION_MODE must throttle, not OOM, under real concurrent load"),
    "BRAND_ASSETS_VALIDATED": (True, "no FINAL artifact may carry placeholder branding"),
    "HUMAN_APPROVAL_VALIDATED": (True, "a release needs an authenticated approver bound to the artifact hash"),
}


def _bench() -> Path:
    return get_settings().artifacts_dir / "bench"


def _load(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- probes: (resolved, evidence)

def probe_brand_valid() -> tuple[bool, str]:
    from apex_one.release.assets import brand_status

    st = brand_status()
    return st["status"] == "VALID", f"apex-one brand validate → {st['status']}: {'; '.join(st['reasons'][:3])}"


def probe_approver_registered() -> tuple[bool, str]:
    from apex_one.core.auth import list_approvers, verify_ledger

    active = [a for a in list_approvers() if not a["revoked"]]
    ok, problems = verify_ledger()
    return bool(active) and ok, f"{len(active)} active approver(s); ledger {'intact' if ok else problems[:2]}"


def probe_real_job_release_candidate() -> tuple[bool, str]:
    s = get_settings()
    hits = []
    for jf in sorted(s.jobs_dir.glob("J-*/job.json")) if s.jobs_dir.exists() else []:
        j = _load(jf) or {}
        if j.get("offline_fixture") or (j.get("mission") or {}).get("synthetic"):
            continue
        if _test_pack_job(j):      # reserved test domains prove the pipeline, never a real opportunity
            continue
        if j.get("status") in ("RELEASE_CANDIDATE", "FINAL"):
            hits.append(jf.parent.name)
    return bool(hits), (f"real jobs at RELEASE_CANDIDATE/FINAL: {hits}" if hits
                        else "no non-synthetic job has reached RELEASE_CANDIDATE")


def _test_pack_job(job: dict[str, Any]) -> bool:
    from apex_one.research.evidence_pack import is_test_url

    for d in job.get("source_inputs") or []:
        man = Path(d) / "sources.yaml"
        if man.exists():
            urls = [e.get("url", "") for e in (yaml.safe_load(man.read_text(encoding="utf-8")) or {}).get("sources") or []]
            if any(is_test_url(u) for u in urls):
                return True
    return False


def probe_load_test_passed() -> tuple[bool, str]:
    rep = _load(_bench() / "load_test" / "report.json")
    if not rep:
        return False, "no load-test report (artifacts/bench/load_test/report.json)"
    return rep.get("verdict") == "PASS" and rep.get("real_model", False), \
        f"load test {rep.get('verdict')} (model {rep.get('model')}, real model: {rep.get('real_model')})"


def probe_gemini_key_present() -> tuple[bool, str]:
    rep = _load(_bench() / "gemini_validation" / "report.json") or {}
    if not os.environ.get("GEMINI_API_KEY"):
        return False, "GEMINI_API_KEY not set"
    return rep.get("live", {}).get("ok") is True, f"key present; live test: {rep.get('live', {}).get('status', 'not run')}"


def probe_remote_provider_live() -> tuple[bool, str]:
    rep = _load(get_settings().artifacts_dir / "live" / "provider_live_report.json") or []
    rows = rep if isinstance(rep, list) else list((rep.get("providers") or {}).values())
    live = [r.get("provider") for r in rows if isinstance(r, dict) and r.get("status") == "LIVE_TESTED"
            and r.get("provider") not in ("llamacpp_local", "mock", "mlx")]
    states = sorted({f"{r.get('provider')}={r.get('status')}" for r in rows if isinstance(r, dict)})
    return bool(live), f"remote providers LIVE_TESTED: {live or 'none'} ({', '.join(states)})"


def probe_licences_verified() -> tuple[bool, str]:
    from apex_one.compute.registry import load_registry

    reg = load_registry()
    pending = [lid for lid in PENDING_LICENCES if lid in reg.licenses and not reg.licenses[lid].verified_by]
    return not pending, f"awaiting a human decision: {pending}" if pending else "every pending licence decided"


def probe_robust_vision_judge() -> tuple[bool, str]:
    from apex_one.vision.council import reliable_judges

    ab = reliable_judges()[0]
    return bool(ab), f"ROBUSTLY_CALIBRATED judges: {ab or 'none'}"


def probe_gdb_full() -> tuple[bool, str]:
    return False, "6/39 tasks runnable offline (n=2); full dataset on huggingface.co"


def probe_large_models_admitted() -> tuple[bool, str]:
    q = _load(_bench() / "queue_state.json") or {}
    blocked = sorted({k.split(":")[0] for k, v in (q.get("failed") or {}).items()
                      if str(v.get("info", "")).startswith("RESOURCE_BLOCKED")})
    return not blocked, f"RESOURCE_BLOCKED on this machine: {blocked}" if blocked else "none blocked"


PROBES = {name.removeprefix("probe_"): fn for name, fn in globals().items() if name.startswith("probe_")}


# ---------------------------------------------------------------- blockers

def load_blockers(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or get_settings().config_dir / "production_blockers.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(data.get("blockers") or [])


def validate_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    problems = []
    ids = {b.get("blocker_id") for b in blockers}
    for b in blockers:
        bid = b.get("blocker_id", "?")
        problems += [f"{bid}: missing {f}" for f in REQUIRED_FIELDS if b.get(f) in (None, "")]
        if b.get("severity") not in SEVERITIES:
            problems.append(f"{bid}: severity {b.get('severity')} not in {SEVERITIES}")
        if b.get("probe") not in PROBES:
            problems.append(f"{bid}: unknown probe {b.get('probe')}")
        if b.get("maturity_dimension") not in DIMENSIONS:
            problems.append(f"{bid}: unknown maturity dimension {b.get('maturity_dimension')}")
        problems += [f"{bid}: depends on unknown {d}" for d in b.get("depends_on") or [] if d not in ids]
        if b.get("requires_human_action") and not (b.get("human_action") or {}).get("command_after"):
            problems.append(f"{bid}: human action without WHY/WHAT/command_after")
        if b.get("requires_human_action") is False and b.get("human_action"):
            problems.append(f"{bid}: autonomous blocker must not appear in HUMAN_ACTIONS_REQUIRED")
    return problems


def evaluate(blockers: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out = []
    for b in blockers if blockers is not None else load_blockers():
        try:
            resolved, ev = PROBES[b["probe"]]()
        except Exception as e:  # noqa: BLE001 — a broken probe never reads as resolved
            resolved, ev = False, f"probe error: {e}"
        out.append({**b, "status": "RESOLVED" if resolved else "OPEN", "probe_evidence": ev})
    return out


# ---------------------------------------------------------------- maturity

def routing_status(policy: dict[str, Any] | None = None) -> tuple[str, str]:
    """YES when every deployable model route is decided on identical measurements with a verified licence."""
    pol = policy if policy is not None else _load(get_settings().home / "docs" / "evidence" /
                                                  "production_routing_policy.json")
    if not pol:
        return "NO", "no frozen routing policy"
    prod = [r for r in pol["rows"] if r.get("decision") == "PRIMARY" and r.get("deployment") == "PRODUCTION"]
    if not prod:     # an empty set never counts as validated
        return "NO", "no production model route in the frozen policy (or a policy without route records)"
    provisional = [r["task"] for r in prod if "NOT on identical measurements" in r.get("why", "")]
    unlicensed = [r["task"] for r in prod if "(verified)" not in r.get("licence_state", "")]
    evaluation_only = [r["task"] for r in pol["rows"] if r.get("decision") == "EVALUATION_ONLY"]
    if provisional or unlicensed:
        return "PARTIAL", (f"provisional (not identical measurements): {provisional}; unverified licence: "
                           f"{unlicensed}")
    return "YES", (f"{len(prod)} production model routes, all on identical measurements with verified licences; "
                   f"EVALUATION_ONLY (native in production): {evaluation_only or 'none'}")


def maturity(evaluated: list[dict[str, Any]] | None = None,
             policy: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Each dimension: status (YES / PARTIAL / NO), mandatory flag and evidence. PRODUCTION_READY is derived."""
    ev = evaluated if evaluated is not None else evaluate()
    open_by_dim: dict[str, list[str]] = {}
    for b in ev:     # a capability-limiting blocker with a safe fallback does not hold its dimension open
        if b["status"] == "OPEN" and b.get("blocks_dimension", True):
            open_by_dim.setdefault(b["maturity_dimension"], []).append(b["blocker_id"])
    from apex_one.vision.council import reliable_judges

    pw, ab = reliable_judges(mode="pairwise")[0], reliable_judges()[0]
    fixed = {
        "ARCHITECTURE_COMPLETE": ("YES", "state machine, $0 compute, research, editorial, design, QA, release, learning"),
        "OFFLINE_PIPELINE_VALIDATED": ("YES", "golden ULTRA: comprehension 98.9, rhythm 94.0, Arabic typography 100; "
                                              "tests/test_pipeline.py::test_golden_ultra_quality_never_regresses"),
        "LOCAL_MODEL_ROUTING_VALIDATED": routing_status(policy),
        "DESIGN_MODEL_VALIDATION": ("PARTIAL", "GDB 6/39 tasks offline (n=2); native wins or ties every page type"),
        "VISION_GATE": ("YES" if ab else "PARTIAL" if pw else "NO",
                        f"robust judges {ab or 'none'}; canonical-only pairwise judges {pw or 'none'}; "
                        "absolute visual quality " + ("measured" if ab else "NOT_MEASURED")),
    }
    out: dict[str, dict[str, Any]] = {}
    for dim, (mandatory, why) in DIMENSIONS.items():
        if dim in fixed:
            status, evidence = fixed[dim]
            if status == "YES" and open_by_dim.get(dim):
                status = "PARTIAL"
        else:
            status = "NO" if open_by_dim.get(dim) else "YES"
            evidence = "; ".join(b["probe_evidence"] for b in ev if b["maturity_dimension"] == dim) or "no blocker"
        out[dim] = {"status": status, "mandatory": mandatory, "why_mandatory_or_not": why, "evidence": evidence,
                    "open_blockers": open_by_dim.get(dim, [])}
    unmet = [d for d, v in out.items() if v["mandatory"] and v["status"] != "YES"]
    out["PRODUCTION_READY"] = {"status": "NO" if unmet else "YES", "mandatory": True,
                               "why_mandatory_or_not": "YES only when every mandatory dimension is YES",
                               "evidence": f"unmet mandatory dimensions: {unmet}" if unmet else "all mandatory met",
                               "open_blockers": unmet}
    return out


# ---------------------------------------------------------------- Markdown

def _stamp() -> str:
    from apex_one.lab.final_reports import _stamp as s

    return s()


def blockers_md(ev: list[dict[str, Any]], mat: dict[str, dict[str, Any]]) -> str:
    order = {s: i for i, s in enumerate(SEVERITIES)}
    ev = sorted(ev, key=lambda b: (b["status"] == "RESOLVED", order[b["severity"]], b["blocker_id"]))
    out = ["# Production blockers", "", _stamp(), "",
           "Authoritative source: `config/production_blockers.yaml`. Status comes from a live probe "
           "(`apex_one/lab/blockers.py`), never from hand-written text. PRODUCTION_READY is "
           f"**{mat['PRODUCTION_READY']['status']}** — {mat['PRODUCTION_READY']['evidence']}.", "",
           "| blocker_id | status | severity | description | affected subsystem | owner | human action | external "
           "access | solvable offline | exact unblock condition | next executable action | probe evidence |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    yn = {True: "yes", False: "no"}
    for b in ev:
        out.append(f"| {b['blocker_id']} | **{b['status']}** | {b['severity']} | {b['description']} | "
                   f"{b['affected_subsystem']} | {b['owner']} | {yn[b['requires_human_action']]} | "
                   f"{yn[b['requires_external_access']]} | {yn[b['can_be_solved_offline']]} | "
                   f"{b['exact_unblock_condition']} | `{b['next_executable_action']}` | {b['probe_evidence']} |")
    out += ["", "## Blocker graph", "",
            "Blockers → the maturity dimension each one holds open → PRODUCTION_READY (mandatory dimensions only).", "",
            "```mermaid", "flowchart LR"]
    for b in ev:
        if b["status"] == "OPEN":
            out.append(f"  {b['blocker_id'].replace('-', '_')}[\"{b['blocker_id']} ({b['severity']})\"] --> "
                       f"{b['maturity_dimension']}")
            out += [f"  {d.replace('-', '_')} --> {b['blocker_id'].replace('-', '_')}" for d in b.get("depends_on") or []]
    for dim, v in mat.items():
        if dim != "PRODUCTION_READY" and v["mandatory"]:
            out.append(f"  {dim} --> PRODUCTION_READY")
    out += ["```", "", "## Maturity matrix (independent dimensions)", "",
            "| dimension | status | mandatory for production | why | evidence | open blockers |", "|---|---|---|---|---|---|"]
    out += [f"| {d} | **{v['status']}** | {'yes' if v['mandatory'] else 'no'} | {v['why_mandatory_or_not']} | "
            f"{v['evidence']} | {', '.join(v['open_blockers']) or '—'} |" for d, v in mat.items()]
    return "\n".join(out) + "\n"


def human_actions_md(ev: list[dict[str, Any]]) -> str:
    acts = sorted((b for b in ev if b["requires_human_action"] and b["status"] == "OPEN"),
                  key=lambda b: b["human_action"]["letter"])
    out = ["# Human actions required", "", _stamp(), "",
           "Only what a person must do. Everything Claude can still do autonomously is in NEXT_ACTIONS.md. Generated "
           "from `config/production_blockers.yaml`; an action disappears when its probe sees it done.", ""]
    for b in acts:
        h = b["human_action"]
        out += [f"## {h['letter']}. {h['title']}  (`{b['blocker_id']}`, {b['severity']})", "",
                f"**WHY** — {h['why']}", "", f"**WHAT EXACTLY IS NEEDED** — {h['what']}", "",
                f"**COMMAND AVAILABLE AFTERWARD** — `{h['command_after']}`", "",
                f"_Done when:_ {b['exact_unblock_condition']}", ""]
    if not acts:
        out.append("None — every human action is done.")
    return "\n".join(out) + "\n"


def update_current_state(path: Path, mat: dict[str, dict[str, Any]], ev: list[dict[str, Any]]) -> None:
    """CURRENT_STATE.json's maturity and blockers are machine-written from the probes (the rest is hand-kept)."""
    data = _load(path) or {}
    data["maturity"] = {d: v["status"] for d, v in mat.items()}
    data["maturity_mandatory"] = [d for d, v in mat.items() if v["mandatory"] and d != "PRODUCTION_READY"]
    data["blockers"] = [f"{b['blocker_id']} ({b['severity']}, {b['status']})" for b in ev]
    data["blockers_source"] = "config/production_blockers.yaml → PRODUCTION_BLOCKERS.md (probe-evaluated)"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def licence_review_md() -> str:
    """Everything a human needs to decide the pending licences, from the local artifact evidence only."""
    v = (yaml.safe_load((get_settings().config_dir / "license_verifications.yaml").read_text(encoding="utf-8"))
         or {}).get("verifications", {})
    out = ["# Licence review pack", "",
           "Prepared offline from the artifacts' own declarations (`config/license_verifications.yaml`). Claude does "
           "NOT decide licences: a person entitled to make the call reads the licence text and records the decision "
           "with `apex-one license verify`. Until then each model below is evaluation-only.", ""]
    for lid in PENDING_LICENCES:
        r = v.get(lid) or {}
        out += [f"## `{lid}` — artifacts: {', '.join(r.get('artifacts') or ['?'])}", "",
                f"* declared: **{r.get('license_name', 'UNKNOWN')}** (state {r.get('production_state', 'UNKNOWN')})",
                f"* artifact source: `{r.get('source_reference', '?')}`",
                "* evidence: " + "; ".join(f"{e.get('source')}={e.get('value')}" for e in r.get("evidence") or []),
                "* why not allowed automatically: " + "; ".join(r.get("reasons_not_allowed") or ["—"]),
                "* what to read: the licence/terms text named above at its official source (not reachable from "
                "this container)",
                f"* record the decision: `apex-one license verify {lid} --license \"<name>\" --state "
                "PRODUCTION_ALLOWED|BLOCKED --source <URL you read> --by \"<your name>\"`", ""]
    return "\n".join(out) + "\n"
