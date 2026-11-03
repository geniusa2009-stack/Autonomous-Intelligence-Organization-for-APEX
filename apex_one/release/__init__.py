"""ONE Release: licence guard, release candidate packaging, human approval gate, export."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.compute import EVALUATION_TASKS
from apex_one.core.security import contains_secret

# Model calls with EVALUATION_TASKS prefixes made under purpose=evaluation only JUDGE or MEASURE; their text never
# enters final.html/final.pdf.


def _is_evaluation(c: dict) -> bool:
    """A call counts as evaluation only if it was BOTH routed with purpose=evaluation and is an evaluation task."""
    return c.get("purpose", "production") == "evaluation" and str(c.get("task", "")).startswith(EVALUATION_TASKS)

# approval contract: identity (token), job id, timestamp, final.pdf/final.html sha256, decision, comment, ledger entry;
# approval refused for bytes not reviewed; FINAL refused if the artifact changed after approval
APPROVAL_CONTRACT_VERSION = 2

REQUIRED_ARTIFACTS = ["final.html", "final.pdf", "sources.json", "evidence.json", "claims.json", "contradictions.json",
                      "document_ast.json", "design_decisions.json", "model_routing.json", "quality_report.json",
                      "license_report.json", "contact_sheet.png", "job.json", "execution_plan.json",
                      "opportunity_model.json", "design_intent.json"]


def license_guard(registry: ArsenalRegistry, engines: list[str], model_calls: list[dict],
                  purpose: str = "production") -> tuple[dict, Metric]:
    """Every engine/model that contributed to output must be production-allowed (verified licence)."""
    rows, prohibited = [], []
    content_calls = [c for c in model_calls if c.get("outcome") == "ok" and not _is_evaluation(c)]
    evaluators = sorted({c["model_id"] for c in model_calls if c.get("outcome") == "ok" and _is_evaluation(c)})
    used = sorted(set(engines) | {c["model_id"] for c in content_calls})
    for mid in used:
        if mid not in registry.models:
            rows.append({"engine": mid, "state": "PIPELINE_STEP", "production_allowed": True})
            continue
        lic = registry.license_for(mid)
        ok = registry.production_allowed(mid)
        rows.append({"engine": mid, "licence": lic.id, "license_name": lic.license_name,
                     "state": lic.production_state.value, "verified_at": str(lic.verified_at) if lic.verified_at else None,
                     "production_allowed": ok})
        if not ok and purpose == "production":
            prohibited.append(mid)
    report = {"purpose": purpose, "engines": rows, "prohibited_in_output": prohibited,
              "evaluation_only_models": evaluators,
              "checked_at": datetime.now(UTC).isoformat()}
    return report, Metric.measured("license.prohibited_engines_in_output", len(prohibited),
                                   "licence registry check of every contributing engine", unit="count",
                                   evidence=prohibited)


def artifacts_complete(job_dir: Path) -> list[str]:
    missing = [a for a in REQUIRED_ARTIFACTS if not (job_dir / a).exists()]
    if not any((job_dir / "screenshots").glob("page-*.png")):
        missing.append("screenshots/")
    return missing


def secret_scan(job_dir: Path) -> list[str]:
    hits = []
    for p in job_dir.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".jsonl", ".html", ".md", ".txt"):
            try:
                if contains_secret(p.read_text(encoding="utf-8", errors="ignore")):
                    hits.append(str(p.relative_to(job_dir)))
            except OSError:
                continue
    return hits


def export_bundle(job_dir: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(job_dir.rglob("*")):
            if p.is_file() and "design_candidates" not in p.parts:
                z.write(p, p.relative_to(job_dir))
    return out


def write_approval(job_dir: Path, approver: str, decision: str, notes: str, ledger: dict | None = None) -> dict:
    """The job-side copy of a release decision: who (authenticated), which job, when, which artifact bytes
    (sha256 of final.pdf / final.html at decision time), what, and the ledger entry that proves it."""
    led = ledger or {}
    rec = {"job_id": led.get("job_id"), "approver": approver, "approver_id": led.get("approver_id"),
           "decision": decision, "notes": notes, "at": led.get("at") or datetime.now(UTC).isoformat(),
           "authenticated": True, "final_pdf_sha256": led.get("final_pdf_sha256"),
           "final_html_sha256": led.get("final_html_sha256"), "ledger_seq": led.get("seq"),
           "ledger_hash": led.get("hash")}
    (job_dir / "human_approval.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def approval_binding_problems(job_dir: Path) -> list[str]:
    """A FINAL artifact must be byte-identical to what the authenticated approver approved, and the approval must
    exist, unaltered, in the hash-chained ledger."""
    from apex_one.core.auth import _entries, file_sha256, verify_ledger

    p = job_dir / "human_approval.json"
    if not p.exists():
        return ["no human_approval.json: never approved"]
    rec = json.loads(p.read_text(encoding="utf-8"))
    probs = []
    if rec.get("decision") != "APPROVED":
        probs.append(f"decision is {rec.get('decision')}, not APPROVED")
    for name, key in (("final.pdf", "final_pdf_sha256"), ("final.html", "final_html_sha256")):
        now = file_sha256(job_dir / name)
        if rec.get(key) != now:
            probs.append(f"{name} changed after approval (approved {str(rec.get(key))[:12]}, now {str(now)[:12]})")
    ok, chain = verify_ledger()
    if not ok:
        probs.append(f"approval ledger broken: {chain[:2]}")
    led = next((e for e in _entries() if e.get("seq") == rec.get("ledger_seq")), None)
    if not led or led.get("hash") != rec.get("ledger_hash") or led.get("job_id") != rec.get("job_id"):
        probs.append("approval record does not match its ledger entry")
    return probs


def export_final(job_dir: Path, out: Path) -> dict:
    """Export a FINAL release: refused unless the job is FINAL and its approval binding is intact. Writes the zip and
    `<zip>.sha256`, and returns the hashes a recipient can verify."""
    import hashlib

    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    if job.get("status") != "FINAL":
        raise RuntimeError(f"job is {job.get('status')}, not FINAL: only an approved release can be exported as FINAL")
    probs = approval_binding_problems(job_dir)
    if probs:
        raise RuntimeError("approval binding broken: " + "; ".join(probs))
    export_bundle(job_dir, out)
    zip_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    rec = json.loads((job_dir / "human_approval.json").read_text(encoding="utf-8"))
    side = out.with_suffix(out.suffix + ".sha256")          # `sha256sum -c` format, run inside the export folder
    side.write_text(f"{zip_sha}  {out.name}\n", encoding="utf-8")
    note = out.with_suffix(out.suffix + ".approval.json")
    note.write_text(json.dumps({k: rec.get(k) for k in ("job_id", "approver", "approver_id", "at", "decision",
                                                        "final_pdf_sha256", "final_html_sha256", "ledger_seq",
                                                        "ledger_hash")} | {"zip_sha256": zip_sha}, indent=2),
                    encoding="utf-8")
    return {"zip": str(out), "zip_sha256": zip_sha, "final_pdf_sha256": rec["final_pdf_sha256"],
            "approved_by": rec["approver"], "ledger_seq": rec["ledger_seq"], "checksum_file": str(side),
            "approval_note": str(note)}
