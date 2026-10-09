"""Loads the provider, model, licence and design-capability registries.

YAML is the declared state; human verifications/attestations recorded in the database overlay it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from apex_one.core.schemas.compute import (
    IntegrationStatus,
    LicenseRecord,
    ModelEntry,
    ProductionState,
    ProviderEntry,
)
from apex_one.settings import get_settings


class RegistryError(Exception):
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RegistryError(f"missing registry file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schema_version") != 1:
        raise RegistryError(f"{path.name}: unsupported schema_version {data.get('schema_version')}")
    return data


@dataclass
class ArsenalRegistry:
    providers: dict[str, ProviderEntry]
    models: dict[str, ModelEntry]
    licenses: dict[str, LicenseRecord]
    design_matrix: dict[str, Any]
    quality_gates: dict[str, Any]
    attestations: list[dict[str, Any]] = field(default_factory=list)
    config_dir: Path | None = None

    # ---------- lookups ----------
    def model(self, model_id: str) -> ModelEntry:
        try:
            return self.models[model_id]
        except KeyError as exc:
            raise RegistryError(f"unknown model {model_id}") from exc

    def provider(self, provider_id: str) -> ProviderEntry:
        try:
            return self.providers[provider_id]
        except KeyError as exc:
            raise RegistryError(f"unknown provider {provider_id}") from exc

    def _entry(self, model: str | ModelEntry) -> ModelEntry:
        return model if isinstance(model, ModelEntry) else self.model(model)

    def license_for(self, model: str | ModelEntry) -> LicenseRecord:
        ref = self._entry(model).license_ref
        return self.licenses.get(ref) or LicenseRecord(id=ref or "lic-missing")

    def production_allowed(self, model: str | ModelEntry) -> bool:
        m = self._entry(model)
        if m.integration_status in (IntegrationStatus.RESEARCH_ONLY, IntegrationStatus.LICENSE_BLOCKED):
            return False
        return self.license_for(m).production_allowed

    def research_allowed(self, model: str | ModelEntry) -> bool:
        return self.license_for(model).production_state != ProductionState.BLOCKED

    def design_role(self, role: str) -> dict[str, Any]:
        roles = self.design_matrix.get("roles", {})
        if role not in roles:
            raise RegistryError(f"unknown design role {role}")
        return roles[role]

    def design_route_for(self, node_type: str) -> tuple[str, list[str]]:
        for name, route in self.design_matrix.get("routes", {}).items():
            if node_type in route.get("applies_to", []):
                return name, list(route["steps"])
        return "narrative", list(self.design_matrix["routes"]["narrative"]["steps"])

    def has_attestation(self, provider_id: str, kind: str, now: datetime | None = None) -> bool:
        for a in self.attestations:
            if a["provider"] == provider_id and a["kind"] == kind and not a.get("revoked"):
                exp = a.get("expires_at")
                if exp is None or now is None or exp > now:
                    return True
        return False

    def spec_named_models(self) -> list[str]:
        return [m.id for m in self.models.values() if not m.id.startswith(("apex-native", "mock"))]


def _overlay_license_verifications(licenses: dict[str, LicenseRecord], db_url: str | None) -> None:
    try:
        from sqlalchemy import select

        from apex_one.persistence.db import db_ready, session_scope
        from apex_one.persistence.models import LicenseVerificationRow

        if not db_ready(db_url):
            return
        with session_scope(db_url) as s:
            rows = s.execute(select(LicenseVerificationRow).order_by(LicenseVerificationRow.at)).scalars().all()
            for row in rows:
                base = licenses.get(row.license_id) or LicenseRecord(id=row.license_id)
                licenses[row.license_id] = base.model_copy(update=dict(row.payload))
    except Exception:  # registry must load even if DB is unavailable
        return


def _load_attestations(db_url: str | None) -> list[dict[str, Any]]:
    try:
        from sqlalchemy import select

        from apex_one.persistence.db import db_ready, session_scope
        from apex_one.persistence.models import ProviderAttestationRow

        if not db_ready(db_url):
            return []
        with session_scope(db_url) as s:
            return [
                {"provider": r.provider, "kind": r.kind, "revoked": bool(r.revoked), "by": r.attested_by,
                 "at": r.at, "expires_at": r.expires_at}
                for r in s.execute(select(ProviderAttestationRow)).scalars().all()
            ]
    except Exception:
        return []


def load_registry(config_dir: Path | None = None, *, db_url: str | None = None,
                  with_db_overlay: bool = True) -> ArsenalRegistry:
    cfg = Path(config_dir or get_settings().config_dir)
    providers_raw = _read_yaml(cfg / "providers.yaml")["providers"]
    models_raw = _read_yaml(cfg / "model_registry.yaml")["models"]
    licenses_raw = _read_yaml(cfg / "license_registry.yaml")["licenses"]
    matrix = _read_yaml(cfg / "design_capability_matrix.yaml")
    gates = _read_yaml(cfg / "quality_gates.yaml")

    providers = {p["id"]: ProviderEntry(**p) for p in providers_raw}
    models = {m["id"]: ModelEntry(**m) for m in models_raw}
    licenses = {lic["id"]: LicenseRecord(**lic) for lic in licenses_raw}

    # Referential integrity: routes -> providers, models -> licences, matrix -> models.
    for m in models.values():
        for r in m.routes:
            if r.provider not in providers:
                raise RegistryError(f"model {m.id} routes to unknown provider {r.provider}")
        if m.license_ref not in licenses:
            raise RegistryError(f"model {m.id} references unknown licence {m.license_ref}")
    for role, spec in matrix.get("roles", {}).items():
        for mid in spec.get("specialists", []):
            if mid not in models:
                raise RegistryError(f"design role {role} names unknown model {mid}")
        if spec.get("native") and spec["native"] not in models:
            raise RegistryError(f"design role {role} names unknown native engine {spec['native']}")

    if with_db_overlay:
        _overlay_license_verifications(licenses, db_url)
    attestations = _load_attestations(db_url) if with_db_overlay else []
    return ArsenalRegistry(providers=providers, models=models, licenses=licenses, design_matrix=matrix,
                           quality_gates=gates, attestations=attestations, config_dir=cfg)
