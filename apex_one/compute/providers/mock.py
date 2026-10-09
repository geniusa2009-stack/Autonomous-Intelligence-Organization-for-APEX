"""Deterministic mock provider for tests and offline benchmarks. Never production."""

from __future__ import annotations

import json
from collections.abc import Callable

from apex_one.compute.firewall.zero_cost import ZeroCostFirewall
from apex_one.compute.providers.base import ChatMessage, ChatResult, ProbeResult, ProviderAdapter, ProviderError
from apex_one.core.schemas.compute import Availability, FirewallDecision, ProviderRoute

Script = Callable[[list[ChatMessage], bool], str]


def _default_script(messages: list[ChatMessage], json_mode: bool) -> str:
    last = messages[-1].content if messages else ""
    if json_mode:
        return json.dumps({"echo": last[:200], "mock": True}, ensure_ascii=False)
    return f"[mock] {last[:200]}"


class MockAdapter(ProviderAdapter):
    def __init__(self, provider, *, script: Script | None = None, fail_with: ProviderError | None = None, **kw):
        super().__init__(provider, **kw)
        self.script = script or _default_script
        self.fail_with = fail_with
        self.calls: list[list[ChatMessage]] = []

    def probe(self, timeout: float = 4.0) -> ProbeResult:
        return ProbeResult(Availability.AVAILABLE, "mock", {"mock-llm"})

    def chat(self, decision: FirewallDecision, route: ProviderRoute, messages: list[ChatMessage], *,
             max_tokens: int = 1024, temperature: float = 0.2, json_mode: bool = False,
             timeout: float = 60.0) -> ChatResult:
        ZeroCostFirewall.assert_allowed(decision, self.provider.id)
        self.calls.append(messages)
        if self.fail_with:
            raise self.fail_with
        return ChatResult(text=self.script(messages, json_mode), latency_ms=0.1)
