"""OpenAI-compatible chat adapter: NVIDIA NIM, Groq, OpenRouter, HF router, Ollama, llama.cpp,
MLX (mlx_lm.server), vLLM, SGLang and self-hosted design-model endpoints."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx

from apex_one.compute.firewall.zero_cost import PriceObservation, ZeroCostFirewall
from apex_one.compute.providers.base import (
    ChatMessage,
    ChatResult,
    ProbeResult,
    ProviderAdapter,
    ProviderError,
    raise_for_status,
)
from apex_one.core.schemas.compute import Availability, FirewallDecision, ProviderRoute

LOCAL_KINDS = {"local", "self_hosted"}


def _v1(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/v1") else url + "/v1"


class OpenAICompatibleAdapter(ProviderAdapter):
    def _root(self, route: ProviderRoute | None = None) -> str:
        base = self.base_url(route)
        if route is not None and route.base_url:
            return route.base_url.rstrip("/")
        if not base:
            raise ProviderError("config", "no base url configured")
        return _v1(base) if self.provider.kind in LOCAL_KINDS else base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        key = self.api_key()
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def probe(self, timeout: float = 4.0) -> ProbeResult:
        ok, why = self.configured()
        if not ok:
            if self.provider.id == "design_endpoint":
                return ProbeResult(Availability.CONFIGURATION_REQUIRED, "per-model endpoint env vars")
            return ProbeResult(Availability.CONFIGURATION_REQUIRED, why)
        try:
            with self.client(timeout) as c:
                resp = c.get(f"{self._root()}/models", headers=self._headers())
            self.last_headers = {k: v for k, v in resp.headers.items() if "ratelimit" in k.lower()}
            raise_for_status(resp)
            ids = {m.get("id") for m in resp.json().get("data", []) if isinstance(m, dict)}
            return ProbeResult(Availability.AVAILABLE, f"{len(ids)} models listed", ids)
        except ProviderError as e:
            return ProbeResult(Availability.UNAVAILABLE, str(e)[:200])
        except (httpx.HTTPError, ValueError) as e:
            return ProbeResult(Availability.UNAVAILABLE, f"network: {type(e).__name__}: {str(e)[:120]}")

    def chat(self, decision: FirewallDecision, route: ProviderRoute, messages: list[ChatMessage], *,
             max_tokens: int = 1024, temperature: float = 0.2, json_mode: bool = False,
             timeout: float = 60.0) -> ChatResult:
        ZeroCostFirewall.assert_allowed(decision, self.provider.id)
        ok, why = self.configured(route)
        if not ok:
            raise ProviderError("config", why)
        payload: dict = {
            "model": route.provider_model_id,
            "messages": [self._msg(m) for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        # transport failures are classified, never collapsed into "network" (see compute/local/supervisor.py)
        try:
            with self.client(timeout) as c:
                resp = c.post(f"{self._root(route)}/chat/completions", json=payload, headers=self._headers())
        except httpx.TimeoutException as e:
            raise ProviderError("timeout", f"{type(e).__name__} after {timeout}s") from e
        except httpx.ConnectError as e:
            raise ProviderError("connection_refused", f"{type(e).__name__}: {e}") from e
        except (httpx.RemoteProtocolError, httpx.ReadError) as e:
            raise ProviderError("disconnected", f"{type(e).__name__}: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError("network", f"{type(e).__name__}: {e}") from e
        self.last_headers = {k: v for k, v in resp.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
        raise_for_status(resp)
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ProviderError("malformed_response", f"not an OpenAI chat response: {resp.text[:200]!r}") from e
        if not isinstance(text, str):
            raise ProviderError("malformed_response", f"content is {type(text).__name__}, not text")
        if not text.strip():
            # an empty completion is an ERROR (EMPTY_OUTPUT), never an answer a checker could score as 0
            finish = (data["choices"][0].get("finish_reason") if isinstance(data["choices"][0], dict) else None)
            raise ProviderError("empty_output", f"empty completion (finish_reason={finish}, max_tokens={max_tokens})")
        return ChatResult(text=text, latency_ms=(time.perf_counter() - t0) * 1000, usage=data.get("usage") or {},
                          raw={"id": data.get("id"), "model": data.get("model")})

    @staticmethod
    def _msg(m: ChatMessage) -> dict:
        if not m.images_b64_png:
            return {"role": m.role, "content": m.content}
        parts: list[dict] = [{"type": "text", "text": m.content}]
        parts += [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}} for b in m.images_b64_png]
        return {"role": m.role, "content": parts}

    def price_observations(self, timeout: float = 6.0) -> list[PriceObservation]:
        """OpenRouter publishes per-model prices (USD per token, as strings)."""
        if self.provider.id != "openrouter":
            return []
        with self.client(timeout) as c:
            resp = c.get(f"{self._root()}/models", headers=self._headers())
        raise_for_status(resp)
        out = []
        now = datetime.now(UTC)
        for m in resp.json().get("data", []):
            p = m.get("pricing") or {}

            def per_mtok(v: object) -> float | None:
                try:
                    return float(v) * 1e6  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return None

            def flat(v: object) -> float | None:
                try:
                    return float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return None

            # per-request cost = request fee + per-image fee (vision calls send >= 1 image). A MISSING request
            # price is unknown, not free: None keeps the observation non-zero so the firewall blocks.
            req, img = flat(p.get("request")), flat(p.get("image")) if p.get("image") not in (None, "") else 0.0
            per_request = None if req is None or img is None else req + img
            out.append(PriceObservation("openrouter", m.get("id", ""), per_mtok(p.get("prompt")),
                                        per_mtok(p.get("completion")), per_request, now))
        return out


class MLXAdapter(OpenAICompatibleAdapter):
    def probe(self, timeout: float = 4.0) -> ProbeResult:
        import platform

        if not (platform.system() == "Darwin" and platform.machine() == "arm64"):
            return ProbeResult(Availability.UNAVAILABLE, "MLX requires Apple Silicon (macOS arm64)")
        return super().probe(timeout)
