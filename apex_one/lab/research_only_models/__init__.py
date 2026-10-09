"""ONE Lab view of research-only / non-commercial / unverified models.

They stay fully visible to experiments and benchmarks; any output they produce is tagged
`research_only=True` and the release LicenseGuard blocks it from production artifacts.
"""

from __future__ import annotations

from apex_one.compute.registry.loader import ArsenalRegistry


def research_only_inventory(registry: ArsenalRegistry) -> list[dict]:
    out = []
    for m in registry.models.values():
        if m.family in ("apex-native", "mock"):
            continue
        if not registry.production_allowed(m):
            lic = registry.license_for(m)
            out.append({"model": m.id, "category": m.category, "licence_state": lic.production_state.value,
                        "verified": lic.verified_at is not None, "lab_usable": registry.research_allowed(m),
                        "integration": m.integration_status.value})
    return out
