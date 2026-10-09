"""Provider adapter contract."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from apex_one.core.schemas.compute import Availability, FirewallDecision, ProviderEntry, ProviderRoute


@dataclass
class ChatMessage:
    role: str
    content: str
    images_b64_png: list[str] = field(default_factory=list)


@dataclass
class ChatResult:
    text: str
    latency_ms: float
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    def __init__(self, kind: str, message: str, retry_after: float | None = None, status: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind            # rate_limited | quota_exhausted | auth | http | network | config | payment_required
        self.retry_after = retry_after
        self.status = status


@dataclass
class ProbeResult:
    availability: Availability
    detail: str
    model_ids: set[str] | None = None


class ProviderAdapter(ABC):
    def __init__(self, provider: ProviderEntry, *, transport: httpx.BaseTransport | None = None,
                 env: Mapping[str, str] | None = None):
        self.provider = provider
        self.transport = transport
        self.env = env if env is not None else os.environ

    # ---- configuration ----
    def api_key(self) -> str | None:
        if not self.provider.api_key_env:
            return None
        return self.env.get(self.provider.api_key_env) or None

    def base_url(self, route: ProviderRoute | None = None) -> str | None:
        if route is not None and route.base_url_env:
            return self.env.get(route.base_url_env) or None
        if self.provider.base_url_env and self.env.get(self.provider.base_url_env):
            return self.env[self.provider.base_url_env]
        return self.provider.base_url

    def configured(self, route: ProviderRoute | None = None) -> tuple[bool, str]:
        if self.provider.api_key_env and not self.api_key():
            return False, f"set {self.provider.api_key_env}"
        for extra in self.provider.extra_env:
            if not self.env.get(extra):
                return False, f"set {extra}"
        if not self.base_url(route):
            env_name = (route.base_url_env if route and route.base_url_env else self.provider.base_url_env)
            return False, f"set {env_name or 'base_url'}"
        return True, ""

    def client(self, timeout: float) -> httpx.Client:
        return httpx.Client(transport=self.transport, timeout=timeout, follow_redirects=False)

    # ---- operations ----
    @abstractmethod
    def probe(self, timeout: float = 4.0) -> ProbeResult: ...

    @abstractmethod
    def chat(self, decision: FirewallDecision, route: ProviderRoute, messages: list[ChatMessage], *,
             max_tokens: int = 1024, temperature: float = 0.2, json_mode: bool = False,
             timeout: float = 60.0) -> ChatResult: ...

    def price_observations(self, timeout: float = 6.0) -> list[Any]:
        return []


def raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    retry = resp.headers.get("retry-after")
    retry_after = float(retry) if retry and retry.replace(".", "", 1).isdigit() else None
    body = resp.text[:300]
    if resp.status_code == 429:
        kind = "quota_exhausted" if "quota" in body.lower() or "exhaust" in body.lower() else "rate_limited"
        raise ProviderError(kind, body, retry_after, 429)
    if resp.status_code == 402:
        raise ProviderError("payment_required", body, None, 402)
    if resp.status_code in (401, 403):
        raise ProviderError("auth", body, None, resp.status_code)
    raise ProviderError("http", body, retry_after, resp.status_code)
