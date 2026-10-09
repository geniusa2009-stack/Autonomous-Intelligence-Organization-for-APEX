"""QuotaTracker (APEX self-imposed throttles) and RateLimitTracker (provider 429s).

Quota exhaustion never triggers paid fallback; it produces WAIT/QUEUE decisions.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apex_one.core.schemas.compute import ProviderEntry


@dataclass
class QuotaCheck:
    ok: bool
    retry_after_seconds: float = 0.0
    reason: str = ""


class QuotaTracker:
    def __init__(self, clock=None):
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._exhausted_until: dict[str, datetime] = {}

    def _prune(self, provider: str, now: datetime) -> None:
        q = self._events[provider]
        while q and now - q[0] > timedelta(days=1):
            q.popleft()

    def check(self, provider: ProviderEntry) -> QuotaCheck:
        now = self._clock()
        with self._lock:
            until = self._exhausted_until.get(provider.id)
            if until and until > now:
                return QuotaCheck(False, (until - now).total_seconds(), "provider reported quota exhausted")
            self._prune(provider.id, now)
            q = self._events[provider.id]
            lim = provider.self_imposed_limits
            if lim.requests_per_minute is not None:
                recent = [t for t in q if now - t <= timedelta(minutes=1)]
                if len(recent) >= lim.requests_per_minute:
                    wait = 60 - (now - recent[0]).total_seconds()
                    return QuotaCheck(False, max(wait, 1.0), "self-imposed per-minute limit reached")
            if lim.requests_per_day is not None and len(q) >= lim.requests_per_day:
                wait = 86400 - (now - q[0]).total_seconds()
                return QuotaCheck(False, max(wait, 60.0), "self-imposed daily limit reached")
        return QuotaCheck(True)

    def record(self, provider_id: str) -> None:
        with self._lock:
            self._events[provider_id].append(self._clock())

    def mark_exhausted(self, provider_id: str, seconds: float) -> None:
        with self._lock:
            self._exhausted_until[provider_id] = self._clock() + timedelta(seconds=seconds)

    def snapshot(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._events.items()}


class RateLimitTracker:
    """Tracks provider-signalled rate limits (HTTP 429 + Retry-After) as cooldowns."""

    def __init__(self, clock=None):
        self._clock = clock or (lambda: datetime.now(UTC))
        self._cooldown: dict[str, datetime] = {}

    def on_rate_limited(self, provider_id: str, retry_after: float | None) -> None:
        self._cooldown[provider_id] = self._clock() + timedelta(seconds=retry_after or 30.0)

    def cooldown_remaining(self, provider_id: str) -> float:
        until = self._cooldown.get(provider_id)
        if not until:
            return 0.0
        return max(0.0, (until - self._clock()).total_seconds())
