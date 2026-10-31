# Local model resource matrix

_Generated 2026-10-31 00:41 UTC by `apex-one reports` at commit `b61868b` from measured artifacts._

Machine: 16.9 GB RAM (10^9 bytes), no swap, 4 CPU threads, no GPU; memory available with no model loaded: **16.0 GB**. On this machine compute scheduling is part of correctness: every stage is admitted BEFORE it starts (`apex_one/compute/local/resources.py`) with ADMIT / DEFER / RESOURCE_BLOCKED and an explicit reason; a clean RESOURCE_BLOCKED is a successful scheduler decision.

**Modes.** EVALUATION_MODE (one controlled benchmark process) needs ≥ 0.5 GB headroom after every reserve. PRODUCTION_MODE needs ≥ 2.0 GB AND ≥ 12% of MemTotal — a second job's worker, long uptimes and real pages are what evaluation never sees. Base reserves: os 0.3 GB, python_worker 0.3 GB, evaluation_artifacts 0.2 GB.

**Stage profiles** (what runs beside the model): TEXT_ONLY_MODEL_CALL = os 0.3 + python_worker 0.3 + evaluation_artifacts 0.2 + model_server_overhead 0.25 + renderer 0.05 GB; VISION_PAGE_JUDGING = os 0.3 + python_worker 0.3 + evaluation_artifacts 0.2 + model_server_overhead 0.25 + image_buffers 0.3 GB; PLAYWRIGHT_RENDER = os 0.3 + python_worker 0.3 + evaluation_artifacts 0.2 + renderer 1 GB; PDF_EXPORT = os 0.3 + python_worker 0.3 + evaluation_artifacts 0.2 + renderer 1 + pdf 0.5 GB; MODEL_PLUS_CHROMIUM = os 0.3 + python_worker 0.3 + evaluation_artifacts 0.2 + model_server_overhead 0.25 + renderer 1 + image_buffers 0.3 GB. Chromium reserve = 2 × its measured peak (0.5 GB, design-bench memory trace).

**Expected peak** = the measured peak RSS when this artifact has run before; otherwise the raw estimate (weights + GGUF-derived KV cache + 0.6 GB) × a safety multiplier: a same-family measured ratio if one exists, else max(1.25, worst observed ratio).

| model | quantization | disk GB | estimated peak GB | measured peak GB | prediction error | load time | warm-up | median inference latency | swap used (peak) | memory recovery ratio | safe in EVALUATION_MODE | safe in PRODUCTION_MODE | recommended concurrency | recommended role |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 3 4B | 4b-q4_K_M | 3.3 | 5.1 raw | NOT_MEASURED | — | — | — | 11 s | — | — | text ✓, vision ✓, +Chromium ✓ | text ✓, vision ✓, +Chromium ✓ | model + Chromium together; never two large models | research / evaluation only (licence DECLARED_BUT_UNVERIFIED) |
| Gemma 3 12B | 12b-q4_K_M | 8.2 | 12.0 raw | 13.86 | +1.9 GB (1.16×) | — | — | 18 s | — | — | text ✓, vision ✓, +Chromium ✗ | text ✗, vision ✗, +Chromium ✗ | sequential only: model, unload, then Chromium; never two large models | research / evaluation only (licence DECLARED_BUT_UNVERIFIED) |
| Qwen3-VL 4B | 4B-UD-Q4_K_XL | 3.4 | 5.2 raw | NOT_MEASURED | — | — | — | 9 s | — | — | text ✓, vision ✓, +Chromium ✓ | text ✓, vision ✓, +Chromium ✓ | model + Chromium together; never two large models | PRIMARY editorial.write.bilingual; PRIMARY evidence.extract; PRIMARY live.structured; PRIMARY retrieval.long; PRIMARY design.html; PRIMARY design.reward; PRIMARY design.critique |
| Qwen3-VL 8B | 8B-UD-Q4_K_XL | 6.3 | 8.1 raw | NOT_MEASURED | — | — | — | 12 s | — | — | text ✓, vision ✓, +Chromium ✓ | text ✓, vision ✓, +Chromium ✓ | model + Chromium together; never two large models | PRIMARY editorial.write.english; FALLBACK editorial.write.bilingual; PRIMARY editorial.write.checklist; FALLBACK evidence.extract; FALLBACK live.structured; FALLBACK retrieval.long; FALLBACK design.html; FALLBACK design.reward; FALLBACK design.critique; SECONDARY_FINALIST_PAIRWISE_JUDGE (640 px only) |
| Nemotron 3 Nano 4B | 4b | 2.9 | 3.5 raw | NOT_MEASURED | — | — | — | 39 s | — | — | text ✓, vision ✓, +Chromium ✓ | text ✓, vision ✓, +Chromium ✓ | model + Chromium together; never two large models | research / evaluation only (licence DECLARED_BUT_UNVERIFIED) |
| gpt-oss 20B | latest | 12.1 (weights freed) | 13.7 raw | NOT_MEASURED | — | — | — | 77 s | — | — | text ✗, vision ✗, +Chromium ✗ | text ✗, vision ✗, +Chromium ✗ | does not fit this machine; never two large models | research / evaluation only (licence UNKNOWN) |
| Qwen3-VL 8B Q8_K_XL | 8B-Q8_K_XL | ~12.0 (registry) | 13.6 raw | NOT_MEASURED | — | — | — | NOT_MEASURED | — | — | text ✗, vision ✗, +Chromium ✗ | text ✗, vision ✗, +Chromium ✗ | does not fit this machine; never two large models | research / evaluation only (licence UNKNOWN) |

✓/✗ = the scheduler's decision for that stage profile on an idle machine (text = text-only model calls; vision = page judging with image buffers; +Chromium = model and renderer resident together). Median inference latency = median wall time of the model's measured council calls (CPU only, one request at a time). Swap / recovery come from the last scheduled load-unload cycle (recorded from 2026-10-31); '—' = no cycle under the scheduler yet. A model may legitimately end with no production role — that is a benchmark result.

## Memory lifecycle per load / unload cycle (resource scheduler)

Available memory (GB) at each point; recovery = available after stabilisation / available before load (< 0.95 → MEMORY_LEAK_OR_RESIDUAL, and no next large model loads).

| model | mode | before load | after load | after warm-up | min while loaded | before unload | after exit | after stabilisation | recovery | server peak RSS | swap before / peak | major faults | load / warm-up / unload | latency degradation | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | no cycle recorded yet under the scheduler | | | | | | | | | | | | | | |

**RESOURCE_BLOCKED decisions** (a refusal is recorded, never an OOM):

* none

