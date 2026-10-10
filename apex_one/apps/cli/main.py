"""apex-one CLI."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="APEX ONE ULTRA — autonomous research, editorial, design & quality organization ($0 API cost).",
                  no_args_is_help=True)
providers_app = typer.Typer(help="Providers: status, free-tier attestation, terms verification.")
license_app = typer.Typer(help="Licence registry: record human verifications.")
facts_app = typer.Typer(help="Facts: inspect claims, confirm/resolve with a human decision.")
lab_app = typer.Typer(help="ONE Lab: proposals, experiments, preference scorer.")
app.add_typer(providers_app, name="providers")
app.add_typer(license_app, name="license")
app.add_typer(facts_app, name="facts")
app.add_typer(lab_app, name="lab")
local_app = typer.Typer(help="Local open-weight models: explicit acquisition (OCI, sha256-verified) and llama-server lifecycle.")
app.add_typer(local_app, name="local")
assets_app = typer.Typer(help="APEX brand asset contract (assets/apex): placeholders fail the Brand Production Gate.")
app.add_typer(assets_app, name="assets")
genome_app = typer.Typer(help="Design genome extraction from approved/rejected documents (principles, never copies).")
app.add_typer(genome_app, name="genome")
console = Console()


def _registry():
    from apex_one.compute.registry import load_registry
    from apex_one.persistence import init_db

    init_db()
    return load_registry()


# ---------------------------------------------------------------- doctor
@app.command()
def doctor(probe: bool = typer.Option(False, help="Probe configured providers over the network.")):
    """Check the machine, policy, browser, database, providers, and recommend local models."""
    from apex_one import WORKFLOW_VERSION, __version__
    from apex_one.apps.status import provider_status
    from apex_one.compute.hardware import detect_hardware, plan_acquisition
    from apex_one.core.policies.cost import COST_POLICY, policy_override_report
    from apex_one.design.genome import load_genome
    from apex_one.editorial.voice import load_voice
    from apex_one.persistence.db import db_ready
    from apex_one.settings import get_settings

    s = get_settings()
    reg = _registry()
    hw = detect_hardware(s.home)
    console.rule(f"APEX ONE {__version__} · workflow {WORKFLOW_VERSION}")
    console.print(f"[bold]Cost policy[/]: max ${COST_POLICY.max_api_cost_usd:.2f} · paid fallback "
                  f"{COST_POLICY.paid_fallback_allowed} · billing {COST_POLICY.auto_billing_allowed} · "
                  f"quota bypass {COST_POLICY.quota_bypass_allowed}")
    for w in policy_override_report():
        console.print(f"[red]POLICY WARNING[/]: {w}")
    console.print(f"[bold]Machine[/]: {hw.os} {hw.machine} · {hw.cpu} · {hw.cpu_count} cores · RAM {hw.ram_gb} GB · "
                  f"Apple Silicon {hw.apple_silicon} · GPU {hw.gpus or 'none'} · free disk {hw.free_disk_gb} GB")
    console.print(f"[bold]Local runtimes[/]: docker {hw.docker} · ollama {hw.ollama_binary} · llama.cpp "
                  f"{hw.llama_cpp_binary} · mlx {hw.mlx_installed}")
    console.print(f"[bold]Chromium[/]: {hw.chromium or '[red]NOT FOUND — run `playwright install chromium` or set APEX_CHROMIUM_PATH'}")
    console.print(f"[bold]Database[/]: {s.database_url.split('@')[-1]} · migrated {db_ready()}")
    console.print(f"[bold]Genome[/]: {load_genome().version} · [bold]Voice[/]: {load_voice().version}")
    console.print(f"[bold]Registry[/]: {len(reg.models)} models/engines · {len(reg.providers)} providers · "
                  f"{len(reg.licenses)} licence records")
    t = Table(title="Providers")
    for c in ("id", "kind", "integration", "availability", "detail"):
        t.add_column(c)
    for r in provider_status(reg, probe=probe):
        t.add_row(r["id"], r["kind"], r["integration"], r["availability"], r["detail"][:60])
    console.print(t)
    t = Table(title="Local model acquisition plan (nothing is downloaded automatically)")
    for c in ("model", "verdict", "reason", "command"):
        t.add_column(c)
    for a in plan_acquisition(reg, hw)[:14]:
        t.add_row(a.model_id, a.verdict, a.reason[:70], a.command[:50])
    console.print(t)


# ---------------------------------------------------------------- providers / models / licences
@providers_app.callback(invoke_without_command=True)
def providers(ctx: typer.Context, probe: bool = typer.Option(False, help="Network probe of configured providers"),
              as_json: bool = typer.Option(False, "--json")):
    """List providers with integration status and runtime availability."""
    if ctx.invoked_subcommand:
        return
    from apex_one.apps.status import provider_status

    rows = provider_status(_registry(), probe=probe)
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    t = Table(title="Providers")
    for c in ("id", "kind", "integration", "availability", "free-tier attested", "terms ok", "detail"):
        t.add_column(c)
    for r in rows:
        t.add_row(r["id"], r["kind"], r["integration"], r["availability"], str(r["free_tier_attested"]),
                  str(r["terms_production"]), r["detail"][:50])
    console.print(t)


@providers_app.command("live-test")
def providers_live_test(out: Path = typer.Option(None), structured: bool = typer.Option(True)):
    """Phase 14: real network/credential checks for every provider + real structured task on every runnable route."""
    from apex_one.compute.live import live_test_route, provider_level_report, save_report
    from apex_one.compute.local.server import LocalServer
    from apex_one.compute.local import load_catalogue
    from apex_one.settings import get_settings

    reg = _registry()
    rows = provider_level_report(reg)
    if structured:
        _, specs = load_catalogue()
        for spec in specs.values():
            m = reg.models.get(spec.registry_model)
            route = next((r for r in (m.routes if m else []) if r.provider == "llamacpp_local"
                          and r.provider_model_id == spec.key), None)
            if route is None:
                rows.append({"provider": "llamacpp_local", "model": spec.key, "status": "UNKNOWN",
                             "detail": "not acquired (apex-one local acquire)"})
                continue
            if not LocalServer(spec).healthy():
                rows.append({"provider": "llamacpp_local", "model": spec.key, "status": "UNKNOWN",
                             "detail": "acquired but server not running (apex-one local serve)"})
                continue
            rows.append(live_test_route(reg, m, route))
    dest = out or get_settings().artifacts_dir / "live" / "provider_live_report.json"
    save_report(rows, dest)
    t = Table(title="Live provider test")
    for c in ("provider", "model", "status", "detail"):
        t.add_column(c)
    for r in rows:
        t.add_row(r["provider"], r.get("model", ""), r["status"],
                  str(r.get("network") or r.get("detail") or r.get("structured_output", ""))[:70])
    console.print(t)
    console.print(f"report: {dest}")


@local_app.command("status")
def local_status_cmd():
    """Show acquired local models and running servers."""
    from apex_one.compute.local import LocalServer, load_catalogue, local_status

    _, specs = load_catalogue()
    t = Table(title="Local models")
    for c in ("key", "registry model", "acquired", "running", "port", "files"):
        t.add_column(c)
    for row in local_status():
        t.add_row(row["key"], row["registry_model"], str(row["acquired"]),
                  str(LocalServer(specs[row["key"]]).healthy()), str(row["port"]), ", ".join(row["files"])[:50])
    console.print(t)


@local_app.command("acquire")
def local_acquire(key: str):
    """Explicitly download one catalogue model (disk-checked, resumable, sha256-verified)."""
    from apex_one.compute.local import acquire, load_catalogue

    _, specs = load_catalogue()
    if key not in specs:
        raise typer.BadParameter(f"unknown key; choose from {sorted(specs)}")
    rec = acquire(specs[key], progress=lambda m: console.print(m))
    console.print(f"[green]acquired[/] {key}: {[f['file'] for f in rec['files']]}")


@local_app.command("serve")
def local_serve(key: str):
    """Start llama-server for an acquired model (OpenAI-compatible on 127.0.0.1)."""
    from apex_one.compute.local import LocalServer, load_catalogue

    _, specs = load_catalogue()
    console.print(f"serving {key} at {LocalServer(specs[key]).start()}")


@local_app.command("stop")
def local_stop(key: str):
    """Stop a local llama-server."""
    from apex_one.compute.local import LocalServer, load_catalogue

    _, specs = load_catalogue()
    LocalServer(specs[key]).stop()
    console.print(f"stopped {key}")


@assets_app.command("validate")
def assets_validate(as_json: bool = typer.Option(False, "--json")):
    """Validate assets/apex against config/asset_contract.yaml. Exit code 1 when not production-ready."""
    from apex_one.release.assets import validate_assets

    rep = validate_assets()
    if as_json:
        console.print_json(json.dumps(rep))
    else:
        t = Table(title=f"APEX assets · {rep['asset_dir']}")
        for c in ("asset", "status", "problems"):
            t.add_column(c)
        for name, r in rep["assets"].items():
            t.add_row(name, r["status"], "; ".join(r["problems"])[:120])
        console.print(t)
        console.print(f"production_ready: [bold]{rep['production_ready']}[/]")
    raise typer.Exit(0 if rep["production_ready"] else 1)


@genome_app.command("ingest")
def genome_ingest(paths: list[Path], verdict: str = typer.Option("approved", help="approved | rejected"),
                  reason: str = typer.Option(""), out: Path = typer.Option(None)):
    """Extract page signatures, principles and occupancy patterns from PDF / HTML / screenshots."""
    from apex_one.design.genome_extraction import ingest
    from apex_one.settings import get_settings

    if verdict not in ("approved", "rejected"):
        raise typer.BadParameter("verdict must be approved or rejected")
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise typer.BadParameter(f"not found: {missing}")
    res = ingest(paths, verdict, out or get_settings().artifacts_dir / "genome", reason=reason)
    console.print_json(json.dumps(res))


@genome_app.command("principles")
def genome_principles(extraction: Path):
    """Print the principles recorded in a genome extraction file."""
    data = json.loads(extraction.read_text(encoding="utf-8"))
    t = Table(title=f"Principles · {data['pages']} page(s) from {', '.join(data['documents'])}")
    for c in ("principle", "value", "statement"):
        t.add_column(c)
    for p in data["principles"]:
        t.add_row(p["name"], json.dumps(p["value"], ensure_ascii=False)[:60], p["statement"])
    console.print(t)


@providers_app.command("attest")
def providers_attest(provider: str, by: str = typer.Option(..., help="Your name"),
                     kind: str = typer.Option("free_tier_no_billing", help="free_tier_no_billing | terms_production"),
                     days: int = typer.Option(30, help="Attestation validity"),
                     note: str = typer.Option("")):
    """Record a human attestation (e.g. the key belongs to a free-tier account with billing disabled)."""
    from apex_one.persistence.db import session_scope
    from apex_one.persistence.models import ProviderAttestationRow

    reg = _registry()
    if provider not in reg.providers:
        raise typer.BadParameter(f"unknown provider {provider}")
    if kind not in ("free_tier_no_billing", "terms_production"):
        raise typer.BadParameter("kind must be free_tier_no_billing or terms_production")
    with session_scope() as s:
        s.add(ProviderAttestationRow(provider=provider, kind=kind, attested_by=by, note=note,
                                     expires_at=datetime.now(UTC) + timedelta(days=days)))
    console.print(f"[green]Recorded[/] {kind} attestation for {provider} by {by} (valid {days} days). "
                  "The firewall still blocks any route whose live price is non-zero.")


@providers_app.command("revoke")
def providers_revoke(provider: str):
    """Revoke all attestations for a provider."""
    from apex_one.persistence.db import session_scope
    from apex_one.persistence.models import ProviderAttestationRow

    _registry()
    with session_scope() as s:
        for r in s.query(ProviderAttestationRow).filter(ProviderAttestationRow.provider == provider):
            r.revoked = 1
    console.print(f"revoked attestations for {provider}")


@app.command()
def models(category: str = typer.Option(None, help="general | design"), as_json: bool = typer.Option(False, "--json")):
    """List the full model arsenal with integration status, availability and licence state."""
    from apex_one.apps.status import model_status

    rows = model_status(_registry(), category)
    if as_json:
        print(json.dumps(rows, indent=2, default=str))
        return
    t = Table(title="Model arsenal")
    for c in ("id", "cat", "integration", "availability", "licence state", "verified", "production"):
        t.add_column(c)
    for r in rows:
        t.add_row(r["id"], r["category"][:3], r["integration"], r["availability"], r["licence_state"],
                  str(r["licence_verified"]), str(r["production_allowed"]))
    console.print(t)


@license_app.command("verify")
def license_verify(license_id: str, license_name: str = typer.Option(..., "--license"),
                   state: str = typer.Option(..., help="PRODUCTION_ALLOWED|RESEARCH_ONLY|NON_COMMERCIAL|BLOCKED"),
                   source: str = typer.Option(..., help="URL of the licence text you read"),
                   by: str = typer.Option(..., help="Your name"),
                   commercial: str = typer.Option("unknown"), notes: str = typer.Option("")):
    """Record a human licence verification (overrides the YAML registry)."""
    from apex_one.core.schemas.compute import ProductionState
    from apex_one.persistence.db import session_scope
    from apex_one.persistence.models import LicenseVerificationRow

    reg = _registry()
    if license_id not in reg.licenses:
        raise typer.BadParameter(f"unknown licence id {license_id}")
    ProductionState(state)
    payload = {"license_name": license_name, "production_state": state, "source_reference": source,
               "verified_by": by, "verified_at": datetime.now(UTC).isoformat(), "commercial_use": commercial,
               "notes": notes}
    with session_scope() as s:
        s.add(LicenseVerificationRow(license_id=license_id, payload=payload, verified_by=by))
    console.print(f"[green]Recorded[/] {license_id} = {license_name} ({state}) by {by}")


# ---------------------------------------------------------------- jobs
def _runner(job_id: str):
    from apex_one.core.governor.runner import JobRunner

    return JobRunner.load(job_id, log=lambda m: console.print(f"[dim]{m}[/]"))


def _summary(job) -> None:
    from apex_one.settings import get_settings

    console.print(f"[bold]{job.job_id}[/] · state [cyan]{job.state}[/] · status [magenta]{job.status.value}[/]")
    for b in job.blockers:
        console.print(f"  • {b}")
    console.print(f"  artifacts: {get_settings().jobs_dir / job.job_id}")


@app.command("create-guide")
def create_guide(opportunity: str = typer.Option(..., help='e.g. "Berea College Fall 2027"'),
                 quality: str = typer.Option("ultra", help="draft|standard|high|ultra"),
                 budget: float = typer.Option(0.0, help="Must be 0. Paid APIs are never used."),
                 offline_fixture: str = typer.Option(None, help="synthetic_berea_style for the offline golden benchmark"),
                 sources: Path = typer.Option(None, help="Directory of saved official sources (+ sources.yaml)"),
                 seed: int = typer.Option(20271)):
    """Create and run a guide job until it needs a human (or is blocked)."""
    from apex_one.core.governor.runner import JobRunner

    if budget != 0:
        console.print("[red]Refused[/]: APEX ONE runs with a hard $0.00 API budget.")
        raise typer.Exit(2)
    text = opportunity if opportunity.lower().startswith(("create", "make")) else f"Create an APEX guide for {opportunity}"
    r = JobRunner.create(text, quality=quality, budget=budget, offline_fixture=offline_fixture,
                         sources=str(sources) if sources else None, seed=seed,
                         log=lambda m: console.print(f"[dim]{m}[/]"))
    job = r.run()
    _summary(job)


@app.command()
def resume(job_id: str):
    """Resume a job from its last checkpoint."""
    _summary(_runner(job_id).run())


@app.command()
def inspect(job_id: str, as_json: bool = typer.Option(False, "--json")):
    """Show a job's state, gates, quality report and artifacts."""
    r = _runner(job_id)
    if as_json:
        print(r.job.model_dump_json(indent=2))
        return
    _summary(r.job)
    if r.ws.exists("quality_report.json"):
        q = r.ws.read_json("quality_report.json")
        t = Table(title="Quality gates")
        for c in ("gate", "kind", "status", "value", "threshold"):
            t.add_column(c)
        for g in q["gates"]:
            v = g["metric"]["value"]
            t.add_row(g["gate"], g["kind"], g["status"], "—" if v is None else f"{v:.1f}", str(g["threshold"]))
        console.print(t)
        for w in q["warnings"]:
            console.print(f"[yellow]warning[/]: {w}")
    console.print(f"{len(r.ws.list_artifacts())} artifacts")


@app.command()
def reproduce(job_id: str):
    """Re-run a job with the same mission, seed, quality, fixture/sources and compare outcomes."""
    from apex_one.core.governor.runner import JobRunner

    src = _runner(job_id)
    j = src.job
    text = j.mission.text
    r = JobRunner.create(text, quality=j.policy.quality.mode.value, offline_fixture=j.offline_fixture,
                         sources=j.source_inputs[0] if j.source_inputs else None, seed=j.policy.seed,
                         log=lambda m: console.print(f"[dim]{m}[/]"))
    new = r.run()
    a = {lk.slot: lk.value.canonical for lk in src.rd.state.locks}
    b = {lk.slot: lk.value.canonical for lk in r.rd.state.locks}
    sig = lambda run: [c["structural_signature"] for c in run.ws.read_json("layout_chosen.json")] \
        if run.ws.exists("layout_chosen.json") else []
    report = {"original": job_id, "reproduction": new.job_id, "facts_identical": a == b,
              "layout_signatures_identical": sig(src) == sig(r), "state": new.state, "status": new.status.value,
              "note": "external model nondeterminism (if any models were used) can cause differences"}
    r.ws.write_json("reproduction_report.json", report)
    console.print_json(json.dumps(report))


@app.command()
def approve(job_id: str, by: str = typer.Option(..., help="Approver name"), notes: str = typer.Option("")):
    """Human release approval: RELEASE_CANDIDATE -> FINAL."""
    _summary(_runner(job_id).approve(by, notes))


@app.command()
def reject(job_id: str, by: str = typer.Option(...), notes: str = typer.Option(...),
           target: str = typer.Option("CREATIVE_DIRECTIONS", help="CREATIVE_DIRECTIONS | CONTENT_ARCHITECTURE")):
    """Reject a release candidate and send it back to a targeted loop."""
    _summary(_runner(job_id).reject(by, notes, target))


@app.command()
def export(job_id: str, out: Path = typer.Option(None)):
    """Export the job's release bundle as a zip."""
    from apex_one.release import export_bundle

    r = _runner(job_id)
    dest = out or (r.ws.root.parent.parent / "exports" / f"{job_id}.zip")
    console.print(f"exported {export_bundle(r.ws.root, dest)}")


@app.command()
def prefer(job_id: str, page: str = typer.Option(..., help="page id"),
           ranking: str = typer.Option(..., help="candidate ids best-first, comma separated"),
           reasons: str = typer.Option("", help="comma separated reasons"), by: str = typer.Option(...)):
    """Record a human design preference ranking (B > A > C) for preference learning."""
    from apex_one.memory import PreferenceMemory
    from apex_one.memory.preference import candidate_features

    r = _runner(job_id)
    search = r.ws.read_json("layout_search.json")
    feats = {}
    for rec in search:
        if rec["page_id"] == page:
            for c in rec["top"]:
                feats[c["candidate_id"]] = candidate_features(c["genes"], c["metrics"])
    ids = [x.strip() for x in ranking.split(",") if x.strip()]
    pairs = PreferenceMemory().record_ranking(ids, reasons=[x.strip() for x in reasons.split(",") if x.strip()],
                                              annotator=by, features=feats, job_id=job_id, page_id=page)
    console.print(f"recorded {len(pairs)} preference pairs")


@facts_app.command("list")
def facts_list(job_id: str):
    """List locked facts and claims needing a human."""
    r = _runner(job_id)
    t = Table(title="Fact locks")
    for c in ("slot", "en", "ar", "verified by", "hedge"):
        t.add_column(c)
    for lk in r.rd.state.locks:
        t.add_row(lk.slot, lk.display_en[:40], lk.display_ar[:40], lk.verified_by, lk.hedge)
    console.print(t)
    t = Table(title="Needs human")
    for c in ("slot", "claim", "value", "sources"):
        t.add_column(c)
    for c in r.rd.state.claims:
        if c.status.value == "NEEDS_HUMAN":
            t.add_row(c.slot, c.claim_id, c.value.canonical[:40], str(len(c.source_ids)))
    console.print(t)


@facts_app.command("confirm")
def facts_confirm(job_id: str, slot: str, claim: str = typer.Option(..., "--claim"), by: str = typer.Option(...)):
    """Human-confirm a claim as the locked value for a slot (resolves contradictions on that slot)."""
    lk = _runner(job_id).confirm_fact(slot, claim, by)
    console.print(f"[green]locked[/] {lk.slot} = {lk.display_en} (human:{by}); run `apex-one resume {job_id}`")


# ---------------------------------------------------------------- benchmarks / lab
@app.command()
def benchmark(suite: str = typer.Option("design", help="design | models | golden"),
              out: Path = typer.Option(None), quality: str = typer.Option("standard")):
    """Run the APEX Design Bench, the model benchmark (free routes only) or the golden end-to-end benchmark."""
    from apex_one.settings import get_settings

    base = out or get_settings().artifacts_dir / "bench"
    if suite == "design":
        from apex_one.lab.benchmarks.design_bench import run_design_bench

        res = run_design_bench(base / "design")
        t = Table(title="APEX Design Bench")
        for c in ("case", "status", "expectation", "detail"):
            t.add_column(c)
        for r in res["cases"]:
            t.add_row(r["case"], r["status"], r["expectation"][:40], r["detail"][:60])
        console.print(t)
        console.print(f"passed {res['passed']}/{res['measured']} measured · not measured {res['not_measured']}")
    elif suite == "models":
        from apex_one.compute.benchmark import run_model_benchmark
        from apex_one.compute.broker import ComputeBroker

        res = run_model_benchmark(ComputeBroker(_registry()), base / "model_scores.json")
        console.print_json(json.dumps(res))
    elif suite == "golden":
        from apex_one.lab.benchmarks.golden import run_golden

        res = run_golden(quality=quality)
        console.print_json(json.dumps(res, default=str))
    else:
        raise typer.BadParameter("suite must be design | models | golden")


@lab_app.command("propose")
def lab_propose(weakness: str = typer.Option(...), overlay: str = typer.Option(..., help="JSON overlay"),
                by: str = typer.Option("apex-one")):
    """Register an improvement proposal (never modifies production directly)."""
    from apex_one.lab.experiments import propose

    p = propose(weakness, json.loads(overlay), by)
    console.print(f"proposal {p['proposal_id']} PROPOSED")


@lab_app.command("run")
def lab_run(proposal_id: str):
    """Run the APEX Design Bench for baseline vs proposal."""
    from apex_one.lab.experiments import run_experiment

    console.print_json(json.dumps(run_experiment(proposal_id), default=str))


@lab_app.command("approve")
def lab_approve(proposal_id: str, by: str = typer.Option(...)):
    """Human approval to promote an evaluated proposal."""
    from apex_one.lab.experiments import decide

    console.print_json(json.dumps(decide(proposal_id, by, approve=True), default=str))


@lab_app.command("train-preference")
def lab_train_preference(approved_by: str = typer.Option(..., help="Explicit human approval for training")):
    """Train a CANDIDATE local preference scorer from recorded human rankings."""
    from apex_one.memory import PreferenceMemory, PreferenceScorer
    from apex_one.settings import get_settings

    _registry()
    scorer = PreferenceScorer.train(PreferenceMemory().pairs(), approved_by=approved_by)
    out = get_settings().artifacts_dir / "lab" / f"preference_scorer_{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    scorer.save(out)
    console.print(f"CANDIDATE scorer saved to {out} (train accuracy {scorer.meta['train_accuracy']:.2f}); "
                  "promotion requires `apex-one lab propose` + `lab approve`.")


# ---------------------------------------------------------------- infra
@app.command("db-upgrade")
def db_upgrade():
    """Run database migrations."""
    from apex_one.persistence import init_db

    init_db()
    console.print("database at latest migration")


@app.command()
def api(host: str = "127.0.0.1", port: int = 8787):
    """Start the FastAPI service."""
    import uvicorn

    uvicorn.run("apex_one.apps.api.main:app", host=host, port=port)


@app.command()
def worker(once: bool = typer.Option(False)):
    """Run queued/pending jobs."""
    from apex_one.apps.worker.main import work

    work(once=once)


def main() -> None:  # pragma: no cover
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
