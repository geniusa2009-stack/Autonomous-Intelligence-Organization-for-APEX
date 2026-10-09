"""Google Gemini API adapter (generateContent)."""

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


class GeminiAdapter(ProviderAdapter):
    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-goog-api-key": self.api_key() or ""}

    def probe(self, timeout: float = 4.0) -> ProbeResult:
        ok, why = self.configured()
        if not ok:
            return ProbeResult(Availability.CONFIGURATION_REQUIRED, why)
        try:
            with self.client(timeout) as c:
                resp = c.get(f"{self.base_url()}/models", headers=self._headers())
            raise_for_status(resp)
            ids = {m.get("name", "").removeprefix("models/") for m in resp.json().get("models", [])}
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
        system = "\n".join(m.content for m in messages if m.role == "system")
        contents = []
        for m in messages:
            if m.role == "system":
                continue
            parts: list[dict] = [{"text": m.content}]
            parts += [{"inline_data": {"mime_type": "image/png", "data": b}} for b in m.images_b64_png]
            contents.append({"role": "model" if m.role == "assistant" else "user", "parts": parts})
        body: dict = {"contents": contents,
                      "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        t0 = time.perf_counter()
        try:
            with self.client(timeout) as c:
                resp = c.post(f"{self.base_url()}/models/{route.provider_model_id}:generateContent",
                              json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        raise_for_status(resp)
        data = resp.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError("http", f"unexpected response: {str(data)[:200]}") from e
        return ChatResult(text=text, latency_ms=(time.perf_counter() - t0) * 1000,
                          usage=data.get("usageMetadata") or {})
