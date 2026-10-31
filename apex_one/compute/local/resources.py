"""Local-model resource scheduler: on a 16 GB machine, compute scheduling is part of correctness.

Every stage that needs a local model (or Chromium, or both) is admitted BEFORE it starts. The scheduler answers
ADMIT / DEFER / RESOURCE_BLOCKED with an explicit reason; it never launches something and hopes. A clean
RESOURCE_BLOCKED is a successful scheduling decision, not a failed benchmark.

need     = expected model peak (measured; else estimate x safety multiplier) + the stage profile's reserves
headroom = MemAvailable (with this model's own anonymous memory added back if it is already loaded) - need
ADMIT             headroom satisfies the MODE's rule (below)
DEFER             it does not fit NOW, but would on this machine once a transient condition clears (another server
                  still resident, memory not yet recovered after an unload) — retry later, do not start
RESOURCE_BLOCKED  it cannot fit on this machine even when idle — do not start; try another strategy

Modes (both fixed before any model was admitted under them; never tuned to admit a model):
  EVALUATION_MODE  one controlled benchmark process, nothing else scheduled: headroom >= 0.5 GB. Enough to absorb
                   allocator jitter; acceptable ONLY because a failure there costs a benchmark sample, not a job.
  PRODUCTION_MODE  headroom >= 2.0 GB AND >= 12 % of MemTotal. Production adds what evaluation never sees: a second
                   job's worker, longer uptimes (fragmentation, page-cache churn of the mmapped weights), larger
                   real pages. 2.0 GB covers one extra worker + one Chromium spike on this machine; the percentage
                   keeps the rule meaningful on bigger machines where 2 GB would be noise.

Stage profiles (StageResourceProfile) — what runs BESIDE the model during the stage. The Chromium reserve is
derived from measurement: the headless Chromium of the design bench peaked at 0.50 GB (2026-10-31 memory trace,
docs/evidence/server_gemma12b_pages_memtrace.txt); the reserve is 2x that (multi-page renders, screenshots).

A run that survives only by swapping is RESOURCE_DEGRADED (never production-safe); after every unload the memory
must recover (memory_recovery_ratio >= 0.95) or the result is MEMORY_LEAK_OR_RESIDUAL and no next large model loads.
"""

from __future__ import annotations

import functools
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

GB = 1e9

EVALUATION_MODE, PRODUCTION_MODE = "EVALUATION_MODE", "PRODUCTION_MODE"
MODE_RULES = {EVALUATION_MODE: {"min_headroom_gb": 0.5, "min_headroom_pct": 0.0},
              PRODUCTION_MODE: {"min_headroom_gb": 2.0, "min_headroom_pct": 0.12}}
BASE_RESERVES_GB = {"os": 0.3, "python_worker": 0.3, "evaluation_artifacts": 0.2}
MODEL_SERVER_OVERHEAD_GB = 0.25
CHROMIUM_MEASURED_PEAK_GB = 0.50
DEFAULT_SAFETY_MULTIPLIER = 1.25          # unmeasured model, no measured sibling: estimates under-shot by 16 % (Gemma 12B)
RECOVERY_MIN_RATIO = 0.95
DEGRADED_SWAP_GB = 0.25
DEGRADED_LATENCY_RATIO = 3.0
UNLOADED_RSS_LIMIT_GB = 1.0
STABLE_SAMPLES, STABLE_DELTA_GB, STABLE_TIMEOUT_S = 3, 0.15, 90.0


class Decision(StrEnum):
    ADMIT = "ADMIT"
    DEFER = "DEFER"
    RESOURCE_BLOCKED = "RESOURCE_BLOCKED"


@dataclass(frozen=True)
class StageResourceProfile:
    name: str
    model_resident: bool          # the model server is loaded during the stage
    renderer_gb: float = 0.0      # Chromium / Playwright beside it
    image_buffers_gb: float = 0.0 # decoded screenshots, base64 payloads, mmproj image batches
    pdf_gb: float = 0.0           # PDF engine

    def reserves(self) -> dict[str, float]:
        r = dict(BASE_RESERVES_GB)
        if self.model_resident:
            r["model_server_overhead"] = MODEL_SERVER_OVERHEAD_GB
        for k in ("renderer_gb", "image_buffers_gb", "pdf_gb"):
            v = getattr(self, k)
            if v:
                r[k.removesuffix("_gb")] = v
        return r


PROFILES = {
    "TEXT_ONLY_MODEL_CALL": StageResourceProfile("TEXT_ONLY_MODEL_CALL", True, renderer_gb=0.05),
    "VISION_PAGE_JUDGING": StageResourceProfile("VISION_PAGE_JUDGING", True, image_buffers_gb=0.3),
    "PLAYWRIGHT_RENDER": StageResourceProfile("PLAYWRIGHT_RENDER", False, renderer_gb=2 * CHROMIUM_MEASURED_PEAK_GB),
    "PDF_EXPORT": StageResourceProfile("PDF_EXPORT", False, renderer_gb=2 * CHROMIUM_MEASURED_PEAK_GB, pdf_gb=0.5),
    "MODEL_PLUS_CHROMIUM": StageResourceProfile("MODEL_PLUS_CHROMIUM", True, renderer_gb=2 * CHROMIUM_MEASURED_PEAK_GB,
                                                image_buffers_gb=0.3),
}
# queue step -> what actually runs beside the model during it
STEP_PROFILE = {
    "live": "TEXT_ONLY_MODEL_CALL", "council": "VISION_PAGE_JUDGING", "vector": "TEXT_ONLY_MODEL_CALL",
    "rerun": "TEXT_ONLY_MODEL_CALL", "rerun_vector": "TEXT_ONLY_MODEL_CALL", "calib": "VISION_PAGE_JUDGING",
    "pcalib": "VISION_PAGE_JUDGING", "invest": "VISION_PAGE_JUDGING", "gdb": "VISION_PAGE_JUDGING",
    "pages": "MODEL_PLUS_CHROMIUM", "pages:generate": "TEXT_ONLY_MODEL_CALL", "pages:render": "PLAYWRIGHT_RENDER",
    "robust:1024": "MODEL_PLUS_CHROMIUM", "golden": "MODEL_PLUS_CHROMIUM", "load": "TEXT_ONLY_MODEL_CALL",
}


def profile_for(step: str) -> StageResourceProfile:
    name = STEP_PROFILE.get(step) or ("VISION_PAGE_JUDGING" if step.startswith("robust:") else "TEXT_ONLY_MODEL_CALL")
    return PROFILES[name]


class ResourceBlocked(RuntimeError):
    def __init__(self, decision: "Admission"):
        super().__init__(f"{decision.decision}: {decision.reason}")
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
    decision: str = Decision.ADMIT
    mode: str = EVALUATION_MODE
    profile: str = ""
    headroom_gb: float = 0.0
    required_headroom_gb: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- system memory

def meminfo() -> dict[str, float]:
    """GB (10^9 bytes) values from /proc/meminfo (Linux)."""
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


def total_gb() -> float:
    return meminfo().get("MemTotal", 0.0)


def used_gb() -> float:
    m = meminfo()
    return m.get("MemTotal", 0.0) - m.get("MemAvailable", 0.0)


def swap_used_gb() -> float:
    m = meminfo()
    return m.get("SwapTotal", 0.0) - m.get("SwapFree", 0.0)


def proc_rss_gb(pid: int) -> dict[str, float] | None:
    """rss / peak (VmHWM) / anonymous part / major page faults. File-backed pages of the mmapped GGUF are already
    counted as reclaimable in MemAvailable; the anonymous part is what the process truly holds."""
    try:
        st = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in
              Path(f"/proc/{pid}/status").read_text().splitlines() if ln.startswith(("VmRSS", "VmHWM", "RssAnon")))}
        out = {"rss_gb": round(st["VmRSS"] * 1024 / GB, 2), "peak_rss_gb": round(st["VmHWM"] * 1024 / GB, 2),
               "anon_gb": round(st.get("RssAnon", 0) * 1024 / GB, 2)}
        try:
            stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            out["major_faults"] = int(stat[9])
        except (OSError, IndexError, ValueError):
            pass
        return out
    except (OSError, ValueError, KeyError):
        return None


def llama_servers() -> list[dict[str, Any]]:
    """Every running llama-server process with its resident memory (read-only inspection of /proc)."""
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


# ---------------------------------------------------------------- estimates (persisted correction factors)

def estimates_path() -> Path:
    from apex_one.settings import get_settings

    return get_settings().artifacts_dir / "bench" / "resource_estimates.json"


def load_estimates() -> dict[str, Any]:
    try:
        return json.loads(estimates_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def family(spec) -> str:
    tag = str(getattr(spec, "registry_model", "") or getattr(spec, "key", ""))
    for f in ("qwen3-vl", "qwen-vl", "gemma", "nemotron", "gpt-oss"):
        if f in tag:
            return "qwen3-vl" if f == "qwen-vl" else f
    return tag


@functools.lru_cache(maxsize=64)
def _arch_fields(path: str, size: int) -> dict[str, Any]:
    from apex_one.compute.license_evidence import gguf_arch_fields
    from apex_one.settings import get_settings

    return gguf_arch_fields(Path(path), get_settings().home)


def kv_cache_gb(spec) -> float:
    """f16 K+V for the configured context, from the GGUF architecture metadata when available (parsed once per
    file — the header of a multi-GB GGUF is not re-read on every admission)."""
    try:
        main = next(p for p in sorted(spec.dir.glob("*.gguf")) if "mmproj" not in p.name.lower())
        f = _arch_fields(str(main), main.stat().st_size)
        arch = f.get("general.architecture")
        layers = int(f[f"{arch}.block_count"])
        heads_kv = f.get(f"{arch}.attention.head_count_kv") or f.get(f"{arch}.attention.head_count")
        heads_kv = int(heads_kv[0] if isinstance(heads_kv, list) else heads_kv)
        dim = int(f.get(f"{arch}.attention.key_length") or int(f[f"{arch}.embedding_length"]) // int(
            f[f"{arch}.attention.head_count"]))
        return layers * spec.ctx * heads_kv * dim * 2 * 2 / GB
    except Exception:  # noqa: BLE001 — no metadata: a conservative 1 GB per 8k context
        return 1.0 * spec.ctx / 8192


def raw_estimate(spec) -> tuple[float, str]:
    files = list(spec.dir.glob("*.gguf"))
    weights = sum(p.stat().st_size for p in files) / GB if files else float(spec.approx_gb)
    kv = kv_cache_gb(spec)
    return round(weights + kv + 0.6, 2), f"weights {weights:.1f} + KV {kv:.1f} + compute 0.6 GB"


def record_estimate(spec, measured_peak: float) -> dict[str, Any]:
    """Persist estimated vs measured peak for this artifact: future admissions use the measurement, and unmeasured
    siblings of the same family use its correction factor."""
    est, _ = raw_estimate(spec)
    data = load_estimates()
    data[spec.key] = {"family": family(spec), "estimated_peak_gb": est, "measured_peak_gb": measured_peak,
                      "prediction_error_gb": round(measured_peak - est, 2),
                      "ratio": round(measured_peak / est, 3) if est else None,
                      "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p = estimates_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data[spec.key]


def safety_multiplier(spec, estimates: dict[str, Any] | None = None) -> tuple[float, str]:
    """Measured ratio of a same-family sibling if one exists (never below 1.0); else the larger of the default and
    the worst ratio observed on any model."""
    estimates = load_estimates() if estimates is None else estimates
    fam = [v["ratio"] for k, v in estimates.items() if v.get("ratio") and v.get("family") == family(spec)
           and k != spec.key]
    if fam:
        return max(1.0, max(fam)), f"same-family measured ratio ({family(spec)})"
    allr = [v["ratio"] for v in estimates.values() if v.get("ratio")]
    return max([DEFAULT_SAFETY_MULTIPLIER] + allr), "conservative default (no measured sibling)"


def measured_peak(spec, qstate: dict[str, Any] | None) -> float | None:
    rec = ((qstate or {}).get("done", {}).get(f"{spec.key}:ram") or {}).get("info") or {}
    return rec.get("peak_rss_gb") or (load_estimates().get(spec.key) or {}).get("measured_peak_gb")


def expected_peak(spec, qstate: dict[str, Any] | None = None) -> tuple[float, str]:
    m = measured_peak(spec, qstate)
    if m:
        return float(m), "measured peak RSS of this artifact"
    est, how = raw_estimate(spec)
    mult, why = safety_multiplier(spec)
    return round(est * mult, 2), f"estimate {est:.1f} GB ({how}) x {mult:.2f} ({why})"


# ---------------------------------------------------------------- admission

def _cycles() -> list[dict[str, Any]]:
    try:
        from apex_one.settings import get_settings

        q = json.loads((get_settings().artifacts_dir / "bench" / "queue_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c for v in q.get("done", {}).values() if isinstance(v, dict) and isinstance(v.get("info"), dict)
            for c in (v["info"].get("cycles") or [])]


def baseline_capacity_gb() -> float:
    """Memory available on this machine with no model loaded: the best MemAvailable recorded before a load, else
    95 % of MemTotal."""
    best = max((v.get("available_before_load_gb", 0.0) for v in _cycles()), default=0.0)
    return best or round(total_gb() * 0.95, 2)


def required_headroom(mode: str, total: float | None = None) -> float:
    rule = MODE_RULES[mode]
    return max(rule["min_headroom_gb"], rule["min_headroom_pct"] * (total_gb() if total is None else total))


def admit(spec, stage: str = "load", qstate: dict[str, Any] | None = None, available: float | None = None,
          others: list[dict[str, Any]] | None = None, mode: str = EVALUATION_MODE,
          capacity: float | None = None, total: float | None = None, recovery_ok: bool = True) -> Admission:
    """ADMIT / DEFER / RESOURCE_BLOCKED for `stage` of `spec` under `mode`, with the reason."""
    prof = profile_for(stage)
    peak, src = expected_peak(spec, qstate)
    if not prof.model_resident:
        peak, src = 0.0, "no model resident in this stage"
    res = prof.reserves()
    avail = available_gb() if available is None else available
    if others is None:
        others = llama_servers()
    others = [o for o in others if str(o.get("port")) != str(spec.port) and o.get("rss_gb", 0) >= UNLOADED_RSS_LIMIT_GB]
    need = peak + sum(res.values())
    req = required_headroom(mode, total)
    headroom = avail - need
    cap = baseline_capacity_gb() if capacity is None else capacity
    fits_idle = cap - need >= req
    if others or not recovery_ok:
        why = (f"another model server is resident ({others}); never two large models at once" if others
               else "memory has not recovered from the previous model (MEMORY_LEAK_OR_RESIDUAL)")
        dec = Decision.DEFER if fits_idle else Decision.RESOURCE_BLOCKED
    elif headroom >= req:
        dec, why = Decision.ADMIT, (f"{mode}: need {need:.1f} GB (peak {peak:.1f} + reserves {sum(res.values()):.2f}); "
                                    f"headroom {headroom:.1f} GB >= required {req:.1f} GB")
    elif fits_idle:
        dec, why = Decision.DEFER, (f"{mode}: headroom {headroom:.1f} GB < required {req:.1f} GB now, but the stage "
                                    f"fits an idle machine ({cap:.1f} GB) — wait for memory to free")
    else:
        dec, why = Decision.RESOURCE_BLOCKED, (
            f"{mode}: need {need:.1f} GB (peak {peak:.1f} + reserves {sum(res.values()):.2f}) leaves "
            f"{cap - need:.1f} GB of the machine's {cap:.1f} GB < required headroom {req:.1f} GB")
    return Admission(spec.key, stage, peak, src, round(avail, 2), round(sum(res.values()), 2), res,
                     dec == Decision.ADMIT, why, others, dec.value, mode, prof.name, round(headroom, 2), round(req, 2))


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


class _Sampler(threading.Thread):
    """Background sampler while a model is loaded: min MemAvailable, peak swap, server major faults."""

    def __init__(self, pid_fn, interval: float = 2.0):
        super().__init__(daemon=True)
        self.pid_fn, self.interval = pid_fn, interval
        self.stop_evt = threading.Event()
        self.min_available = float("inf")
        self.swap_peak = swap_used_gb()
        self.major_faults = 0

    def run(self) -> None:
        while not self.stop_evt.is_set():
            self.min_available = min(self.min_available, available_gb())
            self.swap_peak = max(self.swap_peak, swap_used_gb())
            pid = self.pid_fn()
            mem = proc_rss_gb(pid) if pid else None
            if mem and "major_faults" in mem:
                self.major_faults = mem["major_faults"]
            self.stop_evt.wait(self.interval)


class ScheduledServer:
    """Load -> (stages) -> unload with admission, a measured memory lifecycle and the unload assertion.

    Lifecycle record: available/used before load, after load (process healthy), after warm-up, peak (VmHWM and
    min MemAvailable), before unload, after process exit, after the stabilisation delay; memory_recovery_ratio =
    available after stabilisation / available before load; swap total / before / peak; major page faults;
    warm-up latency at load vs a probe after the last stage (latency degradation)."""

    def __init__(self, server, *, qstate: dict[str, Any] | None = None, log_path: Path | None = None,
                 mode: str = EVALUATION_MODE):
        self.server, self.qstate, self.log_path, self.mode = server, qstate, log_path, mode
        self.metrics: dict[str, Any] = {}
        self.flags: list[str] = []
        self._sampler: _Sampler | None = None

    def _pid(self) -> int | None:
        try:
            return int(self.server.pidfile.read_text())
        except (OSError, ValueError):
            return None

    def load(self, stage: str = "load", wait_s: float = 1200.0, recovery_ok: bool = True) -> Admission:
        # never two large models at once: another resident server makes admission DEFER/BLOCK. The scheduler never
        # kills a process it did not start — its owner (e.g. the queue) stops its own servers.
        squatter = [s for s in llama_servers() if str(s["port"]) == str(self.server.spec.port)]
        dec = admit(self.server.spec, stage, self.qstate, mode=self.mode, recovery_ok=recovery_ok,
                    others=[{**s, "port": f"{s['port']} (not started by this scheduler)"} for s in squatter] or None)
        if squatter and dec.decision == Decision.ADMIT:   # a server we did not start already holds our port
            dec.decision, dec.admitted = Decision.DEFER.value, False
            dec.reason = f"port {self.server.spec.port} is held by a server this scheduler did not start: {squatter}"
        if self.log_path:
            record(self.log_path, {"event": "admission", **dec.as_dict()})
        if dec.decision != Decision.ADMIT:
            raise ResourceBlocked(dec)
        m = meminfo()
        self.metrics.update({"mode": self.mode, "available_before_load_gb": round(m.get("MemAvailable", 0), 2),
                             "rss_before_load_gb": round(used_gb(), 2), "swap_total_gb": round(m.get("SwapTotal", 0), 2),
                             "swap_used_before_gb": round(swap_used_gb(), 2), "estimated_peak_gb": dec.expected_peak_gb,
                             "estimate_source": dec.estimate_source, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        t0 = time.monotonic()
        self.server.start(wait_s=wait_s)
        self.metrics["load_time_s"] = round(time.monotonic() - t0, 1)
        self.metrics["available_after_load_gb"] = round(available_gb(), 2)
        t1 = time.monotonic()
        warmed = self.server.warm_up()
        self.metrics["warmup_time_s"] = round(time.monotonic() - t1, 2)
        self.metrics["available_after_warmup_gb"] = round(available_gb(), 2)
        pid = self._pid()
        mem = proc_rss_gb(pid) if pid else None
        if mem and warmed:
            self.metrics["rss_after_warmup_gb"] = mem["rss_gb"]
            self.metrics["anon_after_warmup_gb"] = mem["anon_gb"]
        self._sampler = _Sampler(self._pid)
        self._sampler.start()
        return dec

    def admit_stage(self, stage: str) -> Admission:
        """While loaded: does this stage fit? The server's own anonymous memory is added back to MemAvailable (its
        file pages are already counted there), so the test is the same as before a load."""
        pid = self._pid()
        mem = proc_rss_gb(pid) if pid else None
        dec = admit(self.server.spec, stage, self.qstate, mode=self.mode,
                    available=available_gb() + (mem["anon_gb"] if mem else 0.0), others=[])
        if self.log_path:
            record(self.log_path, {"event": "stage_admission", **dec.as_dict()})
        return dec

    def sample_peak(self) -> float | None:
        pid = self._pid()
        mem = proc_rss_gb(pid) if pid else None
        if mem:
            self.metrics["peak_rss_gb"] = max(self.metrics.get("peak_rss_gb", 0.0), mem["peak_rss_gb"])
        return self.metrics.get("peak_rss_gb")

    def unload(self) -> dict[str, Any]:
        self.sample_peak()
        self.metrics["available_before_unload_gb"] = round(available_gb(), 2)
        if self.metrics.get("warmup_time_s") is not None and self._pid():
            t0 = time.monotonic()
            if self.server.warm_up():         # the same tiny request as the warm-up: latency degradation probe
                lat = round(time.monotonic() - t0, 2)
                self.metrics["latency_probe_after_s"] = lat
                self.metrics["latency_degradation_ratio"] = round(lat / max(self.metrics["warmup_time_s"], 0.01), 2)
        if self._sampler:
            self._sampler.stop_evt.set()
            self._sampler.join(timeout=5)
            self.metrics.update({"min_available_while_loaded_gb": round(self._sampler.min_available, 2)
                                 if self._sampler.min_available != float("inf") else None,
                                 "swap_used_peak_gb": round(self._sampler.swap_peak, 2),
                                 "server_major_faults": self._sampler.major_faults})
        t0 = time.monotonic()
        self.server.stop()
        for _ in range(60):                       # confirm the process is gone
            if not any(str(s["port"]) == str(self.server.spec.port) for s in llama_servers()):
                break
            time.sleep(0.5)
        self.metrics["available_after_exit_gb"] = round(available_gb(), 2)
        settled = wait_stable()
        before = self.metrics.get("available_before_load_gb") or 0.0
        ratio = round(settled / before, 3) if before else None
        self.metrics.update({"unload_time_s": round(time.monotonic() - t0, 1), "rss_after_unload_gb": round(used_gb(), 2),
                             "available_after_unload_gb": round(settled, 2), "memory_recovery_ratio": ratio,
                             "swap_used_after_gb": round(swap_used_gb(), 2)})
        if ratio is not None and ratio < RECOVERY_MIN_RATIO:
            self.flags.append("MEMORY_LEAK_OR_RESIDUAL")
        if (self.metrics.get("swap_used_peak_gb", 0) - self.metrics.get("swap_used_before_gb", 0) > DEGRADED_SWAP_GB
                or (self.metrics.get("latency_degradation_ratio") or 0) > DEGRADED_LATENCY_RATIO):
            self.flags.append("RESOURCE_DEGRADED")
        self.metrics["flags"] = self.flags
        if self.metrics.get("peak_rss_gb"):
            self.metrics["estimate_record"] = record_estimate(self.server.spec, self.metrics["peak_rss_gb"])
        if self.log_path:
            record(self.log_path, {"event": "unload", "model": self.server.spec.key, **self.metrics})
        assert_unloaded(self.server.spec.port)
        return self.metrics


def last_recovery_ok(qstate: dict[str, Any] | None) -> tuple[bool, str]:
    """The most recent unload of any model must have recovered memory before another large model may load."""
    cyc = sorted((c for v in (qstate or {}).get("done", {}).values() if isinstance(v, dict)
                  and isinstance(v.get("info"), dict) for c in (v["info"].get("cycles") or [])),
                 key=lambda c: c.get("at", ""))
    if not cyc:
        return True, "no previous cycle"
    last = cyc[-1]
    if "MEMORY_LEAK_OR_RESIDUAL" in (last.get("flags") or []):
        if available_gb() >= RECOVERY_MIN_RATIO * (last.get("available_before_load_gb") or 0):
            return True, "recovered since the last unload"
        return False, f"last unload recovered only {last.get('memory_recovery_ratio')}"
    return True, f"last recovery ratio {last.get('memory_recovery_ratio')}"
