"""Manage local llama.cpp `llama-server` processes (OpenAI-compatible, incl. vision via --mmproj)."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import httpx

from apex_one.compute.local.acquisition import LocalModelSpec, load_catalogue
from apex_one.settings import get_settings


def server_binary() -> Path:
    runtime, _ = load_catalogue()
    p = Path(runtime["server_binary"])
    return p if p.is_absolute() else get_settings().home / p


class LocalServer:
    def __init__(self, spec: LocalModelSpec, threads: int | None = None):
        self.spec = spec
        self.threads = threads or max(1, (os.cpu_count() or 2))
        self.pidfile = spec.dir / "server.pid"
        self.logfile = spec.dir / "server.log"
        self.proc: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.spec.port}/v1"

    def model_files(self) -> tuple[Path, Path | None]:
        ggufs = sorted(self.spec.dir.glob("*.gguf"))
        mm = next((p for p in ggufs if "mmproj" in p.name.lower()), None)
        mmproj_alt = next(iter(self.spec.dir.glob("*.mmproj")), None)
        main = [p for p in ggufs if p is not mm]
        if not main:
            raise FileNotFoundError(f"{self.spec.key}: no GGUF weights in {self.spec.dir}; run `apex-one local acquire {self.spec.key}`")
        return main[0], mm or mmproj_alt

    def healthy(self, timeout: float = 2.0) -> bool:
        try:
            return httpx.get(f"http://127.0.0.1:{self.spec.port}/health", timeout=timeout).status_code == 200
        except httpx.HTTPError:
            return False

    def start(self, wait_s: float = 600.0) -> str:
        if self.healthy():
            return self.base_url
        binary = server_binary()
        if not binary.exists():
            raise FileNotFoundError(f"llama-server not built at {binary}")
        model, mmproj = self.model_files()
        cmd = [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.spec.port),
               "-c", str(self.spec.ctx), "-t", str(self.threads), "--jinja", "--alias", self.spec.key, "--no-webui",
               # one sequential client: a single slot and a small prompt cache keep RAM for the next model
               "-np", "1", "--cache-ram", "512"]
        if mmproj is not None and self.spec.vision:
            cmd += ["--mmproj", str(mmproj)]
        log = self.logfile.open("ab")
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.proc = proc
        self.pidfile.write_text(str(proc.pid))
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if proc.poll() is not None:
                raise RuntimeError(f"llama-server exited ({proc.returncode}); see {self.logfile}")
            if self.healthy():
                return self.base_url
            time.sleep(1.0)
        raise TimeoutError(f"{self.spec.key} did not become healthy in {wait_s}s")

    # ---- supervision (apex_one/compute/local/supervisor.py) ----
    def alive(self) -> bool | None:
        """True / False when known; None when this object did not start the process and has no pid."""
        if self.proc is not None:
            return self.proc.poll() is None
        if not self.pidfile.exists():
            return None
        try:
            os.kill(int(self.pidfile.read_text()), 0)
            return True
        except (ProcessLookupError, ValueError):
            return False
        except PermissionError:
            return True

    def exit_code(self) -> int | None:
        return self.proc.poll() if self.proc is not None else None

    def log_tail(self, chars: int = 2000) -> str:
        if not self.logfile.exists():
            return ""
        with self.logfile.open("rb") as fh:
            fh.seek(max(0, self.logfile.stat().st_size - chars))
            return fh.read().decode("utf-8", "replace")

    def warm_up(self, timeout: float = 120.0) -> bool:
        """One tiny completion: the model is loaded and answering (not just the HTTP listener)."""
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", timeout=timeout,
                           json={"model": self.spec.key, "max_tokens": 1, "temperature": 0,
                                 "messages": [{"role": "user", "content": "ok"}]})
            return r.status_code == 200 and "choices" in r.json()
        except (httpx.HTTPError, ValueError):
            return False

    def stop(self) -> None:
        if self.pidfile.exists():
            try:
                os.killpg(int(self.pidfile.read_text()), signal.SIGTERM)
            except (ProcessLookupError, ValueError, PermissionError):
                pass
            self.pidfile.unlink(missing_ok=True)
        if self.proc is not None:
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.proc = None
