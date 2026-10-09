"""Provider adapter factory."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from apex_one.compute.providers.base import ChatMessage, ChatResult, ProbeResult, ProviderAdapter, ProviderError
from apex_one.compute.providers.cloudflare import CloudflareAdapter
from apex_one.compute.providers.gemini import GeminiAdapter
from apex_one.compute.providers.mock import MockAdapter
from apex_one.compute.providers.openai_compatible import MLXAdapter, OpenAICompatibleAdapter
from apex_one.core.schemas.compute import ProviderEntry


def build_adapter(provider: ProviderEntry, *, transport: httpx.BaseTransport | None = None,
                  env: Mapping[str, str] | None = None) -> ProviderAdapter:
    if provider.api_style == "mock":
        return MockAdapter(provider, transport=transport, env=env)
    if provider.api_style == "gemini":
        return GeminiAdapter(provider, transport=transport, env=env)
    if provider.api_style == "cloudflare":
        return CloudflareAdapter(provider, transport=transport, env=env)
    if provider.id == "mlx":
        return MLXAdapter(provider, transport=transport, env=env)
    if provider.api_style == "openai":
        return OpenAICompatibleAdapter(provider, transport=transport, env=env)
    raise ValueError(f"no adapter for api_style={provider.api_style}")


__all__ = ["ChatMessage", "ChatResult", "ProbeResult", "ProviderAdapter", "ProviderError", "build_adapter",
           "MockAdapter", "OpenAICompatibleAdapter", "GeminiAdapter", "CloudflareAdapter", "MLXAdapter"]
