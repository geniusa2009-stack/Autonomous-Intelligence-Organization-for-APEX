"""MANDATORY zero-cost test: no route with estimated_cost > 0 can ever execute.

Expected outcomes are BLOCK / FALLBACK / QUEUE / WAIT — never PAY.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from apex_one.compute.broker import ComputeBroker
from apex_one.compute.firewall import PaidRouteBlocked, PriceObservation, ZeroCostFirewall
from apex_one.compute.providers import ChatMessage, MockAdapter, ProviderError
from apex_one.core.policies.cost import COST_POLICY, policy_override_report
from apex_one.core.schemas.compute import (
    Availability,
    CapabilityRequest,
    Capabilities,
    FirewallVerdict,
    LicenseRecord,
    ModelEntry,
    Pricing,
    ProductionState,
    ProviderRoute,
    RouteOutcome,
)
from apex_one.core.schemas.mission import ComputePolicy
from apex_one.settings import reset_settings_cache

ZERO = Pricing(free_tier=True, input_per_mtok_usd=0, output_per_mtok_usd=0, per_request_usd=0)
PAID = Pricing(free_tier=False, input_per_mtok_usd=0.5, output_per_mtok_usd=1.5, per_request_usd=0)


def _verified_license(registry, lic_id="lic-test-ok"):
    registry.licenses[lic_id] = LicenseRecord(id=lic_id, license_name="Apache-2.0",
                                              production_state=ProductionState.PRODUCTION_ALLOWED,
                                              verified_at=datetime.now(UTC), verified_by="test")
    return lic_id


def _model(mid, routes, lic):
    return ModelEntry(id=mid, family="test", capabilities=Capabilities(reasoning="high", arabic="high"),
                      routes=routes, license_ref=lic, integration_status="CONFIGURED_BUT_UNTESTED")


def _attest(registry, provider, kind="free_tier_no_billing"):
    registry.attestations.append({"provider": provider, "kind": kind, "revoked": False, "expires_at": None})


REQ_PROD = CapabilityRequest(task="bench.custom", min_reasoning="high", purpose="production")
REQ_RES = CapabilityRequest(task="bench.custom", min_reasoning="high", purpose="research")


def test_policy_constants_are_zero():
    assert COST_POLICY.max_api_cost_usd == 0.0
    assert not COST_POLICY.paid_fallback_allowed
    assert not COST_POLICY.auto_billing_allowed
    assert not COST_POLICY.auto_upgrade_allowed
    assert not COST_POLICY.quota_bypass_allowed
    with pytest.raises(Exception):
        COST_POLICY.max_api_cost_usd = 5  # type: ignore[misc]


def test_env_cannot_relax_policy(monkeypatch):
    monkeypatch.setenv("APEX_PAID_FALLBACK_ALLOWED", "true")
    monkeypatch.setenv("APEX_MAX_API_COST_USD", "10")
    reset_settings_cache()
    warnings = policy_override_report()
    assert len(warnings) == 2 and all("IGNORED" in w for w in warnings)
    assert COST_POLICY.max_api_cost_usd == 0.0


def test_job_budget_must_be_zero():
    with pytest.raises(ValueError):
        ComputePolicy(api_budget_usd=0.01)


def test_paid_primary_model_blocked(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="groq", provider_model_id="paid-model", pricing=PAID)
    m = _model("paid-primary", [route], lic)
    registry.models[m.id] = m
    _attest(registry, "groq")
    _attest(registry, "groq", "terms_production")
    fw = ZeroCostFirewall(registry)
    d = fw.evaluate(m, route, REQ_PROD)
    assert d.verdict == FirewallVerdict.BLOCK
    assert any("non-zero" in r or "not marked free" in r for r in d.reasons)


def test_unknown_pricing_blocked(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="groq", provider_model_id="x", pricing=Pricing(free_tier=True))
    m = _model("unknown-price", [route], lic)
    registry.models[m.id] = m
    _attest(registry, "groq")
    d = ZeroCostFirewall(registry).evaluate(m, route, REQ_RES)
    assert d.verdict == FirewallVerdict.BLOCK and "unknown pricing" in d.reasons


def test_unattested_remote_free_route_blocked(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="groq", provider_model_id="x", pricing=ZERO.model_copy(update={"verified": True}))
    m = _model("unattested", [route], lic)
    d = ZeroCostFirewall(registry).evaluate(m, route, REQ_RES)
    assert d.verdict == FirewallVerdict.BLOCK
    assert any("price not verified" in r for r in d.reasons)


def test_provider_changes_price_blocked(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="openrouter", provider_model_id="vendor/model:free", pricing=ZERO)
    m = _model("price-change", [route], lic)
    _attest(registry, "openrouter")
    fw = ZeroCostFirewall(registry)
    assert fw.evaluate(m, route, REQ_RES).verdict == FirewallVerdict.ALLOW
    fw.observe_price(PriceObservation("openrouter", "vendor/model:free", 0.2, 0.8, 0.0, datetime.now(UTC)))
    d = fw.evaluate(m, route, REQ_RES)
    assert d.verdict == FirewallVerdict.BLOCK
    assert any("NON-ZERO" in r for r in d.reasons)


def test_openrouter_requires_free_variant(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="openrouter", provider_model_id="vendor/model", pricing=ZERO)
    m = _model("or-nonfree", [route], lic)
    _attest(registry, "openrouter")
    d = ZeroCostFirewall(registry).evaluate(m, route, REQ_RES)
    assert d.verdict == FirewallVerdict.BLOCK


def test_unknown_license_blocked_for_production(registry):
    route = ProviderRoute(provider="ollama", provider_model_id="m", pricing=ZERO.model_copy(update={"verified": True}))
    m = _model("unknown-lic", [route], "lic-unknown")
    registry.models[m.id] = m
    d = ZeroCostFirewall(registry).evaluate(m, route, REQ_PROD)
    assert d.verdict == FirewallVerdict.BLOCK
    assert any("not production-allowed" in r for r in d.reasons)
    # ...but ONE Lab research use of an UNKNOWN (not BLOCKED) licence is permitted on a local route
    assert ZeroCostFirewall(registry).evaluate(m, route, REQ_RES).verdict == FirewallVerdict.ALLOW


def test_request_with_budget_blocked(registry):
    route = ProviderRoute(provider="mock", provider_model_id="mock-llm", pricing=ZERO)
    m = registry.models["mock-llm"]
    d = ZeroCostFirewall(registry).evaluate(m, route, REQ_RES.model_copy(update={"max_cost_usd": 1.0}))
    assert d.verdict == FirewallVerdict.BLOCK


def test_adapter_refuses_without_allow(registry):
    adapter = MockAdapter(registry.providers["mock"])
    route = registry.models["mock-llm"].routes[0]
    with pytest.raises(PaidRouteBlocked):
        adapter.chat(None, route, [ChatMessage("user", "x")])  # type: ignore[arg-type]


def test_paid_fallback_never_used_quota_exhausted(registry):
    """Free primary hits quota (429) -> paid fallback exists -> broker must NOT pay."""
    lic = _verified_license(registry)
    free_route = ProviderRoute(provider="groq", provider_model_id="free-model", pricing=ZERO)
    paid_route = ProviderRoute(provider="nvidia_nim", provider_model_id="paid-model", pricing=PAID)
    m = _model("dual-route", [free_route, paid_route], lic)
    registry.models = {"dual-route": m}
    _attest(registry, "groq")
    _attest(registry, "nvidia_nim")

    calls = {"groq": 0, "nvidia_nim": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "groq" in host:
            calls["groq"] += 1
            return httpx.Response(429, headers={"retry-after": "3600"}, json={"error": "quota exhausted"})
        calls["nvidia_nim"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "PAID!"}}]})

    env = {"GROQ_API_KEY": "gsk_test_not_real_000000000", "NVIDIA_API_KEY": "nvapi-test-not-real-0000000"}
    broker = ComputeBroker(registry, transport=httpx.MockTransport(handler), env=env)
    for p in ("groq", "nvidia_nim"):
        broker.health.set_probe(p, Availability.AVAILABLE, "test")
    res = broker.complete(REQ_RES, [ChatMessage("user", "hi")])
    assert calls["nvidia_nim"] == 0, "paid route must never be called"
    assert not res.executed
    assert res.decision.outcome in (RouteOutcome.QUEUE, RouteOutcome.WAIT, RouteOutcome.LOCAL_FALLBACK,
                                    RouteOutcome.DEGRADE)
    assert res.decision.outcome == RouteOutcome.QUEUE   # no native engine for bench.custom; long retry-after


def test_self_imposed_quota_produces_wait(registry):
    _attest(registry, "mock")
    broker = ComputeBroker(registry, allow_mock=True)
    registry.providers["mock"].self_imposed_limits.requests_per_minute = 1
    req = CapabilityRequest(task="bench.custom", purpose="research")
    assert broker.complete(req, [ChatMessage("user", "1")]).executed
    second = broker.complete(req, [ChatMessage("user", "2")])
    assert not second.executed and second.decision.outcome == RouteOutcome.WAIT


def test_payment_required_removes_provider(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="groq", provider_model_id="m", pricing=ZERO)
    registry.models = {"m": _model("m", [route], lic)}
    _attest(registry, "groq")
    transport = httpx.MockTransport(lambda r: httpx.Response(402, json={"error": "upgrade required"}))
    broker = ComputeBroker(registry, transport=transport, env={"GROQ_API_KEY": "gsk_test_not_real_0000"})
    broker.health.set_probe("groq", Availability.AVAILABLE, "t")
    res = broker.complete(REQ_RES, [ChatMessage("user", "x")])
    assert not res.executed
    assert broker.health.get("groq").availability == Availability.NO_FREE_ROUTE


def test_exhaustive_real_registry_never_allows_nonzero(registry):
    """Every (model, route, purpose, privacy) in the shipped registry: ALLOW implies exactly $0,
    and with no attestations, NO remote route is ever allowed."""
    fw = ZeroCostFirewall(registry)
    allowed_remote = []
    for m in registry.models.values():
        for r in m.routes:
            for purpose in ("production", "research"):
                for privacy in ("public", "private-student-data"):
                    req = CapabilityRequest(task="t", purpose=purpose, privacy_class=privacy)
                    d = fw.evaluate(m, r, req)
                    if d.verdict == FirewallVerdict.ALLOW:
                        assert d.estimated_cost_usd == 0.0
                        if registry.providers[r.provider].kind == "remote_free":
                            allowed_remote.append((m.id, r.provider))
    assert allowed_remote == []


def test_production_never_routes_to_mock(registry):
    broker = ComputeBroker(registry, allow_mock=True)
    res = broker.complete(CapabilityRequest(task="editorial.write", purpose="production"),
                          [ChatMessage("user", "x")])
    assert res.decision.outcome == RouteOutcome.LOCAL_FALLBACK
    assert not res.executed


def test_private_student_data_not_sent_remote(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="groq", provider_model_id="m", pricing=ZERO)
    m = _model("m", [route], lic)
    _attest(registry, "groq")
    d = ZeroCostFirewall(registry).evaluate(m, route, REQ_RES.model_copy(update={"privacy_class": "private-student-data"}))
    assert d.verdict == FirewallVerdict.BLOCK


def test_expired_attestation_does_not_count(registry):
    lic = _verified_license(registry)
    route = ProviderRoute(provider="groq", provider_model_id="m", pricing=ZERO)
    m = _model("m", [route], lic)
    registry.attestations.append({"provider": "groq", "kind": "free_tier_no_billing", "revoked": False,
                                  "expires_at": datetime.now(UTC) - timedelta(days=1)})
    assert ZeroCostFirewall(registry).evaluate(m, route, REQ_RES).verdict == FirewallVerdict.BLOCK


def test_provider_error_kinds():
    from apex_one.compute.providers.base import raise_for_status

    with pytest.raises(ProviderError) as e:
        raise_for_status(httpx.Response(402, text="pay"))
    assert e.value.kind == "payment_required"
