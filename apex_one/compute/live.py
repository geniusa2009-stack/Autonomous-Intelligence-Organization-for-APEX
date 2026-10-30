"""Phase 14 — live provider activation. Every status here comes from a real network/process interaction.

LIVE_TESTED is assigned only when a real health call AND a real structured-output task succeeded against the
provider, with a verified $0 cost basis. Nothing is inferred from configuration alone.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from apex_one.compute.firewall.zero_cost import ZeroCostFirewall
from apex_one.compute.providers import ChatMessage, ProviderError, build_adapter
from apex_one.compute.registry.loader import ArsenalRegistry
from apex_one.core.schemas.compute import CapabilityRequest, FirewallVerdict, ModelEntry, ProviderRoute


class LiveStatus(StrEnum):
    LIVE_TESTED = "LIVE_TESTED"
    LIVE_FAILED = "LIVE_FAILED"
    CREDENTIALS_REQUIRED = "CREDENTIALS_REQUIRED"
    NO_FREE_ROUTE = "NO_FREE_ROUTE"
    NETWORK_BLOCKED = "NETWORK_BLOCKED"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    UNKNOWN = "UNKNOWN"


STRUCTURED_TASK = ("Extract facts from: 'International applicants must apply by January 15, 2027. The application fee "
                   "is US$65.' Return ONLY JSON: {\"deadline\": \"YYYY-MM-DD\", \"fee_usd\": number}")


def check_structured(text: str) -> tuple[bool, str]:
    try:
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))  # type: ignore[union-attr]
    except Exception:
        return False, "no parseable JSON"
    ok = str(data.get("deadline")) == "2027-01-15" and float(data.get("fee_usd", -1)) == 65.0
    return ok, json.dumps(data)[:200]


def network_check(url: str, timeout: float = 8.0, force: bool = False) -> tuple[bool, str]:
    """Distinguish an egress-policy denial (proxy CONNECT 403) from a reachable host. Cached with a TTL
    (compute/health_cache.py): a denied host is re-probed every few hours, not on every report or task."""
    from apex_one.compute import health_cache

    host = urlparse(url)
    root = f"{host.scheme}://{host.netloc}"
    if host.hostname in ("127.0.0.1", "localhost"):
        return True, "local"
    hit = None if force else health_cache.get(f"net:{host.netloc}")
    if hit:
        return hit["ok"], hit["detail"] + " (cached)"
    try:
        r = httpx.get(root, timeout=timeout, follow_redirects=False)
        ok, why = True, f"reachable (HTTP {r.status_code} unauthenticated)"
    except httpx.ProxyError as e:
        ok, why = False, f"egress proxy denied CONNECT to {host.netloc} ({str(e)[:80]})"
    except httpx.HTTPError as e:
        ok, why = False, f"{type(e).__name__}: {str(e)[:100]}"
    health_cache.put(f"net:{host.netloc}", ok, why)
    return ok, why


def _allow_for_local(registry: ArsenalRegistry, model: ModelEntry, route: ProviderRoute):
    fw = ZeroCostFirewall(registry)
    return fw.evaluate(model, route, CapabilityRequest(task="live.structured", purpose="research"))


def live_test_route(registry: ArsenalRegistry, model: ModelEntry, route: ProviderRoute, *,
                    env: dict[str, str] | None = None, timeout: float = 240.0) -> dict[str, Any]:
    provider = registry.providers[route.provider]
    adapter = build_adapter(provider, env=env)
    rec: dict[str, Any] = {"provider": provider.id, "model": model.id, "provider_model_id": route.provider_model_id,
                           "kind": provider.kind, "at": datetime.now(UTC).isoformat()}
    base = adapter.base_url(route) or provider.base_url or ""
    reachable, detail = network_check(base) if base else (False, "no base url")
    rec["network"] = detail
    if not reachable and provider.kind != "local":
        rec["status"] = LiveStatus.NETWORK_BLOCKED.value
        return rec
    ok, why = adapter.configured(route)
    if not ok:
        rec["status"] = LiveStatus.CREDENTIALS_REQUIRED.value
        rec["detail"] = why
        return rec
    fw = _allow_for_local(registry, model, route)
    rec["firewall"] = {"verdict": fw.verdict.value, "reasons": fw.reasons, "estimated_cost_usd": fw.estimated_cost_usd}
    if fw.verdict != FirewallVerdict.ALLOW:
        lic_reason = any("licence" in r for r in fw.reasons)
        rec["status"] = (LiveStatus.LICENSE_BLOCKED if lic_reason and len(fw.reasons) == 1
                         else LiveStatus.NO_FREE_ROUTE if any("price" in r or "free" in r for r in fw.reasons)
                         else LiveStatus.UNKNOWN).value
        return rec
    # 1. health / model listing
    t0 = time.perf_counter()
    probe = adapter.probe(timeout=10.0) if not route.base_url else _probe_route(route)
    rec["health_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    rec["health"] = {"availability": getattr(probe, "availability", probe.get("availability") if isinstance(probe, dict) else ""),
                     "detail": getattr(probe, "detail", probe.get("detail") if isinstance(probe, dict) else "")}
    ids = getattr(probe, "model_ids", None) if not isinstance(probe, dict) else probe.get("model_ids")
    rec["listed_model_ids"] = sorted(ids)[:30] if ids else []
    if rec["health"]["availability"] != "AVAILABLE":
        rec["status"] = LiveStatus.LIVE_FAILED.value
        return rec
    # 2. real structured-output task
    t0 = time.perf_counter()
    try:
        res = adapter.chat(fw, route, [ChatMessage("user", STRUCTURED_TASK)], json_mode=True, max_tokens=700,
                           temperature=0.0, timeout=timeout)
    except ProviderError as e:
        rec["status"] = LiveStatus.LIVE_FAILED.value
        rec["error"] = str(e)[:300]
        return rec
    rec["structured_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    passed, parsed = check_structured(res.text)
    rec["structured_output"] = parsed
    rec["structured_correct"] = passed
    rec["usage"] = res.usage
    rec["quota_headers"] = dict(adapter.last_headers)
    rec["cost_basis"] = ("local llama-server process on 127.0.0.1 — no billing surface" if provider.kind == "local"
                         else "free tier per attestation / live price check")
    # LIVE_TESTED means the route executed AND solved the structured task; a wrong answer is a live failure
    rec["status"] = (LiveStatus.LIVE_TESTED if passed else LiveStatus.LIVE_FAILED).value
    if not passed:
        rec["detail"] = "responded, but the structured task answer was wrong or unparseable" if res.text.strip() \
            else "empty response"
    return rec


def _probe_route(route: ProviderRoute) -> dict[str, Any]:
    try:
        r = httpx.get(route.base_url.rstrip("/") + "/models", timeout=10)  # type: ignore[union-attr]
        r.raise_for_status()
        ids = {m.get("id") for m in r.json().get("data", [])}
        return {"availability": "AVAILABLE", "detail": f"{len(ids)} model(s) served", "model_ids": ids}
    except httpx.HTTPError as e:
        return {"availability": "UNAVAILABLE", "detail": f"{type(e).__name__}", "model_ids": None}


def provider_level_report(registry: ArsenalRegistry, env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """One row per provider: network reachability + credential state (no model call)."""
    rows = []
    for pid, p in registry.providers.items():
        if pid in ("mock", "design_endpoint", "llamacpp_local"):
            continue
        adapter = build_adapter(p, env=env)
        base = adapter.base_url() or ""
        if p.kind in ("local", "self_hosted"):
            if not base:
                rows.append({"provider": pid, "status": LiveStatus.CREDENTIALS_REQUIRED.value,
                             "detail": f"no endpoint configured ({p.base_url_env})"})
                continue
            res = adapter.probe(timeout=2.0)
            rows.append({"provider": pid, "status": (LiveStatus.UNKNOWN if res.availability.value == "AVAILABLE"
                                                     else LiveStatus.LIVE_FAILED).value,
                         "detail": f"{base}: {res.detail}"})
            continue
        reachable, ndetail = network_check(base)
        ok, why = adapter.configured()
        status = LiveStatus.NETWORK_BLOCKED if not reachable else (
            LiveStatus.CREDENTIALS_REQUIRED if not ok else LiveStatus.UNKNOWN)
        rows.append({"provider": pid, "status": status.value, "network": ndetail,
                     "credentials": "present" if ok else why})
    return rows


def save_report(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
