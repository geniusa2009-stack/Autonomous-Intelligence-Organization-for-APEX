"""Design model arsenal adapters.

Honest integration levels:
* openai_design_endpoint  — real client code for LLM-style design models (PosterCopilot, SEGA, WebGenAgent,
  OmniDocLayout-LLM, MarkupDM, PosterReward, OmniSVG, StarVector) served behind a self-hosted
  OpenAI-compatible endpoint. CONFIGURED_BUT_UNTESTED: exercised only against mocked transports here.
* research_method / agent_framework / diffusion_pipeline / benchmark_harness — NOT_YET_SUPPORTED:
  invoking raises DesignNotSupported with the reason; they remain visible to ONE Lab.
* python_package — optional dependency probe (LayerD).
* native — APEX's own engines; IMPLEMENTED and tested.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from apex_one.compute.firewall.zero_cost import ZeroCostFirewall
from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.compute import (
    Availability,
    CapabilityRequest,
    FirewallVerdict,
    IntegrationStatus,
    ModelEntry,
)


class DesignNotSupported(Exception):
    pass


@dataclass
class DesignModelResult:
    model_id: str
    role: str
    output: Any
    raw: str = ""
    research_only: bool = False
    notes: list[str] = field(default_factory=list)


ROLE_PROMPTS = {
    "page_architecture": ("You are a document layout model. Given page blocks (id, role, approx chars) on a 12-column "
                          "A4 RTL grid, return JSON {\"regions\":[{\"block_id\":str,\"col\":1-12,\"span\":1-12,"
                          "\"row\":1-24,\"rows\":1-24}]}. No overlaps."),
    "graphic_layout": ("You are a professional graphic layout model. Return JSON {\"regions\":[{\"block_id\":str,"
                       "\"col\":int,\"span\":int,\"row\":int,\"rows\":int}]} placing every block without overlap "
                       "on a 12x24 grid with a clear visual hierarchy."),
    "html_generation": ("Generate a single <section class=\"page\"> of semantic HTML for the given page spec. Keep every "
                        "<span class=\"fact\" ...> element EXACTLY as provided. No scripts, no external resources."),
    "design_repair": ("Repair the given page HTML for the stated failure. Keep every fact span unchanged. Return only HTML."),
    "design_completion": ("Complete the partial page markup. Keep fact spans unchanged. Return only HTML."),
    "design_reward": ("Score the page image for the stated intent. Return JSON {\"aesthetic\":0-100,\"typography\":0-100,"
                      "\"layout\":0-100,\"text_quality\":0-100,\"artifacts\":0-100,\"intent_fidelity\":0-100,"
                      "\"rationale\":str}."),
    "svg_generation": "Return a single clean SVG element (no text, no scripts) for the described abstract metaphor.",
    "vision_inspection": "Inspect the page image and answer the questions as JSON.",
}


class DesignModelAdapter:
    def __init__(self, model: ModelEntry, registry: ArsenalRegistry, *, transport: httpx.BaseTransport | None = None,
                 env: Mapping[str, str] | None = None):
        self.model = model
        self.registry = registry
        self.transport = transport
        self.env = env if env is not None else os.environ

    @property
    def model_id(self) -> str:
        return self.model.id

    @property
    def roles(self) -> list[str]:
        return list(self.model.capabilities.design_roles)

    @property
    def integration_status(self) -> IntegrationStatus:
        return self.model.integration_status

    def availability(self) -> tuple[Availability, str]:
        return Availability.UNAVAILABLE, f"{self.model.adapter}: not invocable"

    def eligible(self, purpose: str) -> tuple[bool, str]:
        if purpose == "production" and not self.registry.production_allowed(self.model):
            lic = self.registry.license_for(self.model)
            return False, f"licence {lic.production_state.value} (verified={lic.verified_at is not None})"
        if purpose == "research" and not self.registry.research_allowed(self.model):
            return False, "licence BLOCKED"
        return True, ""

    def invoke(self, role: str, payload: dict[str, Any], purpose: str = "production") -> DesignModelResult:
        raise DesignNotSupported(f"{self.model.id}: {self.model.integration_status.value} — {self.model.notes}")


class OpenAIDesignEndpointAdapter(DesignModelAdapter):
    def _endpoint(self) -> str | None:
        route = self.model.routes[0] if self.model.routes else None
        env_name = route.base_url_env if route else None
        return self.env.get(env_name) if env_name else None

    def availability(self) -> tuple[Availability, str]:
        route = self.model.routes[0] if self.model.routes else None
        if not self._endpoint():
            return Availability.CONFIGURATION_REQUIRED, f"set {route.base_url_env if route else 'endpoint'}"
        return Availability.AVAILABLE, "endpoint configured (untested)"

    def invoke(self, role: str, payload: dict[str, Any], purpose: str = "production") -> DesignModelResult:
        ok, why = self.eligible(purpose)
        if not ok:
            raise DesignNotSupported(f"{self.model.id} not eligible for {purpose}: {why}")
        endpoint = self._endpoint()
        if not endpoint:
            raise DesignNotSupported(f"{self.model.id}: endpoint not configured")
        route = self.model.routes[0]
        fw = ZeroCostFirewall(self.registry).evaluate(self.model, route, CapabilityRequest(task=f"design.{role}",
                                                                                           purpose=purpose))
        if fw.verdict != FirewallVerdict.ALLOW:
            raise DesignNotSupported(f"firewall: {fw.reasons}")
        ZeroCostFirewall.assert_allowed(fw, route.provider)
        content: list[dict] = [{"type": "text", "text": json.dumps(payload.get("spec", {}), ensure_ascii=False)}]
        if payload.get("image_b64"):
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{payload['image_b64']}"}})
        body = {"model": route.provider_model_id, "temperature": 0.4, "max_tokens": 4000,
                "messages": [{"role": "system", "content": ROLE_PROMPTS.get(role, "")},
                             {"role": "user", "content": content}]}
        url = endpoint.rstrip("/") + ("" if endpoint.rstrip("/").endswith("/v1") else "/v1") + "/chat/completions"
        with httpx.Client(transport=self.transport, timeout=180) as c:
            r = c.post(url, json=body)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        return DesignModelResult(self.model.id, role, parse_role_output(role, text), raw=text[:4000],
                                 research_only=purpose == "research")


def parse_role_output(role: str, text: str) -> Any:
    if role in ("page_architecture", "graphic_layout", "design_reward", "vision_inspection"):
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}
    if role in ("html_generation", "design_repair", "design_completion"):
        html = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
        return re.sub(r"\son\w+=\"[^\"]*\"", "", html)
    if role == "svg_generation":
        m = re.search(r"<svg.*?</svg>", text, re.S)
        svg = m.group(0) if m else ""
        return re.sub(r"<(script|foreignObject|text)\b.*?</\1>", "", svg, flags=re.S | re.I)
    return text


class PythonPackageAdapter(DesignModelAdapter):
    PACKAGES = {"LayerD": "layerd"}

    def availability(self) -> tuple[Availability, str]:
        pkg = self.PACKAGES.get(self.model.id, self.model.id.lower())
        if importlib.util.find_spec(pkg) is None:
            return Availability.UNAVAILABLE, f"OPTIONAL_DEPENDENCY_MISSING: python package '{pkg}' not installed"
        return Availability.AVAILABLE, "package importable (untested)"


class NativeAdapter(DesignModelAdapter):
    def availability(self) -> tuple[Availability, str]:
        return Availability.AVAILABLE, "native APEX engine"

    def invoke(self, role: str, payload: dict[str, Any], purpose: str = "production") -> DesignModelResult:
        # Native engines are invoked directly by the design pipeline (layout/compiler/svg/reward/repair).
        return DesignModelResult(self.model.id, role, None, notes=["native engine executed in-process"])


ADAPTER_CLASSES = {
    "openai_design_endpoint": OpenAIDesignEndpointAdapter,
    "python_package": PythonPackageAdapter,
    "native": NativeAdapter,
}


def build_design_adapters(registry: ArsenalRegistry, *, transport: httpx.BaseTransport | None = None,
                          env: Mapping[str, str] | None = None) -> dict[str, DesignModelAdapter]:
    out = {}
    for m in registry.models.values():
        if m.category != "design":
            continue
        cls = ADAPTER_CLASSES.get(m.adapter, DesignModelAdapter)
        out[m.id] = cls(m, registry, transport=transport, env=env)
    return out
