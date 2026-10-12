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
    rec = {"approver": approver, "decision": decision, "notes": notes, "at": datetime.now(UTC).isoformat(),
           "authenticated": True, "ledger_seq": (ledger or {}).get("seq"), "ledger_hash": (ledger or {}).get("hash")}
    (job_dir / "human_approval.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec
