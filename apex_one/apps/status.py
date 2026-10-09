"""Shared status views used by the CLI, API and doctor (no secrets ever included)."""

from __future__ import annotations

from typing import Any

from apex_one.compute.broker import ComputeBroker
from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.compute import Availability
from apex_one.design.models import build_design_adapters


def provider_status(registry: ArsenalRegistry, probe: bool = False) -> list[dict[str, Any]]:
    broker = ComputeBroker(registry)
    rows = []
    for pid, p in registry.providers.items():
        adapter = broker.adapters[pid]
        configured, why = adapter.configured()
        if pid == "mock":
            avail, detail = Availability.AVAILABLE, "tests only (never production)"
        elif not configured and pid != "design_endpoint":
            avail, detail = Availability.CONFIGURATION_REQUIRED, why
        elif probe or p.kind == "local":   # localhost probes are instant and free
            res = adapter.probe(timeout=1.5 if p.kind == "local" else 3.0)
            avail, detail = res.availability, res.detail
        else:
            avail, detail = Availability.CONFIGURATION_REQUIRED if pid == "design_endpoint" else Availability.UNAVAILABLE, \
                "configured; run with --probe to test" if pid != "design_endpoint" else "per-model endpoint env vars"
        rows.append({"id": pid, "name": p.name, "kind": p.kind, "integration": p.integration_status.value,
                     "availability": avail.value, "detail": detail, "free_tier": p.free_tier,
                     "free_tier_attested": registry.has_attestation(pid, "free_tier_no_billing"),
                     "terms_production": p.privacy.production_allowed or registry.has_attestation(pid, "terms_production"),
                     "private_data_allowed": p.privacy.private_student_data_allowed})
    return rows


def model_status(registry: ArsenalRegistry, category: str | None = None) -> list[dict[str, Any]]:
    design = build_design_adapters(registry)
    rows = []
    for m in registry.models.values():
        if category and m.category != category:
            continue
        lic = registry.license_for(m)
        if m.category == "design":
            avail, detail = design[m.id].availability() if m.id in design else (Availability.UNAVAILABLE, "")
            if m.integration_status.value in ("NOT_YET_SUPPORTED",):
                avail, detail = Availability.UNAVAILABLE, "adapter not yet implemented (research method/pipeline)"
        elif m.family == "mock":
            avail, detail = Availability.AVAILABLE, "tests only"
        elif not m.routes:
            avail, detail = Availability.NO_FREE_ROUTE, "no route registered"
        else:
            avail, detail = Availability.CONFIGURATION_REQUIRED, f"{len(m.routes)} route(s): " + ", ".join(
                sorted({r.provider for r in m.routes}))
        if not registry.research_allowed(m):
            avail = Availability.LICENSE_BLOCKED
        rows.append({"id": m.id, "category": m.category, "family": m.family, "integration": m.integration_status.value,
                     "availability": avail.value, "detail": detail, "licence": lic.id,
                     "licence_state": lic.production_state.value, "reported_licence": lic.reported_license,
                     "licence_verified": lic.verified_at is not None,
                     "production_allowed": registry.production_allowed(m),
                     "roles": m.capabilities.design_roles, "notes": m.notes})
    return rows
