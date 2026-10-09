import json
from datetime import UTC, datetime

import httpx

from apex_one.compute.broker import ComputeBroker
from apex_one.compute.firewall import ZeroCostFirewall
from apex_one.compute.hardware import detect_hardware, plan_acquisition
from apex_one.compute.providers import ChatMessage, build_adapter
from apex_one.compute.router import CapabilityRouter
from apex_one.core.schemas.compute import (
    Availability,
    CapabilityRequest,
    FirewallDecision,
    FirewallVerdict,
    Level,
    RouteOutcome,
)


def _allow(provider):
    return FirewallDecision(verdict=FirewallVerdict.ALLOW, model_id="x", provider=provider, estimated_cost_usd=0.0)


def test_openai_adapter_probe_and_chat(registry):
    seen = {}

    def handler(req: httpx.Request):
        seen.setdefault("auth", req.headers.get("authorization"))
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-20b"}]})
        body = json.loads(req.content)
        seen["body"] = body
        return httpx.Response(200, json={"choices": [{"message": {"content": "اهلا"}}], "usage": {"total_tokens": 3}})

    a = build_adapter(registry.providers["groq"], transport=httpx.MockTransport(handler),
                      env={"GROQ_API_KEY": "fake-groq-key-for-tests"})
    probe = a.probe()
    assert probe.availability == Availability.AVAILABLE and "openai/gpt-oss-20b" in probe.model_ids
    route = registry.models["gpt-oss-20b"].routes[0]
    res = a.chat(_allow("groq"), route, [ChatMessage("user", "hi")], json_mode=True)
    assert res.text == "اهلا"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["auth"].startswith("Bearer ")


def test_unconfigured_provider_reports_configuration_required(registry):
    a = build_adapter(registry.providers["nvidia_nim"], env={})
    assert a.probe().availability == Availability.CONFIGURATION_REQUIRED


def test_local_adapter_normalizes_v1(registry):
    paths = []

    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200, json={"data": []})

    a = build_adapter(registry.providers["ollama"], transport=httpx.MockTransport(handler), env={})
    assert a.probe().availability == Availability.AVAILABLE
    assert paths == ["/v1/models"]


def test_gemini_adapter(registry):
    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "models/gemini-flash-latest"}]})
        body = json.loads(req.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "sys"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    a = build_adapter(registry.providers["gemini"], transport=httpx.MockTransport(handler),
                      env={"GEMINI_API_KEY": "fake-gemini-key-for-tests"})
    assert a.probe().availability == Availability.AVAILABLE
    route = registry.models["gemini-flash-free"].routes[0]
    assert a.chat(_allow("gemini"), route, [ChatMessage("system", "sys"), ChatMessage("user", "u")]).text == "ok"


def test_cloudflare_adapter(registry):
    def handler(req):
        assert "/accounts/acc123/ai/run/@cf/openai/gpt-oss-20b" in req.url.path
        return httpx.Response(200, json={"result": {"response": "cf-ok"}})

    a = build_adapter(registry.providers["cloudflare"], transport=httpx.MockTransport(handler),
                      env={"CLOUDFLARE_API_TOKEN": "t" * 20, "CLOUDFLARE_ACCOUNT_ID": "acc123"})
    route = [r for r in registry.models["gpt-oss-20b"].routes if r.provider == "cloudflare"][0]
    assert a.chat(_allow("cloudflare"), route, [ChatMessage("user", "x")]).text == "cf-ok"


def test_openrouter_price_observations_feed_firewall(registry):
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"id": "openai/gpt-oss-20b:free", "pricing": {"prompt": "0", "completion": "0", "request": "0"}},
            {"id": "openai/gpt-oss-120b:free", "pricing": {"prompt": "0.0000002", "completion": "0", "request": "0"}},
        ]})

    a = build_adapter(registry.providers["openrouter"], transport=httpx.MockTransport(handler),
                      env={"OPENROUTER_API_KEY": "fake-openrouter-key-for-tests"})
    obs = {o.provider_model_id: o for o in a.price_observations()}
    assert obs["openai/gpt-oss-20b:free"].is_zero()
    assert not obs["openai/gpt-oss-120b:free"].is_zero()
    fw = ZeroCostFirewall(registry, list(obs.values()))
    req = CapabilityRequest(task="t", purpose="research")
    m20, m120 = registry.models["gpt-oss-20b"], registry.models["gpt-oss-120b"]
    r20 = [r for r in m20.routes if r.provider == "openrouter"][0]
    r120 = [r for r in m120.routes if r.provider == "openrouter"][0]
    assert fw.evaluate(m20, r20, req).verdict == FirewallVerdict.ALLOW       # fresh live $0 check
    assert fw.evaluate(m120, r120, req).verdict == FirewallVerdict.BLOCK     # live non-zero price


def test_capability_routing_is_by_capability(registry):
    router = CapabilityRouter(registry)
    vision = router.candidates(CapabilityRequest(task="vision", vision=True))
    assert vision and all(c.model.capabilities.vision for c in vision)
    arabic = router.candidates(CapabilityRequest(task="w", min_arabic=Level.HIGH))
    assert all(Level(c.model.capabilities.arabic).rank >= Level.HIGH.rank for c in arabic)
    design = router.candidates(CapabilityRequest(task="d", design_role="graphic_layout"))
    assert {c.model.id for c in design} >= {"PosterCopilot-7B"}


def test_broker_logs_routing_and_calls(registry, tmp_path):
    from apex_one.core.workspace import JobWorkspace

    ws = JobWorkspace("J-test", root=tmp_path)
    b = ComputeBroker(registry, allow_mock=True)
    res = b.complete(CapabilityRequest(task="x", purpose="research"), [ChatMessage("user", "q")], workspace=ws,
                     job_id="J-test")
    assert res.executed and res.decision.outcome == RouteOutcome.EXECUTE
    assert ws.routing.read() and ws.model_calls.read()[0]["model_id"] == "mock-llm"


def test_hardware_and_acquisition_plan_never_downloads(registry):
    hw = detect_hardware()
    advice = plan_acquisition(registry, hw)
    assert advice and all(a.verdict for a in advice)
    assert hw.ram_gb is None or hw.ram_gb > 0


def test_health_circuit_breaker():
    from apex_one.compute.health import HealthMonitor

    h = HealthMonitor()
    h.set_probe("p", Availability.AVAILABLE, "ok")
    for _ in range(3):
        h.record_failure("p")
    ok, why = h.usable("p")
    assert not ok and "circuit" in why


def test_benchmark_suite_runs_on_mock(registry, tmp_path):
    from apex_one.compute.benchmark import run_model_benchmark

    b = ComputeBroker(registry, allow_mock=True)
    out = run_model_benchmark(b, tmp_path / "scores.json")
    assert set(out) == {"normalize_date", "extract_fee", "egyptian_rewrite"}
    assert all(v["status"] == "MEASURED" for v in out.values())
    _ = datetime.now(UTC)
