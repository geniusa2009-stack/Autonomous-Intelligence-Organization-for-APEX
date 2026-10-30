# Model Activation Report (Phases 14–15)

_Generated 2026-10-30 17:00 UTC by `apex-one reports build` from measured artifacts._

Real local inference: llama.cpp `llama-server` (built from source in this container) serving GGUF models pulled from the Docker Hub `ai/` OCI catalogue, each blob sha256-verified. One model in RAM at a time (4 vCPU, 15.7 GB RAM, no GPU).

## Acquired models

| key | registry model | source | size | vision | live structured test | licence state |
|---|---|---|---|---|---|---|
| gpt-oss-20b-mxfp4 | gpt-oss-20b | `ai/gpt-oss:latest` | NOT ACQUIRED | False | LIVE_TESTED (correct) | UNKNOWN (lic-gpt-oss) |
| nemotron-3-nano-4b-q4km | nemotron-nano-omni | `ai/nemotron-3-nano:4b` | 2.90 GB | False | LIVE_TESTED (correct) | UNKNOWN (lic-nvidia-nemotron-nano) |
| qwen3-vl-4b-q4kxl | qwen-vl-current | `ai/qwen3-vl:4B-UD-Q4_K_XL` | 3.38 GB | True | LIVE_TESTED (correct) | PRODUCTION_ALLOWED (lic-qwen3-vl-apache); artifact ships `LICENSE` |
| gemma3-4b-q4km | gemma-multimodal | `ai/gemma3:4b-q4_K_M` | 3.34 GB | True | LIVE_TESTED (correct) | UNKNOWN (lic-gemma) |
| qwen3-vl-8b-q4kxl | qwen3-vl-8b | `ai/qwen3-vl:8B-UD-Q4_K_XL` | 6.31 GB | True | LIVE_TESTED (correct) | PRODUCTION_ALLOWED (lic-qwen3-vl-8b); artifact ships `LICENSE` |
| gemma3-12b-q4km | gemma3-12b | `ai/gemma3:12b-q4_K_M` | NOT ACQUIRED | True | PENDING | UNKNOWN (lic-gemma3-12b) |

## General council benchmark (Phase 15)

Tasks are scored by deterministic checkers (no model grades another model): date reasoning, Egyptian Arabic register, EN/AR term mixing, structured JSON extraction (exact fields), fact preservation through rewriting, RTL HTML/CSS contract, design criticism coverage, long-context needle, and (vision models) order-swapped pairwise visual hierarchy.

| model | reasoning | egyptian_arabic | en_ar_mixing | english_factual_writing | structured_editorial | structured_json | fact_preservation | html_css | design_criticism | long_context | visual_hierarchy | measured tasks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-multimodal | 0 | 75 | 100 | — | — | 100 | 50 | 100 | 100 | 100 | 50 | 9/11 |
| nemotron-nano-omni | 0 | 0 | 100 | — | — | 100 | 100 | 100 | 100 | 100 | — | 8/11 |
| qwen-vl-current | 0 | 0 | 100 | — | — | 100 | 100 | 100 | 100 | 100 | 100 | 9/11 |
| gpt-oss-20b | 100 | 50 | 100 | — | — | 100 | 100 | 100 | 100 | 100 | — | 8/11 |
| qwen3-vl-8b | 0 | 0 | 67 | — | — | 100 | 100 | 100 | 100 | 100 | 100 | 9/11 |

`—` = NOT_MEASURED (not run, not applicable, or empty output because a reasoning model spent its token budget on hidden reasoning; re-run with a larger budget). **No overall mean is shown**: the rows cover different task sets, and an average would hide a 0 (e.g. Egyptian Arabic or date reasoning) behind unrelated 100s. Compare per task; routing uses the capability vector in PRODUCTION_ROUTING_MATRIX.md. Checker version 2: scores recomputed from stored outputs.

These measured scores overwrite the registry's prior estimates (`capability_source: apex-benchmark`), so the CapabilityRouter now ranks local models by what they actually did here.

## Vision judge calibration (Phase 18)

Each vision model reviews a known-good page and five deliberately broken variants (low contrast, card overuse, gradient, cramped, no hierarchy). A judge is RELIABLE only if it scores the good page above the broken one on the targeted role in ≥ 60 % of cases. Unreliable judges never influence gates.

| model | low_contrast | card_overuse | gradient | cramped | no_hierarchy | discrimination | reliable |
|---|---|---|---|---|---|---|---|
| gemma-multimodal | False | True | False | False | False | 0.20 | **False** |
| qwen-vl-current | False | False | True | False | False | 0.20 | **False** |
| qwen3-vl-8b | False | True | True | False | True | 0.60 | **False** |
