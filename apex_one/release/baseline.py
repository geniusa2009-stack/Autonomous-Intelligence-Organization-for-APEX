"""APEX_ONE_OFFLINE_VALIDATED_BASELINE: the validated system, as content hashes and contract versions.

`docs/evidence/APEX_ONE_OFFLINE_VALIDATED_BASELINE.json` records it; `tests/test_release_closure.py` fails on any drift until the baseline is
re-recorded on purpose (`apex-one release baseline --write --reason "..."`). Routing is frozen this way: a routing
change needs new measured evidence on the identical benchmark contract, a valid licence, passing regression tests and
an explicit policy regeneration (`apex-one reports`) — and then a deliberate, reasoned baseline update. No manual
model promotion: the policy is only ever regenerated from evidence, never edited.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from apex_one.settings import get_settings

BASELINE_ID = "APEX_ONE_OFFLINE_VALIDATED_BASELINE"
ROUTE_FIELDS = ("task", "decision", "primary", "fallback", "deployment", "minimum_requirement", "licence_state")


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def baseline_path() -> Path:
    return get_settings().home / "docs" / "evidence" / f"{BASELINE_ID}.json"


def routing_policy_hash(policy: dict[str, Any] | None = None) -> str:
    """The routing DECISIONS only (not the commit stamp or latencies): who serves which task, under which rule."""
    pol = policy or json.loads((get_settings().home / "docs" / "evidence" / "production_routing_policy.json")
                               .read_text(encoding="utf-8"))
    return _h({"rule": pol["rule"], "rows": [{k: r.get(k) for k in ROUTE_FIELDS} for r in pol["rows"]]})


def memory_policy_hash() -> str:
    from apex_one.compute.local import resources as R

    return _h({"modes": R.MODE_RULES, "frozen_eval_bound_gb": R.FROZEN_EVAL_BOUND_GB,
               "production_over_evaluation_gb": R.PRODUCTION_OVER_EVALUATION_GB, "base_reserves": R.BASE_RESERVES_GB,
               "model_server_overhead_gb": R.MODEL_SERVER_OVERHEAD_GB, "chromium_peak_gb": R.CHROMIUM_MEASURED_PEAK_GB,
               "profiles": {k: v.reserves() for k, v in R.PROFILES.items()}, "recovery_min": R.RECOVERY_MIN_RATIO,
               "default_multiplier": R.DEFAULT_SAFETY_MULTIPLIER})


def acceptance_hash() -> str:
    from apex_one.lab.blockers import acceptance

    acc = acceptance()
    return _h({"rule": acc["rule"], "required": sorted(acc["required"])})


def current() -> dict[str, Any]:
    from apex_one.lab.load_test import LOAD_TEST_VERSION
    from apex_one.release import APPROVAL_CONTRACT_VERSION
    from apex_one.research.evidence_pack import EVIDENCE_PACK_VERSION

    contract = yaml.safe_load((get_settings().config_dir / "asset_contract.yaml").read_text(encoding="utf-8"))
    return {"routing_policy_sha256": routing_policy_hash(), "memory_policy_sha256": memory_policy_hash(),
            "acceptance_rule_sha256": acceptance_hash(), "brand_contract_version": contract["schema_version"],
            "approval_contract_version": APPROVAL_CONTRACT_VERSION, "evidence_pack_version": EVIDENCE_PACK_VERSION,
            "load_test_version": LOAD_TEST_VERSION}


def recorded() -> dict[str, Any] | None:
    p = baseline_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def drift() -> list[str]:
    """What differs from the recorded baseline (empty = the validated system, unchanged)."""
    rec = recorded()
    if not rec:
        return [f"no baseline recorded ({baseline_path()})"]
    cur = current()
    return [f"{k}: baseline {rec['values'].get(k)} != current {v}" for k, v in cur.items() if rec["values"].get(k) != v]


def write(commit: str, test_count: int, reason: str) -> dict[str, Any]:
    prev = recorded()
    rec = {"id": BASELINE_ID, "baseline_commit": commit, "test_count": test_count,
           "recorded_at": datetime.now(UTC).isoformat(), "reason": reason, "values": current(),
           "history": ((prev or {}).get("history") or []) + ([{k: prev[k] for k in ("baseline_commit", "recorded_at",
                                                                                    "reason")}] if prev else [])}
    baseline_path().write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec
