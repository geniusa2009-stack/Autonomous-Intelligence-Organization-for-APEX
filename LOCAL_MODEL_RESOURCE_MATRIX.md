# Local model resource matrix

_Generated 2026-10-30 23:39 UTC by `apex-one reports` at commit `2e7ded4` from measured artifacts._

Machine: 16.9 GB RAM, no swap, 4 CPU threads, no GPU. Memory available with no model loaded: **16.0 GB** (ESTIMATE 95% of MemTotal — no load recorded under the scheduler yet). On this machine compute scheduling is part of correctness: the resource scheduler (`apex_one/compute/local/resources.py`) refuses a load with RESOURCE_BLOCKED when `expected_peak + reserves > available`, never runs two large models at once, and asserts after every unload that the server process is gone and its memory has returned.

Reserves (headroom beside the model, GB): os_headroom 0.3, python_worker_growth 0.3, evaluation_artifacts 0.2, model_server_overhead 0.25, safety margin 0.3; + renderer 0.8 for stages that start Chromium (model-written pages, golden runs). Expected peak = the MEASURED peak RSS of the artifact when it has run before, else weights + KV cache (from GGUF metadata, configured context) + 0.6 GB compute.

| model | quantization | disk GB | loaded RAM GB | peak RAM GB | load time | unload time | median inference latency | vision capability | text capability (≥ floor) | production status | recommended role | safe concurrent services |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 3 4B | 4b-q4_K_M | 3.3 | NOT_MEASURED | NOT_MEASURED | — | — | 11 s | abs 1/5, pair 0/5 → **UNQUALIFIED** | strong: structured_json, egyptian_arabic, fact_preservation, html_css, long_context, design_criticism; weak: date_reasoning | DECLARED_BUT_UNVERIFIED | research / evaluation only (licence DECLARED_BUT_UNVERIFIED) | NOT_MEASURED (no recorded peak) |
| Gemma 3 12B | 12b-q4_K_M | 8.2 | 13.61 | 13.86 | — | — | NOT_MEASURED | abs 1/5, pair 0/5 → **UNQUALIFIED** | strong: —; weak: — | DECLARED_BUT_UNVERIFIED | research / evaluation only (licence DECLARED_BUT_UNVERIFIED) | Chromium renderer: NO (RESOURCE_BLOCKED); second model: never |
| Qwen3-VL 4B | 4B-UD-Q4_K_XL | 3.4 | NOT_MEASURED | NOT_MEASURED | — | — | 9 s | abs 1/5, pair 0/5 → **UNQUALIFIED** | strong: structured_json, fact_preservation, html_css, long_context, design_criticism; weak: egyptian_arabic, date_reasoning | PRODUCTION_ALLOWED (verified) | PRIMARY editorial.write.bilingual; PRIMARY evidence.extract; PRIMARY live.structured; PRIMARY retrieval.long; PRIMARY design.html; PRIMARY design.reward; PRIMARY design.critique | NOT_MEASURED (no recorded peak) |
| Qwen3-VL 8B | 8B-UD-Q4_K_XL | 6.3 | NOT_MEASURED | NOT_MEASURED | — | — | 12 s | abs 3/5, pair 4/5 → **CANONICAL_640_ONLY** | strong: structured_json, english_writing, fact_preservation, structured_editorial, html_css, long_context, design_criticism; weak: egyptian_arabic, date_reasoning | PRODUCTION_ALLOWED (verified) | PRIMARY editorial.write.english; FALLBACK editorial.write.bilingual; PRIMARY editorial.write.checklist; FALLBACK evidence.extract; FALLBACK live.structured; FALLBACK retrieval.long; FALLBACK design.html; FALLBACK design.reward; FALLBACK design.critique; SECONDARY_FINALIST_PAIRWISE_JUDGE (640 px only) | NOT_MEASURED (no recorded peak) |
| Nemotron 3 Nano 4B | 4b | 2.9 | NOT_MEASURED | NOT_MEASURED | — | — | 39 s | UNSUPPORTED (text-only artifact) | strong: structured_json, fact_preservation, html_css, long_context, design_criticism; weak: egyptian_arabic, date_reasoning | DECLARED_BUT_UNVERIFIED | research / evaluation only (licence DECLARED_BUT_UNVERIFIED) | NOT_MEASURED (no recorded peak) |
| gpt-oss 20B | latest | 12.1 (weights freed) | NOT_MEASURED | NOT_MEASURED | — | — | 77 s | UNSUPPORTED (text-only artifact) | strong: structured_json, egyptian_arabic, fact_preservation, html_css, long_context, design_criticism, date_reasoning; weak: — | UNKNOWN | research / evaluation only (licence UNKNOWN) | NOT_MEASURED (no recorded peak) |
| Qwen3-VL 8B Q8_K_XL | 8B-Q8_K_XL | ~12.0 (registry) | NOT_MEASURED | NOT_MEASURED | — | — | NOT_MEASURED | abs NOT_RUN, pair NOT_RUN → **NOT_RUN** | strong: —; weak: — | UNKNOWN | research / evaluation only (licence UNKNOWN) | NOT_MEASURED (no recorded peak) |

Median inference latency = median wall time of the model's measured council calls (CPU only, one request at a time). Loaded / peak RAM = llama-server resident memory after the warm-up request and its high-water mark; recorded from 2026-10-30 — models measured earlier show NOT_MEASURED until they run again. A model may legitimately end with no production role: that is a benchmark result, not a failure of the benchmark.

## Load / unload cycles (resource scheduler accounting)

| model | rss before load (system) | rss after warm-up (server) | peak rss (server) | rss after unload (system) | swap used | load time | unload time |
|---|---|---|---|---|---|---|---|
| — | no cycle recorded yet under the scheduler | | | | | | |

**RESOURCE_BLOCKED decisions** (a refusal is recorded, never an OOM):

* none

