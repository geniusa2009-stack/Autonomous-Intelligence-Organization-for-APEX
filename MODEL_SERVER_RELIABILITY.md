# Model server reliability

_Generated 2026-10-31 02:19 UTC by `apex-one reports` at commit `bdc6bce` from measured artifacts._

A local model server can crash, hang, run out of memory, return nothing or return garbage. None of these is a wrong answer. `apex_one/compute/local/supervisor.py` classifies every failed call into exactly one failure kind, recovers the server when that is safe, and the benchmark records the sample as **ERROR** (never a score). Result states are kept separate: PASSED · FAILED (measured) · UNSUPPORTED · SKIPPED · ERROR.

## Why this exists

On 2026-10-30 the Qwen3-VL 8B llama-server died in the middle of a GraphicDesignBench run. The harness of that time turned the resulting empty answers into 0 scores (12/12 samples "ok"). That run is quarantined (`artifacts/bench/gdb/_invalid_qwen3-vl-8b-q4kxl-full_20261030`), the valid re-run replaced it, and the supervision below makes the same failure an ERROR with a kind.

## Supervision policy

* pre-call health probe (`/health`, 3 s) before every model call
* timeout detection: the call timeout raises MODEL_TIMEOUT; a hung server is restarted (it holds the only slot)
* restart: at most 3 per server per run, backoff 2 s, 8 s, 30 s; each restart must pass `/health` AND a 1-token warm-up completion
* restart on: CONNECTION_REFUSED, HEALTHCHECK_FAILED, MODEL_SERVER_CRASH, MODEL_TIMEOUT, OOM
* the SAME request is retried once, only after a verified recovery, only for: CONNECTION_REFUSED, MODEL_SERVER_CRASH, MODEL_TIMEOUT, OOM, STREAM_INTERRUPTED — a chat completion is side-effect free; pipeline stages and jobs are never re-run by the supervisor, so no side effect can be duplicated
* EMPTY_OUTPUT and MALFORMED_OUTPUT are never retried (at temperature 0 they would only repeat); RESOURCE_BLOCKED is never retried (waiting does not create RAM)
* every incident is a JSON line: `artifacts/bench/server_reliability/events.jsonl` (benchmarks), `artifacts/logs/model_server_events.jsonl` (production)
* production brokers supervise only servers that are already running; supervision recovers a crash, it never starts a model nobody asked for

## Failure kinds (infrastructure — never a quality score)

| kind | detected from |
|---|---|
| MODEL_SERVER_CRASH | process no longer alive after the failed call (any transport symptom) |
| OOM | process dead by SIGKILL, or an allocator failure in the server log |
| MODEL_TIMEOUT | no response within the call timeout, process alive |
| EMPTY_OUTPUT | HTTP 200, valid shape, empty / whitespace content |
| MALFORMED_OUTPUT | the response body is not an OpenAI chat response (a well-formed answer with wrong content is QUALITY, scored by the checker) |
| CONNECTION_REFUSED | nothing listening on the port and restarts did not bring it up |
| STREAM_INTERRUPTED | connection closed mid-response, process alive |
| HEALTHCHECK_FAILED | process running but `/health` not OK and the restart budget is spent |
| RESOURCE_BLOCKED | the resource scheduler refused the load (expected peak + reserves > available) |
| UNKNOWN_FAILURE | anything else (e.g. HTTP 500) |

## Outcome classes (persisted separately on every council sample, never collapsed)

| class | meaning | example |
|---|---|---|
| MEASURED | the model answered; the checker scored it > 0 | Qwen3-VL 8B English writing = 100 |
| QUALITY_ZERO | the model answered; the answer is wrong (score 0) | Qwen3-VL 8B Egyptian Arabic = 0 |
| INFRASTRUCTURE_ERROR | a failure kind above: there was no answer to judge | server crash mid-GDB |
| NOT_MEASURED | unsupported, skipped or never run | GDB image-generation tasks |

## Resource scheduler

Before a model loads: expected peak (measured, else weights + KV + compute) + reserves must fit in MemAvailable, or the load is refused with RESOURCE_BLOCKED. While loaded, each stage is admitted again (a stage that starts Chromium needs 0.8 GB more). After every model: stop the server, confirm the process exited, wait until MemAvailable is stable, assert no llama-server still holds ≥ 1 GB (a model marked finished while its server holds memory is a scheduler bug and stops the queue), and only then load the next model. The scheduler never kills a process it did not start. Full matrix: LOCAL_MODEL_RESOURCE_MATRIX.md.

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

Every row also carries its outcome class: persistent faults are INFRASTRUCTURE_ERROR. `ok` and the `*_once` modes are real measurements of the fake server's fixed answer (the checker scores it FAILED because the fake answer is not the task's answer) — the point is that they were MEASURED after recovery, while every persistent fault is ERROR and never enters the score table.

## Incidents in real benchmark runs (since supervision)

No supervisor event (restart, crash, timeout, empty output) was recorded in a real run.

**Queue / scheduler incidents** (before a server was under supervision):

| at | server | what happened | outcome | fix | regression tests |
|---|---|---|---|---|---|
| 2026-10-31T01:04:30 | qwen3-vl-4b-q4kxl (port 8093) | a second validation-queue process (snapshot d28e25e) started while the first (b61868b) was loading the same model on the same port; the second llama-server exited (1) on the busy port and its unload assertion found a 1.47 GB server it had not started | SchedulerViolation raised (fail-closed); no OOM, no swap, no process killed; the first queue finished normally | bdc6bce: exclusive queue lock (a second queue exits with code 3) + a server we did not start on our port DEFERs the load | `tests/test_server_reliability.py::test_only_one_queue_process_may_run, ::test_a_server_on_our_port_that_we_did_not_start_defers_the_load` |

## Memory lifecycle per load / unload cycle (resource scheduler)

Available memory (GB) at each point; recovery = available after stabilisation / available before load (< 0.95 → MEMORY_LEAK_OR_RESIDUAL, and no next large model loads).

| model | mode | before load | after load | after warm-up | min while loaded | before unload | after exit | after stabilisation | recovery | server peak RSS | swap before / peak | major faults | load / warm-up / unload | latency degradation | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 3 4B | EVALUATION_MODE | 15.7 | 12.27 | 12.27 | 12.23 | 12.23 | 15.96 | 15.99 | 1.018 | 6.35 | 0.0 / 0.0 | 0 | 254.6 / 0.58 / 2.4 s | 0.6 | — |
| Gemma 3 12B | pre-scheduler record (partial) | 16.14 | — | — | — | — | — | 16.09 | — | 14.08 | — / — | — | 14.0 / — / 2.6 s | — | — |
| Qwen3-VL 4B | pre-scheduler record (partial) | 15.68 | — | — | — | — | — | 16.08 | — | — | — / — | — | 251.2 / — / 33.0 s | — | — |
| Qwen3-VL 4B | EVALUATION_MODE | 15.78 | 11.34 | 11.34 | 11.3 | 11.3 | 16.01 | 16.03 | 1.016 | 7.32 | 0.0 / 0.0 | 0 | 5.4 / 0.33 / 2.3 s | 0.7 | — |
| Qwen3-VL 8B | EVALUATION_MODE | 15.6 | 8.5 | 8.51 | 7.86 | 8.21 | 15.43 | 15.45 | 0.99 | 12.51 | 0.0 / 0.0 | 98 | 254.1 / 0.53 / 2.4 s | 1.45 | — |
| Nemotron 3 Nano 4B | EVALUATION_MODE | 15.66 | 14.38 | 14.2 | 13.55 | 13.63 | 15.85 | 15.86 | 1.013 | 4.9 | 0.0 / 0.0 | 12 | 209.4 / 0.96 / 2.3 s | 0.97 | — |

**RESOURCE_BLOCKED decisions** (a refusal is recorded, never an OOM):

* `qwen3-vl-8b-q8kxl` (9 steps: acquire, live, pcalib, robust:640, robust:native, robust:320, robust:480, robust:768, robust:1024) — RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leaves -5.9 GB of the machine's 16.1 GB < required headroom 0.5 GB (estimate 13.6 GB (weights 12.0 + KV 1.0 + compute 0.6 GB) x 1.54 (same-family measured ratio (qwen3-vl)))
* `gpt-oss-20b-mxfp4` (3 steps: acquire, vector, rerun_vector) — RESOURCE_BLOCKED: EVALUATION_MODE: need 22.2 GB (peak 21.1 + reserves 1.10) leaves -6.1 GB of the machine's 16.1 GB < required headroom 0.5 GB (estimate 13.7 GB (weights 12.1 + KV 1.0 + compute 0.6 GB) x 1.54 (conservative default (no measured sibling)))


Regression tests: `tests/test_server_reliability.py` (classification, bounded restart with backoff, the full drill, GDB failures carry their kind).

