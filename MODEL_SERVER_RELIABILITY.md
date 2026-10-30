# Model server reliability

_Generated 2026-10-30 21:39 UTC by `apex-one reports` at commit `11d21c6` from measured artifacts._

A local model server can crash, hang, run out of memory, return nothing or return garbage. None of these is a wrong answer. `apex_one/compute/local/supervisor.py` classifies every failed call into exactly one failure kind, recovers the server when that is safe, and the benchmark records the sample as **ERROR** (never a score). Result states are kept separate: PASSED · FAILED (measured) · UNSUPPORTED · SKIPPED · ERROR.

## Why this exists

On 2026-10-30 the Qwen3-VL 8B llama-server died in the middle of a GraphicDesignBench run. The harness of that time turned the resulting empty answers into 0 scores (12/12 samples "ok"). That run is quarantined (`artifacts/bench/gdb/_invalid_qwen3-vl-8b-q4kxl-full_20261030`), the valid re-run replaced it, and the supervision below makes the same failure an ERROR with a kind.

## Supervision policy

* pre-call health probe (`/health`, 3 s) before every model call
* timeout detection: the call timeout raises MODEL_TIMEOUT; a hung server is restarted (it holds the only slot)
* restart: at most 3 per server per run, backoff 2 s, 8 s, 30 s; each restart must pass `/health` AND a 1-token warm-up completion
* restart on: HEALTHCHECK_FAILED, MODEL_SERVER_CRASH, MODEL_TIMEOUT, OOM
* the SAME request is retried once, only after a verified recovery, only for: CONNECTION_DROPPED, MODEL_SERVER_CRASH, MODEL_TIMEOUT, OOM — a chat completion is side-effect free; pipeline stages and jobs are never re-run by the supervisor, so no side effect can be duplicated
* EMPTY_OUTPUT and MALFORMED_RESPONSE are never retried (at temperature 0 they would only repeat)
* every incident is a JSON line: `artifacts/bench/server_reliability/events.jsonl` (benchmarks), `artifacts/logs/model_server_events.jsonl` (production)
* production brokers supervise only servers that are already running; supervision recovers a crash, it never starts a model nobody asked for

## Failure kinds

| kind | detected from |
|---|---|
| MODEL_SERVER_CRASH | process no longer alive after the failed call (any transport symptom) |
| OOM | process dead by SIGKILL, or an allocator failure in the server log |
| MODEL_TIMEOUT | no response within the call timeout, process alive |
| EMPTY_OUTPUT | HTTP 200, valid shape, empty / whitespace content |
| MALFORMED_RESPONSE | body is not an OpenAI chat response |
| CONNECTION_DROPPED | connection closed mid-response, process alive |
| HEALTHCHECK_FAILED | `/health` not OK and the restart budget is spent |
| UNKNOWN_FAILURE | anything else (e.g. HTTP 500) |

## Fault-injection drill (fake model server, real broker + council path)

Result: **ALL PASS** — 12/12 modes classified as expected.

| fake server mode | sample state | failure kind | in score table | restarts | supervisor events | expected | pass |
|---|---|---|---|---|---|---|---|
| ok | FAILED | — | yes | 0 | — | MEASURED/— | PASS |
| empty | ERROR | EMPTY_OUTPUT | no | 0 | call_failed:EMPTY_OUTPUT | ERROR/EMPTY_OUTPUT | PASS |
| hang | ERROR | MODEL_TIMEOUT | no | 2 | call_failed:MODEL_TIMEOUT, restart, warmup_failed, restart, warmup_failed, restart_budget_exhausted | ERROR/MODEL_TIMEOUT | PASS |
| crash | ERROR | MODEL_SERVER_CRASH | no | 2 | call_failed:MODEL_SERVER_CRASH, restart, warmup_failed, restart, warmup_failed, restart_budget_exhausted | ERROR/MODEL_SERVER_CRASH | PASS |
| oom | ERROR | OOM | no | 2 | call_failed:OOM, restart, warmup_failed, restart, warmup_failed, restart_budget_exhausted | ERROR/OOM | PASS |
| malformed | ERROR | MALFORMED_RESPONSE | no | 0 | call_failed:MALFORMED_RESPONSE | ERROR/MALFORMED_RESPONSE | PASS |
| disconnect | ERROR | CONNECTION_DROPPED | no | 0 | call_failed:CONNECTION_DROPPED, call_failed:CONNECTION_DROPPED | ERROR/CONNECTION_DROPPED | PASS |
| unhealthy | ERROR | HEALTHCHECK_FAILED | no | 2 | unhealthy_before_call:HEALTHCHECK_FAILED, restart, start_failed, restart, start_failed, restart_budget_exhausted | ERROR/HEALTHCHECK_FAILED | PASS |
| crash_once | FAILED | — | yes | 1 | call_failed:MODEL_SERVER_CRASH, restart, recovered | MEASURED/— | PASS |
| hang_once | FAILED | — | yes | 1 | call_failed:MODEL_TIMEOUT, restart, recovered | MEASURED/— | PASS |
| oom_once | FAILED | — | yes | 1 | call_failed:OOM, restart, recovered | MEASURED/— | PASS |
| disconnect_once | FAILED | — | yes | 0 | call_failed:CONNECTION_DROPPED | MEASURED/— | PASS |

`ok` and the `*_once` modes are real measurements of the fake server's fixed answer (the checker scores it FAILED because the fake answer is not the task's answer) — the point is that they were MEASURED after recovery, while every persistent fault is ERROR and never enters the score table.

## Incidents in real benchmark runs (since supervision)

none recorded

Regression tests: `tests/test_server_reliability.py` (classification, bounded restart with backoff, the full drill, GDB failures carry their kind).

