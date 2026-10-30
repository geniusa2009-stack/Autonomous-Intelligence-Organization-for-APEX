# Final model matrix

_Generated 2026-10-30 23:37 UTC by `apex-one reports` at commit `551042c` from measured artifacts._

One normalized table for the six local models. Every cell is ONE measured task under the same contract (same prompt, checker version, temperature 0, 500-token budget unless a cell says otherwise). **There is no overall score and no overall winner**: the models were not all measured on the same task set, and an average would hide a 0 behind unrelated 100s. Cells that did not measure say why (NOT_MEASURED / ERROR <kind>); none is ever counted as 0. GraphicDesignBench ran 2 samples per task — enough to show a model runs end to end, never enough to rank models.

**Identical measured-task set across all six models:** none — the only tasks on which a side-by-side reading is fair.

| model | structured_json | english_writing | egyptian_arabic | fact_preservation | structured_editorial | html_css | long_context | design_criticism | date_reasoning | vision_calibration | gdb_tasks_supported | median_latency | ram | production_license_state |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 3 4B | 100 | NOT_MEASURED | 75 | 50 | NOT_MEASURED | 100 | 100 | 100 | 0 QUALITY_ZERO | abs 1/5, pair 0/5 → **UNQUALIFIED** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | NOT_MEASURED | NOT_MEASURED | DECLARED_BUT_UNVERIFIED |
| Gemma 3 12B | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | abs 1/5, pair 0/5 → **UNQUALIFIED** | NOT_RUN | NOT_MEASURED | 13.6 loaded / 13.9 peak GB | DECLARED_BUT_UNVERIFIED |
| Qwen3-VL 4B | 100 | NOT_MEASURED | 0 QUALITY_ZERO | 100 | NOT_MEASURED | 100 | 100 | 100 | 0 QUALITY_ZERO | abs 1/5, pair 0/5 → **UNQUALIFIED** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | NOT_MEASURED | NOT_MEASURED | PRODUCTION_ALLOWED (verified) |
| Qwen3-VL 8B | 100 | 100 | 0 QUALITY_ZERO | 100 | 100 | 100 | 100 | 100 | 0 QUALITY_ZERO | abs 3/5, pair 4/5 → **CANONICAL_640_ONLY** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | NOT_MEASURED | NOT_MEASURED | PRODUCTION_ALLOWED (verified) |
| Nemotron 3 Nano 4B | 100 | NOT_MEASURED | 0 QUALITY_ZERO | 100 | NOT_MEASURED | 100 | 100 | 100 | 0 QUALITY_ZERO (re-run budget 4096) | UNSUPPORTED (text-only artifact) | NOT_RUN | NOT_MEASURED | NOT_MEASURED | DECLARED_BUT_UNVERIFIED |
| gpt-oss 20B | 100 | NOT_MEASURED | 50 | 100 (re-run budget 4096) | NOT_MEASURED | 100 | 100 | 100 | 100 (re-run budget 4096) | UNSUPPORTED (text-only artifact) | NOT_RUN | NOT_MEASURED | NOT_MEASURED | UNKNOWN |

Scores are 0–100 per deterministic checker (checker version 2). `abs` = absolute calibration, `pair` = order-swapped pairwise calibration (≥ 4/5 needed for either), the bold state is the resolution-robustness status (VISION_JUDGE_ROBUSTNESS.md). Median latency is over the identical task set only, so it is comparable. RAM = llama-server resident memory (`/proc`), recorded from 2026-10-30; earlier runs did not record it.

## Provenance per model

| model | artifact (quantization) | model fingerprint (GGUF sha256) | council token budget | outputs complete | failures by kind | evaluation commits |
|---|---|---|---|---|---|---|
| Gemma 3 4B | 4b-q4_K_M | `sha256:04a43a22e8d2` | — | 9/9 tasks scored | none | before commit tracking |
| Gemma 3 12B | 12b-q4_K_M | `sha256:15b8fd9d8672` | — | 0/0 tasks scored | none | 0463a23 |
| Qwen3-VL 4B | 4B-UD-Q4_K_XL | `sha256:a5563711a524` | — | 9/9 tasks scored | none | before commit tracking |
| Qwen3-VL 8B | 8B-UD-Q4_K_XL | `sha256:e3d1a6e87c5c` | 300, 500, 600, 700, 900 | 11/11 tasks scored | none | before commit tracking |
| Nemotron 3 Nano 4B | 4b | `sha256:e515c9ceb10a` | 4096 | 8/8 tasks scored | none | before commit tracking |
| gpt-oss 20B | latest | `weights not on disk` | 4096 | 8/8 tasks scored | none | before commit tracking |
| Qwen3-VL 8B Q8_K_XL | 8B-Q8_K_XL | `weights not on disk` | — | 0/0 tasks scored | none | before commit tracking |

## Load / unload cycles (resource scheduler accounting)

| model | rss before load (system) | rss after warm-up (server) | peak rss (server) | rss after unload (system) | swap used | load time | unload time |
|---|---|---|---|---|---|---|---|
| — | no cycle recorded yet under the scheduler | | | | | | |

**RESOURCE_BLOCKED decisions** (a refusal is recorded, never an OOM):

* none


## Gemma 3 12B — full results

| item | result |
|---|---|
| live structured-output test | LIVE_TESTED, structured answer correct=True |
| absolute vision calibration | 1/5 (ties on target 3, inversions 1) → FAILS the 4/5 bar |
| pairwise calibration (both orders) | 0/5; cases low_contrast=False, card_overuse=False, gradient=False, cramped=False, no_hierarchy=False |
| robustness 640 px (pair-order + 3 repeats) | correct per repeat [0, 0, 0], order sensitivity 1.0, run variance 0, legible True |
| **vision judge status** | **UNQUALIFIED** (canonical 640 px fails A_defect_discrimination, B_pair_order_stability, D_repeat_stability (correct per repeat [0, 0, 0], position_bias_rate 1.0, legible=True)) |
| RAM | 13.6 loaded / 13.9 peak GB |
| licence | DECLARED_BUT_UNVERIFIED — evaluation use only unless PRODUCTION_ALLOWED |

## Qwen3-VL 8B Q8_K_XL — stronger-judge candidate

| item | result |
|---|---|
| live structured-output test | NOT_RUN |
| absolute vision calibration | NOT_RUN |
| pairwise calibration (both orders) | NOT_RUN |
| **vision judge status** | **NOT_RUN**  |
| RAM | NOT_MEASURED |
| licence | UNKNOWN — evaluation use only unless PRODUCTION_ALLOWED |
