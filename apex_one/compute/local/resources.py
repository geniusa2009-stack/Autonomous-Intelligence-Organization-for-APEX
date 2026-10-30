"""Local-model resource scheduler: on a 16 GB machine, compute scheduling is part of correctness.

Before a model loads, the scheduler compares its EXPECTED PEAK resident memory plus the reserves the rest of the
system needs against the memory available right now. If it does not fit, loading is refused with RESOURCE_BLOCKED
(a recorded infrastructure state) instead of letting the kernel OOM-kill something mid-benchmark.

Expected peak comes from MEASUREMENT when this exact artifact has been loaded before (the queue records peak RSS),
otherwise from an explicit estimate: weights on disk (mmapped, resident once touched) + KV cache for the configured
context + compute buffers. Only one large model is ever resident: before a load, any other llama-server holding
memory is a scheduler violation, and after an unload the process must be gone and memory must return.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

GB = 1e9

# Reserves (GB): HEADROOM beside the model, on top of what is already running. MemAvailable (the "available" side of
# the comparison) is read just before the load, so the OS, the session agent and the Python worker that are ALREADY
# resident are excluded from it; the reserves cover what will still GROW or START while the model is loaded.
# Fixed before any model was admitted under this scheduler; never tuned to admit a particular model.
RESERVES_GB = {
    "os_headroom": 0.3,             # kernel buffers / dirty pages under load
    "python_worker_growth": 0.3,    # decoded images, JSON evidence, broker state in the worker
    "evaluation_artifacts": 0.2,    # page cache for screenshots and logs written during the stage
    "model_server_overhead": 0.25,  # llama-server slots and mmproj image buffers beyond the estimate
}
RENDERER_RESERVE_GB = 0.8      # headless Chromium (Playwright) — only for stages that START a renderer
SAFETY_MARGIN_GB = 0.3
LARGE_MODEL_GB = 4.0           # "large": two such models are never resident together
UNLOADED_RSS_LIMIT_GB = 1.0    # after unload no llama-server may hold more than this
STABLE_SAMPLES, STABLE_DELTA_GB, STABLE_TIMEOUT_S = 3, 0.15, 90.0

# stages that start Chromium while the model is loaded
RENDERING_STAGES = {"pages", "golden", "robust:1024"}


class ResourceBlocked(RuntimeError):
    def __init__(self, decision: "Admission"):
        super().__init__(f"RESOURCE_BLOCKED: {decision.reason}")
        self.decision = decision


@dataclass
class Admission:
    model: str
    stage: str
    expected_peak_gb: float
    estimate_source: str
    available_gb: float
    reserve_gb: float
    reserves: dict[str, float]
    admitted: bool
    reason: str
    other_servers: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- system memory

def meminfo() -> dict[str, float]:
    """GB values from /proc/meminfo (Linux)."""
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            out[k] = int(v.split()[0]) * 1024 / GB
    except OSError:
        pass
    return out


def available_gb() -> float:
    return meminfo().get("MemAvailable", 0.0)


def used_gb() -> float:
    m = meminfo()
    return m.get("MemTotal", 0.0) - m.get("MemAvailable", 0.0)


def swap_used_gb() -> float:
    m = meminfo()
    return m.get("SwapTotal", 0.0) - m.get("SwapFree", 0.0)


def proc_rss_gb(pid: int) -> dict[str, float] | None:
    """rss / peak (VmHWM) / anonymous part. File-backed pages of the mmapped GGUF are already counted as reclaimable
    in MemAvailable; the anonymous part is what the process truly holds."""
    try:
        st = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in
              Path(f"/proc/{pid}/status").read_text().splitlines() if ln.startswith(("VmRSS", "VmHWM", "RssAnon")))}
        return {"rss_gb": round(st["VmRSS"] * 1024 / GB, 2), "peak_rss_gb": round(st["VmHWM"] * 1024 / GB, 2),
                "anon_gb": round(st.get("RssAnon", 0) * 1024 / GB, 2)}
    except (OSError, ValueError, KeyError):
        return None


def llama_servers() -> list[dict[str, Any]]:
    """Every running llama-server process with its resident memory (any port, any owner)."""
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            cmd = (d / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if cmd and cmd[0].endswith(b"llama-server"):
            mem = proc_rss_gb(int(d.name)) or {}
            port = cmd[cmd.index(b"--port") + 1].decode() if b"--port" in cmd else "?"
            out.append({"pid": int(d.name), "port": port, **mem})
    return out


# ---------------------------------------------------------------- estimates

def kv_cache_gb(spec) -> float:
    """f16 K+V for the configured context, from the GGUF architecture metadata when available."""
    try:
        from apex_one.compute.license_evidence import gguf_arch_fields
        from apex_one.settings import get_settings

        main = next(p for p in sorted(spec.dir.glob("*.gguf")) if "mmproj" not in p.name.lower())
        f = gguf_arch_fields(main, get_settings().home)
        arch = f.get("general.architecture")
        layers = int(f[f"{arch}.block_count"])
        heads_kv = f.get(f"{arch}.attention.head_count_kv") or f.get(f"{arch}.attention.head_count")
        heads_kv = int(heads_kv[0] if isinstance(heads_kv, list) else heads_kv)
        dim = int(f.get(f"{arch}.attention.key_length") or int(f[f"{arch}.embedding_length"]) // int(
            f[f"{arch}.attention.head_count"]))
        return layers * spec.ctx * heads_kv * dim * 2 * 2 / GB
    except Exception:  # noqa: BLE001 — no metadata: a conservative 1 GB per 8k context
        return 1.0 * spec.ctx / 8192


def measured_peak(spec, qstate: dict[str, Any] | None) -> float | None:
    rec = ((qstate or {}).get("done", {}).get(f"{spec.key}:ram") or {}).get("info") or {}
    return rec.get("peak_rss_gb")


def expected_peak(spec, qstate: dict[str, Any] | None = None) -> tuple[float, str]:
    m = measured_peak(spec, qstate)
    if m:
        return float(m), "measured peak RSS of this artifact"
    files = list(spec.dir.glob("*.gguf"))
    weights = sum(p.stat().st_size for p in files) / GB if files else float(spec.approx_gb)
    kv = kv_cache_gb(spec)
    return round(weights + kv + 0.6, 2), f"estimate: weights {weights:.1f} + KV {kv:.1f} + compute 0.6 GB"


# ---------------------------------------------------------------- admission

def reserve_for(stage: str) -> dict[str, float]:
    r = dict(RESERVES_GB)
    if stage in RENDERING_STAGES:
        r["renderer"] = RENDERER_RESERVE_GB
    r["safety_margin"] = SAFETY_MARGIN_GB
    return r


def admit(spec, stage: str = "load", qstate: dict[str, Any] | None = None,
          available: float | None = None, others: list[dict[str, Any]] | None = None) -> Admission:
    """Decide BEFORE loading. Refused if expected_peak + reserves > available, or another large model is resident."""
    peak, src = expected_peak(spec, qstate)
    res = reserve_for(stage)
    avail = available_gb() if available is None else available
    others = [o for o in (llama_servers() if others is None else others)
              if str(o.get("port")) != str(spec.port) and o.get("rss_gb", 0) >= UNLOADED_RSS_LIMIT_GB]
    need = peak + sum(res.values())
    if others:
        ok, why = False, f"another model server is resident ({others}); never two large models at once"
    elif need > avail:
        ok, why = False, (f"expected peak {peak:.1f} GB + reserves {sum(res.values()):.2f} GB = {need:.1f} GB > "
                          f"available {avail:.1f} GB")
    else:
        ok, why = True, f"expected peak {peak:.1f} + reserves {sum(res.values()):.2f} = {need:.1f} ≤ available {avail:.1f} GB"
    return Admission(spec.key, stage, peak, src, round(avail, 2), round(sum(res.values()), 2), res, ok, why, others)


def wait_stable(timeout: float = STABLE_TIMEOUT_S, sleep=time.sleep) -> float:
    """Wait until MemAvailable stops moving (pages released after an unload); returns the settled value."""
    vals: list[float] = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        vals.append(available_gb())
        if len(vals) >= STABLE_SAMPLES and max(vals[-STABLE_SAMPLES:]) - min(vals[-STABLE_SAMPLES:]) < STABLE_DELTA_GB:
            break
        sleep(1.0)
    return vals[-1] if vals else available_gb()


class SchedulerViolation(RuntimeError):
    pass


def assert_unloaded(port: int | None = None) -> None:
    """Operational assertion: a model marked finished while its server still holds memory is a scheduler bug."""
    held = [s for s in llama_servers() if (port is None or str(s["port"]) == str(port))
            and s.get("rss_gb", 0) >= UNLOADED_RSS_LIMIT_GB]
    if held:
        raise SchedulerViolation(f"llama-server still resident after unload: {held}")


def record(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}, default=str) + "\n")


class ScheduledServer:
    """Load → (stages) → unload, with admission, memory accounting and the unload assertion.

    Records rss_before_load (system used), rss_after_warmup (server), peak_rss, rss_after_unload (system used),
    swap_used, load_time_s, unload_time_s."""

    def __init__(self, server, *, qstate: dict[str, Any] | None = None, log_path: Path | None = None):
        self.server, self.qstate, self.log_path = server, qstate, log_path
        self.metrics: dict[str, Any] = {}

    def load(self, stage: str = "load", wait_s: float = 1200.0) -> Admission:
        # never two large models at once: another resident server makes admission fail (RESOURCE_BLOCKED). The
        # scheduler never kills a process it did not start — its owner (e.g. the queue) stops its own servers.
        dec = admit(self.server.spec, stage, self.qstate)
        if self.log_path:
            record(self.log_path, {"event": "admission", **dec.as_dict()})
        if not dec.admitted:
            raise ResourceBlocked(dec)
        self.metrics.update({"rss_before_load_gb": round(used_gb(), 2), "swap_used_gb": round(swap_used_gb(), 2),
                             "available_before_load_gb": round(available_gb(), 2)})
        t0 = time.monotonic()
        self.server.start(wait_s=wait_s)
        warmed = self.server.warm_up()
        self.metrics["load_time_s"] = round(time.monotonic() - t0, 1)
        mem = proc_rss_gb(int(self.server.pidfile.read_text())) if self.server.pidfile.exists() else None
        if mem and warmed:
            self.metrics["rss_after_warmup_gb"] = mem["rss_gb"]
        return dec

    def admit_stage(self, stage: str) -> Admission:
        """While loaded: would this stage (e.g. one that starts Chromium) still fit? Memory the server holds is added
        back to MemAvailable (anonymous part only — its file pages are already counted there), so the test is the
        same as before a load: expected_peak + stage reserves <= memory available without this model."""
        mem = proc_rss_gb(int(self.server.pidfile.read_text())) if self.server.pidfile.exists() else None
        dec = admit(self.server.spec, stage, self.qstate,
                    available=available_gb() + (mem["anon_gb"] if mem else 0.0), others=[])
        if self.log_path:
            record(self.log_path, {"event": "stage_admission", **dec.as_dict()})
        return dec

    def sample_peak(self) -> float | None:
        if not self.server.pidfile.exists():
            return None
        mem = proc_rss_gb(int(self.server.pidfile.read_text()))
        if mem:
            self.metrics["peak_rss_gb"] = max(self.metrics.get("peak_rss_gb", 0.0), mem["peak_rss_gb"])
        return self.metrics.get("peak_rss_gb")

    def unload(self) -> dict[str, Any]:
        self.sample_peak()
        t0 = time.monotonic()
        self.server.stop()
        for _ in range(60):                       # confirm the process is gone
            if not any(str(s["port"]) == str(self.server.spec.port) for s in llama_servers()):
                break
            time.sleep(0.5)
        settled = wait_stable()
        self.metrics.update({"unload_time_s": round(time.monotonic() - t0, 1), "rss_after_unload_gb": round(used_gb(), 2),
                             "available_after_unload_gb": round(settled, 2), "swap_used_gb": round(swap_used_gb(), 2)})
        if self.log_path:
            record(self.log_path, {"event": "unload", "model": self.server.spec.key, **self.metrics})
        assert_unloaded(self.server.spec.port)
        return self.metrics
