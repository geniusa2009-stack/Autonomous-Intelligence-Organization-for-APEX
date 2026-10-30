"""Licence verification from AUTHORITATIVE LOCAL EVIDENCE of an acquired model artifact (no memory, no guessing).

Evidence sources (independent declarations in the distribution chain):
  oci_descriptor  `descriptor.licenses` in the OCI model config blob (set by the registry publisher)
  gguf_metadata   `general.license` / `general.license.name` / `.link` embedded in the GGUF by its converter
  licence_layer   a licence file shipped as a layer of the artifact (identified from its text)

Decision rule (deliberately strict):
  PRODUCTION_ALLOWED only if >= 2 independent declarations agree on ONE permissive SPDX licence
  (Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause), no declaration names a custom/"other" licence, and the licence
  registry does not report additional usage terms (e.g. a usage policy) whose text is not available locally.
  Otherwise production_allowed = false; research/benchmark (evaluation) use is unaffected.
A human verification recorded with `apex-one license verify` always overrides this file.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PERMISSIVE = {
    "Apache-2.0": {"commercial_use": "yes", "derivative_use": "yes",
                   "redistribution": "yes, with the licence text and NOTICE preserved"},
    "MIT": {"commercial_use": "yes", "derivative_use": "yes", "redistribution": "yes, with the licence text"},
    "BSD-2-Clause": {"commercial_use": "yes", "derivative_use": "yes", "redistribution": "yes, with the licence text"},
    "BSD-3-Clause": {"commercial_use": "yes", "derivative_use": "yes", "redistribution": "yes, with the licence text"},
}
ALIASES = {"apache-2.0": "Apache-2.0", "apache 2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
           "apache license, version 2.0": "Apache-2.0", "mit": "MIT", "bsd-3-clause": "BSD-3-Clause",
           "bsd-2-clause": "BSD-2-Clause"}
GGUF_PY = "var/build/llama_cpp_python-0.3.36/vendor/llama.cpp/gguf-py"


def _spdx(value: str) -> str:
    return ALIASES.get(value.strip().lower(), value.strip())


def _licence_text_id(text: str) -> str | None:
    head = text[:4000]
    m = re.search(r"spdx-id:\s*([A-Za-z0-9.\-]+)", head)
    if m:
        return _spdx(m.group(1))
    if re.search(r"Apache License\s*,?\s*Version 2\.0", head, re.I) or "title: Apache License 2.0" in head:
        return "Apache-2.0"
    if re.search(r"\bMIT License\b", head):
        return "MIT"
    return None


def gguf_licence_fields(path: Path, home: Path) -> dict[str, str]:
    sys.path.insert(0, str(home / GGUF_PY))
    try:
        from gguf import GGUFReader  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    out = {}
    for k, fld in GGUFReader(str(path)).fields.items():
        if k.startswith("general.license") or k in ("general.base_model.0.repo_url", "general.base_model.0.organization"):
            try:
                out[k] = str(fld.contents())
            except Exception:  # noqa: BLE001
                continue
    return out


def collect_evidence(spec, home: Path) -> dict[str, Any]:
    man_path = spec.dir / "apex_manifest.json"
    if not man_path.exists():
        return {"key": spec.key, "error": "artifact not acquired"}
    man = json.loads(man_path.read_text(encoding="utf-8"))
    decl: list[dict[str, str]] = []
    desc = ((man.get("config") or {}).get("descriptor") or {}).get("licenses") or []
    for v in desc:
        decl.append({"source": "oci_descriptor", "value": v, "spdx": _spdx(v)})
    gg = (man.get("config") or {}).get("config", {}).get("gguf", {})
    main = next((f for f in man["files"] if f["file"].endswith(".gguf") and "mmproj" not in f["file"]), None)
    fields: dict[str, str] = {}
    if main and (spec.dir / main["file"]).exists():
        fields = gguf_licence_fields(spec.dir / main["file"], home)
    elif gg:
        fields = {k: v for k, v in gg.items() if k.startswith("general.license")}
    if fields.get("general.license"):
        v = fields["general.license"]
        decl.append({"source": "gguf_metadata", "value": v,
                     "spdx": "other:" + fields.get("general.license.name", "") if v.strip().lower() == "other" else _spdx(v)})
    for f in man.get("licence_files", []):
        p = spec.dir / f
        if p.exists():
            lid = _licence_text_id(p.read_text(encoding="utf-8", errors="ignore"))
            decl.append({"source": "licence_layer", "value": f, "spdx": lid or "unidentified"})
    return {"key": spec.key, "model": spec.registry_model, "artifact": man.get("source"), "declarations": decl,
            "gguf_fields": fields, "main_digest": main["digest"] if main else None}


def decide(evidence: dict[str, Any], reported_license: str = "") -> dict[str, Any]:
    decl = evidence.get("declarations", [])
    ids = {d["spdx"] for d in decl}
    sources = {d["source"] for d in decl}
    custom = sorted(i for i in ids if i.startswith("other") or i not in PERMISSIVE)
    extra_terms = bool(re.search(r"usage policy|terms of use|acceptable use|\+", reported_license, re.I))
    agreed = next(iter(ids)) if len(ids) == 1 else None
    reasons = []
    if not decl:
        reasons.append("no licence declaration found in the artifact")
    if len(ids) > 1:
        reasons.append(f"declarations disagree: {sorted(ids)}")
    if custom:
        reasons.append(f"custom / non-permissive licence declared ({custom}); its text is not available locally")
    if len(sources) < 2:
        reasons.append(f"only {len(sources)} independent declaration source(s); 2 required")
    if extra_terms and agreed in PERMISSIVE:
        reasons.append(f"licence registry reports additional terms ({reported_license!r}) not available locally")
    allowed = not reasons and agreed in PERMISSIVE
    name = agreed if allowed else f"{agreed} (declared; not production-verified)" if agreed in PERMISSIVE else (
        next((d["value"] for d in decl if d["source"] == "gguf_metadata" and "other" in d["spdx"]), None)
        and f"{evidence['gguf_fields'].get('general.license.name', 'custom')} (declared; text not verified)"
        or ("; ".join(sorted(ids)) + " (declared; not verified)" if ids else "UNKNOWN"))
    terms = PERMISSIVE.get(agreed or "", {}) if allowed else {}
    return {"license_name": name,
            "production_state": "PRODUCTION_ALLOWED" if allowed else "DECLARED_BUT_UNVERIFIED" if decl else "UNKNOWN",
            "production_allowed": allowed,
            "commercial_use": terms.get("commercial_use", "unknown"),
            "derivative_use": terms.get("derivative_use", "unknown"),
            "redistribution": terms.get("redistribution", "unknown"),
            "research_use": "yes" if decl and not any("blocked" in i.lower() for i in ids) else "unknown",
            "verification_method": "local artifact evidence: " + ", ".join(sorted(sources)) if sources else "none",
            "reasons_not_allowed": reasons,
            "evidence": decl,
            "verified_at": datetime.now(UTC).isoformat() if allowed else None,
            "verified_by": "apex-one license verify-local (artifact evidence rule)" if allowed else None,
            "source_reference": evidence.get("artifact", "")}
