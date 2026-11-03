"""Evidence packs: validate a REAL opportunity from saved authoritative evidence, with no live network during the run.

A pack is a directory:

  pack.yaml            opportunity: "<name and cycle>", prepared_by, prepared_at, notes
  sources.yaml         sources: [{url, file, cycle_year?, title?, kind?}]   — url = where the file was saved FROM
  <files>              saved official pages (.html/.htm) and PDFs (.pdf)
  confirmations.yaml   confirmations: [{slot, value, by, at, note?}]        — optional human-confirmed facts

`apex-one evidence run <pack>` runs the normal pipeline on it — source extraction → Fact Lock → deadline /
eligibility / funding validation → citation mapping → guide → deterministic QA → release candidate — then applies
the human confirmations to any slot left NEEDS_HUMAN (matching the confirmed value to an extracted claim, never
inventing one) and resumes. Every file is hashed into the job, so the run is reproducible from the pack alone.

A pack whose URLs use reserved test domains (.invalid, .test, .example, example.com, ...) is a TEST PACK: it proves
the pipeline, and it never counts as a validated real opportunity.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

EVIDENCE_PACK_VERSION = 1      # pack.yaml + sources.yaml + files + confirmations.yaml (module docstring)
RESERVED = re.compile(r"(\.invalid|\.test|\.example|\.localhost|(^|\.)example\.(com|org|net))$", re.IGNORECASE)
KINDS = {".html": "html", ".htm": "html", ".pdf": "pdf"}

PACK_TEMPLATE = """# Evidence pack — see apex_one/research/evidence_pack.py
opportunity: "<official programme name> <cycle, e.g. Fall 2027>"
prepared_by: "<your name>"
prepared_at: "<YYYY-MM-DD>"
notes: ""
"""
SOURCES_TEMPLATE = """# One entry per saved file. url = the official page the file was saved from (https).
sources: []
#  - url: https://<official domain>/<deadline page>
#    file: deadlines.html
#    cycle_year: 2027
#  - url: https://<official domain>/<funding page>.pdf
#    file: funding.pdf
"""
CONFIRMATIONS_TEMPLATE = """# Facts that only ONE source states need a named human confirmation (value exactly as printed).
confirmations: []
#  - slot: deadline.application
#    value: "16 February 2027"
#    by: "<your name>"
#    at: "<YYYY-MM-DD>"
#    note: "checked on the official page on <date>"
"""


def is_test_url(url: str) -> bool:
    return bool(RESERVED.search(urlparse(url).hostname or ""))


def init(pack: Path) -> list[str]:
    pack.mkdir(parents=True, exist_ok=True)
    made = []
    for name, text in (("pack.yaml", PACK_TEMPLATE), ("sources.yaml", SOURCES_TEMPLATE),
                       ("confirmations.yaml", CONFIRMATIONS_TEMPLATE)):
        if not (pack / name).exists():
            (pack / name).write_text(text, encoding="utf-8")
            made.append(name)
    return made


def _yaml(p: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {} if p.exists() else {}
    except yaml.YAMLError as e:
        return {"__error__": str(e)}


def check(pack: Path) -> dict[str, Any]:
    """Readiness of a pack: problems block a run; warnings do not."""
    problems, warnings, sources = [], [], []
    meta = _yaml(pack / "pack.yaml")
    opp = str(meta.get("opportunity") or "")
    if not opp or opp.startswith("<"):
        problems.append("pack.yaml: set `opportunity` (programme name + cycle)")
    man = _yaml(pack / "sources.yaml")
    if "__error__" in man:
        problems.append(f"sources.yaml is not valid YAML: {man['__error__']}")
    entries = man.get("sources") or []
    if not entries:
        problems.append("sources.yaml lists no sources")
    seen = set()
    for e in entries:
        url, f = str(e.get("url") or ""), str(e.get("file") or "")
        p = pack / f
        rec = {"url": url, "file": f, "kind": KINDS.get(p.suffix.lower()), "exists": p.is_file(),
               "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
               "bytes": p.stat().st_size if p.is_file() else 0, "test_domain": is_test_url(url)}
        sources.append(rec)
        if not url.startswith(("https://", "http://")):
            problems.append(f"{f or '?'}: url must be the http(s) page it was saved from")
        if url in seen:
            problems.append(f"duplicate url {url}")
        seen.add(url)
        if not rec["exists"]:
            problems.append(f"{f}: file missing")
        elif rec["kind"] is None:
            problems.append(f"{f}: only .html/.htm/.pdf are accepted")
        elif rec["bytes"] < 200:
            problems.append(f"{f}: only {rec['bytes']} bytes — not a saved page")
    conf = _yaml(pack / "confirmations.yaml").get("confirmations") or []
    for c in conf:
        miss = [k for k in ("slot", "value", "by", "at") if not c.get(k)]
        if miss:
            problems.append(f"confirmation {c.get('slot', '?')}: missing {miss}")
    test_pack = bool(sources) and any(s["test_domain"] for s in sources)
    if test_pack:
        warnings.append("TEST PACK: reserved test domains — proves the pipeline, never a real opportunity")
    pack_hash = hashlib.sha256(json.dumps(sorted((s["url"], s["sha256"]) for s in sources)).encode()).hexdigest()
    return {"pack": str(pack), "opportunity": opp, "ready": not problems, "problems": problems,
            "warnings": warnings, "test_pack": test_pack, "sources": sources, "confirmations": len(conf),
            "pack_sha256": pack_hash}


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]+", " ", str(s).lower()).strip()


def apply_confirmations(runner, pack: Path) -> list[dict[str, Any]]:
    """Lock NEEDS_HUMAN slots from confirmations.yaml — only to a value an extracted claim actually carries."""
    applied = []
    open_slots = {c.slot for c in runner.rd.state.claims if c.status.value == "NEEDS_HUMAN"}
    for c in _yaml(pack / "confirmations.yaml").get("confirmations") or []:
        if c.get("slot") not in open_slots:
            applied.append({**c, "applied": False, "why": "slot is not awaiting a human"})
            continue
        claim = next((x for x in runner.rd.state.claims if x.slot == c["slot"] and _norm(c["value"]) in
                      (_norm(x.value.canonical), _norm(x.value.raw))), None)
        if claim is None:
            applied.append({**c, "applied": False, "why": "no extracted claim carries this value: add the source"})
            continue
        runner.confirm_fact(c["slot"], claim.claim_id, f"{c['by']} ({c['at']})")
        applied.append({**c, "applied": True, "claim_id": claim.claim_id})
    return applied


def run(pack: Path, quality: str = "standard", seed: int = 20271) -> dict[str, Any]:
    from apex_one.core.governor.runner import JobRunner

    rep = check(pack)
    if not rep["ready"]:
        return {**rep, "status": "PACK_NOT_READY"}
    r = JobRunner.create(f"Create an APEX guide for {rep['opportunity']}", quality=quality, sources=str(pack),
                         seed=seed)
    r.ws.write_json("evidence_pack.json", rep)
    job = r.run()
    applied = []
    if job.status.value in ("AWAITING_HUMAN", "BLOCKED") and rep["confirmations"]:
        r = JobRunner.load(job.job_id)
        applied = apply_confirmations(r, pack)
        if any(a["applied"] for a in applied):
            job = JobRunner.load(job.job_id).run()
    r = JobRunner.load(job.job_id)
    locks = {lk.slot: lk for lk in r.rd.state.locks}
    critical = {k: [s for s in locks if s.startswith(k)] for k in ("deadline.", "eligibility.", "funding.")}
    out = {**rep, "job_id": job.job_id, "state": job.state, "status": job.status.value,
           "blockers": list(job.blockers), "confirmations_applied": applied,
           "stages": {"source_extraction": len(r.rd.state.sources), "claims": len(r.rd.state.claims),
                      "fact_locks": len(locks),
                      "deadline_validation": critical["deadline."] or "NO LOCK",
                      "eligibility_validation": critical["eligibility."] or "NO LOCK",
                      "funding_validation": critical["funding."] or "NO LOCK",
                      "needs_human": sorted({c.slot for c in r.rd.state.claims if c.status.value == "NEEDS_HUMAN"}),
                      "citations_mapped": r.ws.exists("evidence.json"),
                      "guide_built": r.ws.exists("final.html"), "qa_report": r.ws.exists("quality_report.json"),
                      "release_candidate": job.state == "RELEASE_CANDIDATE" and not job.blockers},
           "counts_as_real_opportunity": not rep["test_pack"]}
    r.ws.write_json("evidence_pack_run.json", out)
    return out
