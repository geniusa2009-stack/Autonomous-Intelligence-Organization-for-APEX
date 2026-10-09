"""Cloudflare Workers AI adapter (/ai/run/{model})."""

from __future__ import annotations

import time

import httpx

from apex_one.compute.firewall.zero_cost import ZeroCostFirewall
from apex_one.compute.providers.base import (
    ChatMessage,
    ChatResult,
    ProbeResult,
    ProviderAdapter,
    ProviderError,
    raise_for_status,
)
from apex_one.core.schemas.compute import Availability, FirewallDecision, ProviderRoute


class CloudflareAdapter(ProviderAdapter):
    def _url(self, suffix: str) -> str:
        base = (self.base_url() or "").replace("{account_id}", self.env.get("CLOUDFLARE_ACCOUNT_ID", ""))
        return f"{base}{suffix}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key() or ''}", "Content-Type": "application/json"}

    def probe(self, timeout: float = 4.0) -> ProbeResult:
        ok, why = self.configured()
        if not ok:
            return ProbeResult(Availability.CONFIGURATION_REQUIRED, why)
        acct = self.env.get("CLOUDFLARE_ACCOUNT_ID", "")
        try:
            with self.client(timeout) as c:
                resp = c.get(f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/models/search",
                             headers=self._headers())
            raise_for_status(resp)
            ids = {m.get("name") for m in resp.json().get("result", []) if isinstance(m, dict)}
            return ProbeResult(Availability.AVAILABLE, f"{len(ids)} models listed", ids)
        except ProviderError as e:
            return ProbeResult(Availability.UNAVAILABLE, str(e)[:200])
        except (httpx.HTTPError, ValueError) as e:
            return ProbeResult(Availability.UNAVAILABLE, f"network: {type(e).__name__}")

    def chat(self, decision: FirewallDecision, route: ProviderRoute, messages: list[ChatMessage], *,
             max_tokens: int = 1024, temperature: float = 0.2, json_mode: bool = False,
             timeout: float = 60.0) -> ChatResult:
        ZeroCostFirewall.assert_allowed(decision, self.provider.id)
        ok, why = self.configured(route)
        if not ok:
            raise ProviderError("config", why)
        body = {"messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens, "temperature": temperature}
        t0 = time.perf_counter()
        try:
            with self.client(timeout) as c:
                resp = c.post(self._url(f"/{route.provider_model_id}"), json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        raise_for_status(resp)
        data = resp.json()
        result = data.get("result") or {}
        text = result.get("response") or ""
        if not isinstance(text, str):
            text = str(text)
        return ChatResult(text=text, latency_ms=(time.perf_counter() - t0) * 1000, usage=result.get("usage") or {})
