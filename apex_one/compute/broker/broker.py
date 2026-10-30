"""ComputeBroker — the only path from APEX code to any model."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

from apex_one import PROMPT_TEMPLATE_VERSION
from apex_one.compute.firewall.zero_cost import ZeroCostFirewall
from apex_one.compute.health import HealthMonitor
from apex_one.compute.local.supervisor import ServerSupervisor, SupervisorError, failure_kind_for
from apex_one.compute.providers import ChatMessage, ProviderAdapter, ProviderError, build_adapter
from apex_one.compute.quotas.tracker import QuotaTracker, RateLimitTracker
from apex_one.compute.registry.loader import ArsenalRegistry, load_registry
from apex_one.compute.router.capability import CapabilityRouter
from apex_one.compute.router.fallback import FallbackPlanner
from apex_one.core.schemas.compute import (
    Availability,
    CapabilityRequest,
    ModelCallRecord,
    RouteOutcome,
    RoutingDecision,
)
from apex_one.core.security import redact_text
from apex_one.core.workspace import JobWorkspace


@dataclass
class BrokerResult:
    decision: RoutingDecision
    text: str | None = None
    calls: list[ModelCallRecord] = field(default_factory=list)

    @property
    def executed(self) -> bool:
        return self.text is not None

    @property
    def model_id(self) -> str | None:
        return self.decision.model_id if self.executed else None


class ComputeBroker:
    MAX_ATTEMPTS = 4

    def __init__(self, registry: ArsenalRegistry | None = None, *, allow_mock: bool = False,
                 transport: httpx.BaseTransport | None = None, env: Mapping[str, str] | None = None,
                 adapters: dict[str, ProviderAdapter] | None = None,
                 supervisors: dict[str, ServerSupervisor] | None = None):
        self.registry = registry or load_registry()
        self.firewall = ZeroCostFirewall(self.registry)
        self.health = HealthMonitor()
        self.quotas = QuotaTracker()
        self.rate_limits = RateLimitTracker()
        self.router = CapabilityRouter(self.registry, allow_mock=allow_mock)
        self.planner = FallbackPlanner(self.router, self.firewall, self.health, self.quotas, self.rate_limits)
        self.adapters: dict[str, ProviderAdapter] = {
            pid: build_adapter(p, transport=transport, env=env) for pid, p in self.registry.providers.items()
        }
        if adapters:
            self.adapters.update(adapters)
        # model id -> supervisor of the local process serving it (health probe, restart, failure classification)
        if supervisors is None:
            from apex_one.compute.local.supervisor import active_supervisors, supervise_running_local_servers
            from apex_one.settings import get_settings

            supervisors = {**supervise_running_local_servers(
                get_settings().artifacts_dir / "logs" / "model_server_events.jsonl"), **active_supervisors()}
        self.supervisors: dict[str, ServerSupervisor] = dict(supervisors)
        self.planner.supervised = set(self.supervisors)
        # mock and unprobed providers: mock is trivially available
        self.health.set_probe("mock", Availability.AVAILABLE, "mock", {"mock-llm"})

    # ---------- health ----------
    def refresh_health(self, providers: list[str] | None = None, timeout: float = 4.0,
                       force: bool = False) -> dict[str, dict]:
        """Probe providers — through the TTL cache (compute/health_cache.py), so a blocked provider is re-checked
        periodically, not on every job. Local providers are always probed (cheap, and their state changes)."""
        from apex_one.compute import health_cache
        from apex_one.compute.providers.base import ProbeResult

        out = {}
        for pid, adapter in self.adapters.items():
            if providers and pid not in providers:
                continue
            remote = adapter.provider.kind not in ("local", "self_hosted", "mock")
            hit = health_cache.get(f"provider:{pid}") if remote and not force else None
            if hit:
                res = ProbeResult(Availability(hit["availability"]), hit["detail"] + " (cached)",
                                  set(hit["model_ids"]) if hit.get("model_ids") is not None else None)
            else:
                res = adapter.probe(timeout)
                if remote:
                    health_cache.put(f"provider:{pid}", res.availability == Availability.AVAILABLE, res.detail,
                                     availability=res.availability.value,
                                     model_ids=sorted(res.model_ids) if res.model_ids is not None else None)
            self.health.set_probe(pid, res.availability, res.detail, res.model_ids)
            out[pid] = {"availability": res.availability.value, "detail": res.detail}
            if pid == "openrouter" and res.availability == Availability.AVAILABLE:
                try:
                    for obs in adapter.price_observations():
                        self.firewall.observe_price(obs)
                except (ProviderError, httpx.HTTPError):
                    pass
        return out

    # ---------- execution ----------
    def complete(self, req: CapabilityRequest, messages: list[ChatMessage], *, job_id: str | None = None,
                 workspace: JobWorkspace | None = None, max_tokens: int = 1024, temperature: float = 0.2,
                 json_mode: bool = False, timeout: float = 60.0) -> BrokerResult:
        exclude: set[tuple[str, str]] = set()
        calls: list[ModelCallRecord] = []
        decision: RoutingDecision | None = None
        retried: set[tuple[str, str]] = set()
        for _ in range(self.MAX_ATTEMPTS):
            decision, cand, fw = self.planner.plan(req, exclude)
            if workspace:
                workspace.routing.emit("routing", **decision.model_dump(mode="json"))
            if decision.outcome != RouteOutcome.EXECUTE or cand is None:
                return BrokerResult(decision=decision, calls=calls)
            adapter = self.adapters[cand.route.provider]
            self.quotas.record(cand.route.provider)
            record = ModelCallRecord(call_id=f"MC-{uuid.uuid4().hex[:10]}", job_id=job_id, task=req.task,
                                     model_id=cand.model.id, provider=cand.route.provider,
                                     provider_model_id=cand.route.provider_model_id, outcome="ok", latency_ms=0.0,
                                     input_chars=sum(len(m.content) for m in messages), output_chars=0,
                                     estimated_cost_usd=fw.estimated_cost_usd if fw else 0.0,
                                     prompt_template_version=PROMPT_TEMPLATE_VERSION, purpose=req.purpose)
            key = (cand.model.id, cand.route.provider)
            sup = self.supervisors.get(cand.model.id)
            if sup is not None:
                try:
                    sup.before_call()
                except SupervisorError as e:
                    record.outcome, record.error, record.failure_kind = "error:unhealthy", str(e)[:300], e.kind.value
                    calls.append(record)
                    self._log_call(record, workspace)
                    exclude.add(key)
                    continue
            try:
                res = adapter.chat(fw, cand.route, messages, max_tokens=max_tokens, temperature=temperature,
                                   json_mode=json_mode, timeout=timeout)
            except ProviderError as e:
                record.outcome, record.error = f"error:{e.kind}", redact_text(str(e))[:300]
                if sup is not None:
                    kind, safe_retry = sup.after_failure(e.kind)
                else:
                    kind, safe_retry = failure_kind_for(e.kind), False
                record.failure_kind = kind.value if kind else None
                calls.append(record)
                self._log_call(record, workspace)
                if safe_retry and key not in retried:
                    # a completion is side-effect free: after a verified recovery the SAME request may run once more
                    retried.add(key)
                    continue
                if e.kind in ("rate_limited", "quota_exhausted"):
                    # not excluded: the cooldown makes the planner report WAIT/QUEUE with retry-after
                    self.rate_limits.on_rate_limited(cand.route.provider, e.retry_after)
                    if e.kind == "quota_exhausted":
                        self.quotas.mark_exhausted(cand.route.provider, e.retry_after or 3600)
                elif e.kind == "payment_required":
                    exclude.add((cand.model.id, cand.route.provider))
                    # A provider asking for payment is removed for the session: never pay.
                    self.health.set_probe(cand.route.provider, Availability.NO_FREE_ROUTE, "HTTP 402 payment required")
                else:
                    exclude.add(key)
                    if e.kind != "empty_output":    # the model said nothing; the provider itself worked
                        self.health.record_failure(cand.route.provider)
                continue
            self.health.record_success(cand.route.provider)
            record.latency_ms, record.output_chars = res.latency_ms, len(res.text)
            calls.append(record)
            self._log_call(record, workspace)
            return BrokerResult(decision=decision, text=res.text, calls=calls)
        assert decision is not None
        final = decision.model_copy(update={"outcome": RouteOutcome.DEGRADE,
                                            "reasons": decision.reasons + ["all attempts failed"]})
        return BrokerResult(decision=final, calls=calls)

    @staticmethod
    def _log_call(record: ModelCallRecord, workspace: JobWorkspace | None) -> None:
        if workspace:
            workspace.model_calls.emit("model_call", **record.model_dump(mode="json"))
