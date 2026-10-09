"""HealthMonitor: per-provider circuit breaker + last probe results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from apex_one.core.schemas.compute import Availability


@dataclass
class ProviderHealth:
    availability: Availability = Availability.CONFIGURATION_REQUIRED
    detail: str = "not probed"
    consecutive_failures: int = 0
    open_until: datetime | None = None
    last_probe: datetime | None = None
    verified_model_ids: set[str] = field(default_factory=set)


class HealthMonitor:
    FAILURE_THRESHOLD = 3
    OPEN_SECONDS = 300

    def __init__(self) -> None:
        self.state: dict[str, ProviderHealth] = {}

    def get(self, provider_id: str) -> ProviderHealth:
        return self.state.setdefault(provider_id, ProviderHealth())

    def set_probe(self, provider_id: str, availability: Availability, detail: str,
                  model_ids: set[str] | None = None) -> None:
        h = self.get(provider_id)
        h.availability, h.detail, h.last_probe = availability, detail, datetime.now(UTC)
        if model_ids is not None:
            h.verified_model_ids = model_ids

    def record_success(self, provider_id: str) -> None:
        h = self.get(provider_id)
        h.consecutive_failures, h.open_until = 0, None

    def record_failure(self, provider_id: str) -> None:
        h = self.get(provider_id)
        h.consecutive_failures += 1
        if h.consecutive_failures >= self.FAILURE_THRESHOLD:
            h.open_until = datetime.now(UTC) + timedelta(seconds=self.OPEN_SECONDS)

    def usable(self, provider_id: str) -> tuple[bool, str]:
        h = self.get(provider_id)
        if h.open_until and h.open_until > datetime.now(UTC):
            return False, "circuit open after repeated failures"
        if h.availability != Availability.AVAILABLE:
            return False, f"{h.availability}: {h.detail}"
        return True, ""
