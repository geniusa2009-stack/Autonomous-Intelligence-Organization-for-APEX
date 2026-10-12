"""Minimal release-control authentication and an append-only, hash-chained approval ledger.

* Approvers are named people with a random bearer token. Only the token's SHA-256 is stored
  (`<auth dir>/approvers.json`, outside git); the token is shown once at creation.
* The approver identity of a release decision ALWAYS comes from an authenticated token — never from a name a caller
  types. A request that names someone else is rejected as forged.
* Every decision is appended to `<auth dir>/approval_ledger.jsonl`; each entry carries the hash of the previous one,
  so editing or deleting any past entry breaks `verify_ledger()`.

Auth dir: $APEX_AUTH_DIR, default `<APEX home>/var/auth`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROLE_RELEASE = "release_approver"
GENESIS = "0" * 64


class AuthError(Exception):
    """Missing, unknown, revoked or insufficient credentials (HTTP 401/403)."""


@dataclass(frozen=True)
class Identity:
    approver_id: str
    name: str
    role: str


def auth_dir() -> Path:
    from apex_one.settings import get_settings

    d = Path(os.environ.get("APEX_AUTH_DIR") or get_settings().home / "var" / "auth")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load() -> dict[str, Any]:
    p = auth_dir() / "approvers.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"approvers": []}


def _save(data: dict[str, Any]) -> None:
    p = auth_dir() / "approvers.json"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(p, 0o600)


def create_approver(name: str, role: str = ROLE_RELEASE) -> str:
    """Register a named approver; returns the bearer token ONCE (only its hash is stored)."""
    name = name.strip()
    if not name:
        raise ValueError("an approver needs a name")
    data = _load()
    if any(a["name"] == name and not a["revoked"] for a in data["approvers"]):
        raise ValueError(f"approver {name!r} already exists (revoke first to rotate)")
    token = "apx_" + secrets.token_urlsafe(32)
    data["approvers"].append({"id": "AP-" + secrets.token_hex(6), "name": name, "role": role, "sha256": _sha(token),
                              "created_at": datetime.now(UTC).isoformat(), "revoked": False})
    _save(data)
    append_ledger({"event": "approver_created", "name": name, "role": role})
    return token


def revoke_approver(name: str) -> None:
    data = _load()
    hit = [a for a in data["approvers"] if a["name"] == name and not a["revoked"]]
    if not hit:
        raise ValueError(f"no active approver {name!r}")
    for a in hit:
        a["revoked"] = True
        a["revoked_at"] = datetime.now(UTC).isoformat()
    _save(data)
    append_ledger({"event": "approver_revoked", "name": name})


def list_approvers() -> list[dict[str, Any]]:
    return [{k: v for k, v in a.items() if k != "sha256"} for a in _load()["approvers"]]


def authenticate(token: str | None, role: str = ROLE_RELEASE) -> Identity:
    if not token:
        raise AuthError("authentication required: no approver token")
    digest = _sha(token)
    for a in _load()["approvers"]:
        if hmac.compare_digest(a["sha256"], digest):
            if a["revoked"]:
                raise AuthError(f"approver token for {a['name']} has been revoked")
            if a["role"] != role:
                raise AuthError(f"{a['name']} lacks role {role}")
            return Identity(a["id"], a["name"], a["role"])
    raise AuthError("invalid approver token")


def check_claimed_name(identity: Identity, claimed: str | None) -> None:
    """A caller may restate who they are, but never claim to be someone else."""
    if claimed and claimed.strip() != identity.name:
        raise AuthError(f"forged approver: token belongs to {identity.name!r}, request claims {claimed!r}")


# ---------------------------------------------------------------- ledger


def _ledger() -> Path:
    return auth_dir() / "approval_ledger.jsonl"


def _entries() -> list[dict[str, Any]]:
    p = _ledger()
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def _entry_hash(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return _sha(json.dumps(body, sort_keys=True, ensure_ascii=False))


def append_ledger(event: dict[str, Any]) -> dict[str, Any]:
    entries = _entries()
    entry = {"seq": len(entries) + 1, "at": datetime.now(UTC).isoformat(),
             "prev_hash": entries[-1]["hash"] if entries else GENESIS, **event}
    entry["hash"] = _entry_hash(entry)
    with _ledger().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def verify_ledger() -> tuple[bool, list[str]]:
    problems, prev = [], GENESIS
    for i, e in enumerate(_entries(), 1):
        if e.get("seq") != i:
            problems.append(f"entry {i}: sequence {e.get('seq')} (deleted or reordered entry)")
        if e.get("prev_hash") != prev:
            problems.append(f"entry {i}: chain broken (prev_hash mismatch)")
        if _entry_hash(e) != e.get("hash"):
            problems.append(f"entry {i}: content altered (hash mismatch)")
        prev = e.get("hash", "")
    return not problems, problems


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
