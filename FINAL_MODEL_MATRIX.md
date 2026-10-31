# Final model matrix

_Generated 2026-10-31 02:19 UTC by `apex-one reports` at commit `bdc6bce` from measured artifacts._

One normalized table for the six local models. Every cell is ONE measured task under the same contract (same prompt, checker version, temperature 0, 500-token budget unless a cell says otherwise). **There is no overall score and no overall winner**: the models were not all measured on the same task set, and an average would hide a 0 behind unrelated 100s. Cells that did not measure say why (NOT_MEASURED / ERROR <kind>); none is ever counted as 0. GraphicDesignBench ran 2 samples per task — enough to show a model runs end to end, never enough to rank models.

**Identical measured-task set across all six models:** structured_json, egyptian_arabic, fact_preservation, html_css, long_context, design_criticism, reasoning — the only tasks on which a side-by-side reading is fair.

| model | structured_json | english_writing | egyptian_arabic | fact_preservation | structured_editorial | html_css | long_context | design_criticism | date_reasoning | vision_calibration | gdb_tasks_supported | median_latency | ram | production_license_state |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 3 4B | 100 | 100 | 75 | 50 | 100 | 100 | 100 | 100 | 0 QUALITY_ZERO | abs 1/5, pair 0/5 → **UNQUALIFIED** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | 11 s (common set) | 6.2 loaded / 6.2 peak GB | DECLARED_BUT_UNVERIFIED |
| Gemma 3 12B | 100 | 100 | 25 | 100 | 100 | 100 | 100 | 50 | 0 QUALITY_ZERO | abs 1/5, pair 0/5 → **UNQUALIFIED** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | 29 s (common set) | 13.5 loaded / 13.9 peak GB | DECLARED_BUT_UNVERIFIED |
| Qwen3-VL 4B | 100 | 100 | 0 QUALITY_ZERO | 100 | 100 | 100 | 100 | 100 | 0 QUALITY_ZERO | abs 1/5, pair 0/5 → **UNQUALIFIED** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | 9 s (common set) | 7.1 loaded / 7.2 peak GB | PRODUCTION_ALLOWED (verified) |
| Qwen3-VL 8B | 100 | 100 | 0 QUALITY_ZERO | 100 | 100 | 100 | 100 | 100 | 0 QUALITY_ZERO | abs 3/5, pair 4/5 → **CANONICAL_640_ONLY** | 6 measured (n=2 each); 9 UNSUPPORTED; 24 SKIPPED | 20 s (common set) | 11.7 loaded / 12.2 peak GB | PRODUCTION_ALLOWED (verified) |
| Nemotron 3 Nano 4B | 100 | 100 | 0 QUALITY_ZERO | 100 | 100 | 100 | 100 | 100 | 0 QUALITY_ZERO (re-run budget 4096) | UNSUPPORTED (text-only artifact) | NOT_RUN | 39 s (common set) | 4.2 loaded / 4.8 peak GB | DECLARED_BUT_UNVERIFIED |
| gpt-oss 20B | 100 | NOT_MEASURED | 50 | 100 (re-run budget 4096) | NOT_MEASURED | 100 | 100 | 100 | 100 (re-run budget 4096) | UNSUPPORTED (text-only artifact) | NOT_RUN | 77 s (common set) | NOT_MEASURED | UNKNOWN |

Scores are 0–100 per deterministic checker (checker version 2). `abs` = absolute calibration, `pair` = order-swapped pairwise calibration (≥ 4/5 needed for either), the bold state is the resolution-robustness status (VISION_JUDGE_ROBUSTNESS.md). Median latency is over the identical task set only, so it is comparable. RAM = llama-server resident memory (`/proc`), recorded from 2026-10-30; earlier runs did not record it.

## Provenance per model

| model | artifact (quantization) | model fingerprint (GGUF sha256) | council token budget | outputs complete | failures by kind | evaluation commits |
|---|---|---|---|---|---|---|
| Gemma 3 4B | 4b-q4_K_M | `sha256:04a43a22e8d2` | 500 | 11/11 tasks scored | none | bdc6bce |
| Gemma 3 12B | 12b-q4_K_M | `sha256:15b8fd9d8672` | 300, 500, 600, 700, 900 | 11/11 tasks scored | none | 0463a23, b61868b |
| Qwen3-VL 4B | 4B-UD-Q4_K_XL | `sha256:a5563711a524` | 500 | 11/11 tasks scored | none | bdc6bce |
| Qwen3-VL 8B | 8B-UD-Q4_K_XL | `sha256:e3d1a6e87c5c` | 300, 500, 600, 700, 900 | 11/11 tasks scored | none | bdc6bce |
| Nemotron 3 Nano 4B | 4b | `sha256:e515c9ceb10a` | 500, 4096 | 10/10 tasks scored | none | bdc6bce |
| gpt-oss 20B | latest | `weights not on disk` | 4096 | 8/8 tasks scored | none | before commit tracking |
| Qwen3-VL 8B Q8_K_XL | 8B-Q8_K_XL | `weights not on disk` | — | 0/0 tasks scored | none | before commit tracking |

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


## Gemma 3 12B — full results

| item | result |
|---|---|
| live structured-output test | LIVE_TESTED, structured answer correct=True |
| absolute vision calibration | 1/5 (ties on target 3, inversions 1) → FAILS the 4/5 bar |
| pairwise calibration (both orders) | 0/5; cases low_contrast=False, card_overuse=False, gradient=False, cramped=False, no_hierarchy=False |
| robustness 640 px (pair-order + 3 repeats) | correct per repeat [0, 0, 0], order sensitivity 1.0, run variance 0, legible True |
| **vision judge status** | **UNQUALIFIED** (canonical 640 px fails A_defect_discrimination, B_pair_order_stability, D_repeat_stability (correct per repeat [0, 0, 0], position_bias_rate 1.0, legible=True)) |
| calibration investigation | {'E2': {'correct': 0, 'valid': 5}, 'E3': {'correct': 2, 'valid': 5}, 'E4': {'correct': 2, 'valid': 5}} |
| structured_json | 100 — PASSED 29.4 s; 4/4 fields exact |
| english_writing | 100 — PASSED 15.7 s; {"date_kept": true, "amount_kept": true, "no_new_numbers": true, "english": true, "short": |
| egyptian_arabic | 25 — FAILED 9.3 s; dialect_markers=1 msa=0 number_kept=True |
| fact_preservation | 100 — PASSED 17.5 s; dates=['2026-11-01'] money=[('USD', 50.0)] |
| structured_editorial | 100 — PASSED 17.0 s; {"three_bullets": true, "only_bullets": true, "date_kept": true, "amount_kept": true, "iel |
| html_css | 100 — PASSED 38.9 s; {"rtl": true, "h2": true, "p": true, "no_script": true, "no_gradient": true, "bdi_or_ltr": |
| long_context | 100 — PASSED 191.7 s; got 2027-01-20 |
| design_criticism | 50 — PASSED 229.8 s; {"hierarchy": true, "contrast": false, "line_length": true, "cards": false} |
| date_reasoning | 0 QUALITY_ZERO — FAILED 9.3 s; expected 2026-10-17, got 2026-10-24 |
| visual_hierarchy (1 pair) | 50 — PASSED 139.2 s; order-swapped answers correct=[True, False] |
| en_ar_mixing | 100 — PASSED 28.1 s; latin_terms=['deadline', 'deposit', 'TOEFL'] transliterated=False arabic_words=34 |
| GDB category-1 | top1_accuracy=0.00, top5_accuracy=0.00, macro_f1=0.00 |
| GDB layout-4 | accuracy=0.00, f1=0.00, precision=0.00 |
| GDB layout-5 | mae=16.00, mse=320.00 |
| GDB typography-1 | accuracy_top1=0.50, f1_montserrat=0.67, f1_macro=0.67 |
| GDB svg-1 | accuracy=1.00 |
| GDB template-1 | accuracy=0.50, precision=0.50, recall=0.50 |
| model-written pages (5 types) | produced 5/5, critical pages 3, contract violations 0, median latency 547.6 s |
| RAM | 13.5 loaded / 13.9 peak GB |
| licence | DECLARED_BUT_UNVERIFIED — evaluation use only unless PRODUCTION_ALLOWED |

## Qwen3-VL 8B Q8_K_XL — stronger-judge candidate

| item | result |
|---|---|
| live structured-output test | {'at': '2026-10-31T02:15:44', 'info': "RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leaves -5.9 GB of the machine's 16.1 GB < required headroom 0.5 GB (estimate 13.6 GB (weights 12.0 + KV 1.0 + compute 0.6 GB) x 1.54 (same-family measured ratio (qwen3-vl)))", 'commit': 'bdc6bce'} |
| absolute vision calibration | NOT_RUN |
| pairwise calibration (both orders) | NOT_RUN |
| **vision judge status** | **NOT_RUN**  |
| RAM | NOT_MEASURED |
| licence | UNKNOWN — evaluation use only unless PRODUCTION_ALLOWED |
| failed steps | acquire: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; live: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; pcalib: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; robust:640: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; robust:native: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; robust:320: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; robust:480: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; robust:768: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav; robust:1024: RESOURCE_BLOCKED: EVALUATION_MODE: need 22.1 GB (peak 21.0 + reserves 1.10) leav |
