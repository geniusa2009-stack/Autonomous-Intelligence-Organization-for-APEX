"""The absolute APEX cost policy.

These values are constants, not configuration. Environment variables, YAML, API calls or
job options can NOT relax them. `policy_override_report` exists only so `apex-one doctor`
can tell a human that someone tried.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_one.settings import get_settings


@dataclass(frozen=True)
class CostPolicy:
    max_api_cost_usd: float = 0.0
    paid_fallback_allowed: bool = False
    auto_billing_allowed: bool = False
    auto_upgrade_allowed: bool = False
    quota_bypass_allowed: bool = False
    multi_account_rotation_allowed: bool = False
    automatic_account_creation_allowed: bool = False
    # When free capacity is exhausted the only permitted outcomes, in order of preference:
    exhaustion_strategy: tuple[str, ...] = ("LOCAL_FALLBACK", "QUEUE", "WAIT", "DEGRADE")

    def __setattr__(self, *_: object) -> None:  # pragma: no cover - frozen guard
        raise AttributeError("CostPolicy is immutable")


COST_POLICY = CostPolicy()

_SAFE = {
    "APEX_MAX_API_COST_USD": {"0", "0.0", "0.00", "0.000"},
    "APEX_PAID_FALLBACK_ALLOWED": {"false", "0", "no"},
    "APEX_AUTO_BILLING_ALLOWED": {"false", "0", "no"},
    "APEX_AUTO_UPGRADE_ALLOWED": {"false", "0", "no"},
    "APEX_QUOTA_BYPASS_ALLOWED": {"false", "0", "no"},
}


def policy_override_report() -> list[str]:
    """Return human-readable warnings for any env var that tried to relax the policy."""
    warnings: list[str] = []
    for key, value in get_settings().env_policy_overrides.items():
        if value.strip().lower() not in _SAFE.get(key, set()):
            warnings.append(
                f"{key}={value!r} was IGNORED: the APEX cost policy is a hard invariant "
                f"(max cost $0.00, no paid fallback, no billing, no upgrades, no quota bypass)."
            )
    return warnings
