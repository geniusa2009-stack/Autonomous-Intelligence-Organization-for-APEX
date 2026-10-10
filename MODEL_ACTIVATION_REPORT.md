# Model Activation Report (Phases 14–15)

_Generated 2026-10-10 16:42 UTC by `apex-one reports build` from measured artifacts._

Real local inference: llama.cpp `llama-server` (built from source in this container) serving GGUF models pulled from the Docker Hub `ai/` OCI catalogue, each blob sha256-verified. One model in RAM at a time (4 vCPU, 15.7 GB RAM, no GPU).

## Acquired models

| key | registry model | source | size | vision | live structured test | licence state |
|---|---|---|---|---|---|---|
| gpt-oss-20b-mxfp4 | gpt-oss-20b | `ai/gpt-oss:latest` | 12.11 GB | False | PENDING | UNKNOWN (lic-gpt-oss) |
| nemotron-3-nano-4b-q4km | nemotron-nano-omni | `ai/nemotron-3-nano:4b` | 2.90 GB | False | PENDING | UNKNOWN (lic-nvidia-nemotron-nano) |
| qwen3-vl-4b-q4kxl | qwen-vl-current | `ai/qwen3-vl:4B-UD-Q4_K_XL` | 3.38 GB | True | PENDING | UNKNOWN (lic-qwen-open); artifact ships `LICENSE` |
| gemma3-4b-q4km | gemma-multimodal | `ai/gemma3:4b-q4_K_M` | 3.34 GB | True | LIVE_TESTED (correct) | UNKNOWN (lic-gemma) |

## General council benchmark (Phase 15)

Tasks are scored by deterministic checkers (no model grades another model): date reasoning, Egyptian Arabic register, EN/AR term mixing, structured JSON extraction (exact fields), fact preservation through rewriting, RTL HTML/CSS contract, design criticism coverage, long-context needle, and (vision models) order-swapped pairwise visual hierarchy.

PENDING: the council benchmark has not produced scores yet.

## Vision judge calibration (Phase 18)

Each vision model reviews a known-good page and five deliberately broken variants (low contrast, card overuse, gradient, cramped, no hierarchy). A judge is RELIABLE only if it scores the good page above the broken one on the targeted role in ≥ 60 % of cases. Unreliable judges never influence gates.

PENDING: calibration has not completed.
