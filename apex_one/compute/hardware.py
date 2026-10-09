"""Hardware-aware execution: detect the machine and plan (never auto-run) model acquisition."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from apex_one.compute.registry.loader import ArsenalRegistry


@dataclass
class HardwareProfile:
    os: str
    os_version: str
    machine: str
    cpu: str
    cpu_count: int
    apple_silicon: bool
    ram_gb: float | None
    gpus: list[str] = field(default_factory=list)
    free_disk_gb: float | None = None
    docker: bool = False
    ollama_binary: bool = False
    llama_cpp_binary: bool = False
    mlx_installed: bool = False
    chromium: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _ram_gb() -> float | None:
    try:
        if Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3)
            return round(int(out.stdout.strip()) / 1024**3, 1)
    except Exception:
        return None
    return None


def _cpu_name() -> str:
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=3)
            return out.stdout.strip() or platform.processor()
        if Path("/proc/cpuinfo").exists():
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def _gpus() -> list[str]:
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=5)
            return [x.strip() for x in out.stdout.splitlines() if x.strip()]
        except Exception:
            return []
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return ["Apple Silicon integrated GPU (unified memory)"]
    return []


def find_chromium() -> str | None:
    env = os.environ.get("APEX_CHROMIUM_PATH")
    if env and Path(env).exists():
        return env
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-linux64/chrome",
                    "chromium_headless_shell-*/chrome-*/chrome-headless-shell",
                    "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
        hits = sorted(base.glob(pattern), reverse=True) if base.exists() else []
        if hits:
            return str(hits[0])
    return None


def detect_hardware(home: Path | None = None) -> HardwareProfile:
    disk = None
    try:
        disk = round(shutil.disk_usage(home or Path.cwd()).free / 1024**3, 1)
    except Exception:
        pass
    return HardwareProfile(
        os=platform.system(), os_version=platform.release(), machine=platform.machine(), cpu=_cpu_name(),
        cpu_count=os.cpu_count() or 1,
        apple_silicon=platform.system() == "Darwin" and platform.machine() == "arm64",
        ram_gb=_ram_gb(), gpus=_gpus(), free_disk_gb=disk, docker=shutil.which("docker") is not None,
        ollama_binary=shutil.which("ollama") is not None,
        llama_cpp_binary=any(shutil.which(b) for b in ("llama-server", "llama-cli")),
        mlx_installed=importlib.util.find_spec("mlx") is not None, chromium=find_chromium(),
    )


@dataclass
class AcquisitionAdvice:
    model_id: str
    verdict: str          # RECOMMENDED | POSSIBLE | TOO_LARGE | REMOTE_ONLY | LICENSE_BLOCKED_FOR_PRODUCTION | NOT_LOCAL
    reason: str
    command: str = ""
    download_gb: float | None = None


def plan_acquisition(registry: ArsenalRegistry, hw: HardwareProfile) -> list[AcquisitionAdvice]:
    """Recommend which local models are realistically runnable. NEVER downloads anything."""
    advice: list[AcquisitionAdvice] = []
    ram = hw.ram_gb or 0.0
    disk = hw.free_disk_gb or 0.0
    for m in registry.models.values():
        if m.family in ("apex-native", "mock", "future"):
            continue
        local_routes = [r for r in m.routes if registry.providers[r.provider].kind == "local"]
        if not local_routes:
            advice.append(AcquisitionAdvice(m.id, "REMOTE_ONLY" if m.routes else "NOT_LOCAL",
                                            "no local route registered" if m.routes else "no route registered yet"))
            continue
        need = m.min_ram_gb or 0
        size = m.weights_size_gb
        prod = registry.production_allowed(m.id)
        if need and need > ram * 0.8:
            advice.append(AcquisitionAdvice(m.id, "TOO_LARGE", f"needs ~{need} GB memory; machine has {ram} GB",
                                            download_gb=size))
            continue
        if size and size > disk * 0.8:
            advice.append(AcquisitionAdvice(m.id, "TOO_LARGE", f"~{size} GB download; {disk} GB free", download_gb=size))
            continue
        verdict = "RECOMMENDED" if prod else "POSSIBLE"
        reason = "fits memory/disk" + ("" if prod else "; licence not yet verified for production (research use only)")
        if m.id == "aya-expanse-32b":
            verdict, reason = "LICENSE_BLOCKED_FOR_PRODUCTION", "non-commercial licence (reported): ONE Lab only"
        advice.append(AcquisitionAdvice(m.id, verdict, reason, m.local_hint, size))
    order = {"RECOMMENDED": 0, "POSSIBLE": 1, "LICENSE_BLOCKED_FOR_PRODUCTION": 2, "TOO_LARGE": 3,
             "REMOTE_ONLY": 4, "NOT_LOCAL": 5}
    return sorted(advice, key=lambda a: (order.get(a.verdict, 9), a.model_id))
