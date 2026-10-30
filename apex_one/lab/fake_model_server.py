"""Deliberately faulty OpenAI-compatible model server for fault-injection drills.

Run: python -m apex_one.lab.fake_model_server --port 8199 --mode <mode> [--state-file f]

Modes for POST /v1/chat/completions:
  ok          valid completion
  empty       valid shape, empty content
  hang        never answers
  crash       the process exits while handling the request
  oom         writes an allocator failure to the log, then dies by SIGKILL (what the kernel OOM killer does)
  malformed   HTTP 200 with a body that is not JSON
  disconnect  promises a body (Content-Length) then closes the connection mid-response; the process stays alive
  unhealthy   /health answers 503 (the process runs but never becomes ready)
  <mode>_once  fault on the first request only (tracked in --state-file, so it survives a restart), then ok
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OK_TEXT = '{"answer": "ok"}'


def _completion(text: str) -> bytes:
    return json.dumps({"id": "fake", "model": "fake", "choices": [{"index": 0, "finish_reason": "stop",
                                                                   "message": {"role": "assistant", "content": text}}],
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()


def make_handler(mode: str, state_file: Path | None):
    def effective_mode() -> str:
        if not mode.endswith("_once"):
            return mode
        if state_file is not None and state_file.exists():
            return "ok"
        if state_file is not None:
            state_file.write_text("faulted")
        return mode.removesuffix("_once")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path.startswith("/health"):
                if mode == "unhealthy":
                    self._send(503, b'{"status":"loading"}')
                else:
                    self._send(200, b'{"status":"ok"}')
            elif self.path.startswith("/v1/models"):
                self._send(200, b'{"data":[{"id":"fake"}]}')
            else:
                self._send(404, b"{}")

        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            m = effective_mode()
            if m == "hang":
                time.sleep(3600)
            elif m == "crash":
                print("fatal: segmentation fault in decode", flush=True)
                os._exit(1)
            elif m == "oom":
                print("ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer: out of memory", flush=True)
                os.kill(os.getpid(), signal.SIGKILL)
            elif m == "malformed":
                self._send(200, b"{this is not json")
            elif m == "disconnect":
                body = _completion(OK_TEXT)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body) + 500))
                self.end_headers()
                self.wfile.write(body[:20])
                self.wfile.flush()
                self.close_connection = True
                self.connection.shutdown(2)
            elif m == "empty":
                self._send(200, _completion(""))
            else:
                self._send(200, _completion(OK_TEXT))

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--mode", default="ok")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.mode, Path(a.state_file) if a.state_file else None))
    srv.daemon_threads = True
    srv.serve_forever()


class FakeServerProcess:
    """SupervisedProcess implementation (compute/local/supervisor.py) around the fake server."""

    def __init__(self, port: int, mode: str, workdir: Path):
        self.port, self.mode, self.workdir = port, mode, workdir
        self.logfile = workdir / f"fake-{port}.log"
        self.state_file = workdir / f"fake-{port}.state"
        self.proc: subprocess.Popen | None = None
        self.starts = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self, wait_s: float = 10.0) -> str:
        import httpx

        self.starts += 1
        log = self.logfile.open("ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "apex_one.lab.fake_model_server", "--port", str(self.port),
                                      "--mode", self.mode, "--state-file", str(self.state_file)],
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.proc.poll() is not None:
                raise RuntimeError(f"fake server exited ({self.proc.returncode})")
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=1).status_code == 200:
                    return self.base_url
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise TimeoutError(f"fake server ({self.mode}) not healthy in {wait_s}s")

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)

    def healthy(self, timeout: float = 2.0) -> bool:
        import httpx

        try:
            return httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=timeout).status_code == 200
        except httpx.HTTPError:
            return False

    def alive(self) -> bool | None:
        return None if self.proc is None else self.proc.poll() is None

    def exit_code(self) -> int | None:
        return None if self.proc is None else self.proc.poll()

    def log_tail(self, chars: int = 2000) -> str:
        return self.logfile.read_text(errors="replace")[-chars:] if self.logfile.exists() else ""

    def warm_up(self, timeout: float = 5.0) -> bool:
        import httpx

        try:
            r = httpx.post(f"{self.base_url}/chat/completions", timeout=timeout,
                           json={"model": "fake", "max_tokens": 1, "messages": [{"role": "user", "content": "ok"}]})
            return r.status_code == 200 and "choices" in r.json()
        except (httpx.HTTPError, ValueError):
            return False


if __name__ == "__main__":
    main()
