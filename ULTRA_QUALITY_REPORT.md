# APEX ONE ULTRA — Quality Report (model validation phase)

_Updated 2026-10-31. Every number comes from an artifact produced in this container (`docs/evidence/`). The
generated reports are FINAL_MODEL_MATRIX, PRODUCTION_ROUTING_MATRIX, VISION_JUDGE_ROBUSTNESS,
MODEL_SERVER_RELIABILITY, LOCAL_MODEL_RESOURCE_MATRIX, APEX_DESIGN_BENCH and MODEL_ACTIVATION_REPORT. Regenerate
them with `apex-one reports`._

## Maturity (each level separate — not "finished")

| Level | Status | Why |
|---|---|---|
| ARCHITECTURE_COMPLETE | **YES** | Every stage exists, is wired and is tested. |
| OFFLINE_PIPELINE_VALIDATED | **YES** | Golden ULTRA: all 10 targets PASS (comprehension 98.9, rhythm 94.0, Arabic typography 100). A hard test guards against regression. |
| LOCAL_MODEL_ROUTING_VALIDATED | **YES (evaluation scope)** | 6 local models measured per task under one contract. The routing policy is frozen. A model is routed only when it passes the task's floor and its licence allows production. |
| DESIGN_MODEL_VALIDATION | **PARTIAL** | GraphicDesignBench: 6/39 tasks run offline (n=2 smoke). Specialist checkpoints are network- or hardware-blocked. Native wins or ties every page type. |
| VISION_GATE | **PARTIAL** | No ROBUSTLY_CALIBRATED judge. Qwen3-VL 8B is CANONICAL_640_ONLY, so it serves only as an advisory secondary finalist judge. Absolute VisionCouncil = NOT_MEASURED. |
| REMOTE_FREE_COMPUTE_VALIDATED | **NO** | Remote free tiers are egress-denied (proxy CONNECT 403). Gemini is reachable, but there is no key. |
| REAL_OPPORTUNITY_VALIDATED | **NO (research stage)** | The CNCF LFX 2027 job is AWAITING_HUMAN: a single-source deadline, and the funding and eligibility pages are unreachable. |
| PRODUCTION_READY | **NO** | Brand assets are missing, there is no approver, no real job has reached release candidate, and the vision gate is partial. |

## What each model is actually good at (measured)

Full table: FINAL_MODEL_MATRIX.md. There is no overall score.

* **Qwen3-VL 4B** (Apache-2.0, PRODUCTION_ALLOWED; peak 7.3 GB). Scores 100 on structured JSON, English writing,
  checklist, fact preservation, HTML/CSS, long context and design criticism. Fastest model (9 s).
  - Egyptian Arabic: 0. Date reasoning: 0. Vision judging: position bias 1.0, UNQUALIFIED.
  - **Role:** PRIMARY for the English, checklist, extraction, retrieval and design-text tasks.
* **Qwen3-VL 8B** (Apache-2.0; peak 12.5 GB). Same text profile as the 4B. It is the only model that is a usable
  visual judge, and only at canonical 640 px (4/4/4, bias 0.0; every other width 3/5).
  - **Role:** FALLBACK for the 4B, plus SECONDARY_FINALIST_PAIRWISE_JUDGE.
* **Gemma 3 12B** (DECLARED_BUT_UNVERIFIED; peak 14.1 GB). Scores 100 on structured JSON, English, editorial,
  fact preservation, HTML/CSS, long context and EN/AR mixing.
  - Design criticism: 50. Egyptian Arabic: 25 (below the floor). Date reasoning: 0, a QUALITY_ZERO (it answered
    2026-10-24 for 2026-10-17).
  - Vision judging: UNQUALIFIED. It answered "A" in 10 of 10 pairwise calls, so its position bias is 1.0.
  - **Role:** evaluation only. Parameter count bought nothing measurable over the Qwen 4B.
* **Gemma 3 4B** (peak 6.4 GB). Egyptian Arabic 75 is the best local result, but still below the floor. Fact
  preservation: 50. **Role:** evaluation only.
* **Nemotron 3 Nano 4B** (peak 4.9 GB). Strong on text; Egyptian Arabic 0. Text-only. **Role:** evaluation only.
* **gpt-oss 20B**. The only model with 100 on date reasoning (budget 4096) and 50 on Egyptian Arabic. Its licence
  is UNKNOWN, and it no longer fits the scheduler's admission (expected peak 21.1 GB). **Role:** none.

Deterministic engines own dates, locked facts, layout and page design. Humans own release and brand.
Egyptian-Arabic guide writing has NO_QUALIFIED_MODEL, so the native engine writes it.

## Phase results

* **Resource scheduler.** Every load and stage is admitted before it starts (ADMIT / DEFER / RESOURCE_BLOCKED, with
  a reason). There are two modes: EVALUATION (≥ 0.5 GB headroom) and PRODUCTION (≥ 2.0 GB and ≥ 12%). The full
  memory lifecycle is recorded for every cycle.
  - All five scheduled cycles recovered (ratio 0.99 to 1.02) with zero swap.
  - Peak-memory estimates were low on the first model of each family, by up to 4.4 GB. The multiplier now uses the
    worst measured same-family ratio (1.54 for Qwen3-VL).
* **Q8_K_XL.** RESOURCE_BLOCKED before download. The multiplicative estimate gives 21.0 GB. An additive
  cross-check gives 18.2 GB: the Q4 build's measured 12.5 GB plus 5.7 GB of extra weights. Both exceed the 16.1 GB
  machine. Nothing about quantization was measured, so no claim is made.
* **Server reliability.** The 14-mode fault drill passes. No supervisor incident occurred in real runs. One queue
  incident (two queue processes) failed closed, and is now prevented by a lock and a same-port DEFER.
* **Native vs model pages.** KEEP NATIVE on every page type. Qwen3-VL 8B's Checklist page ties native on every
  dimension. A tie is not a win while the model's stability is NOT_MEASURED.

## Quality rule (never lowered)

Reader comprehension ≥ 95 · rhythm ≥ 93 · Arabic typography ≥ 98. These are enforced by
`tests/test_pipeline.py::test_golden_ultra_quality_never_regresses`.

## NOT_MEASURED

* Absolute visual quality (VisionCouncil).
* Qwen3-VL 8B Q8_K_XL and gpt-oss 20B under the scheduler (RESOURCE_BLOCKED).
* gpt-oss English writing and editorial.
* GDB on 33 of 39 tasks (Hugging Face dataset unreachable).
* Run-to-run stability of model-written pages.
* Every remote free provider.
* PRODUCTION_MODE behaviour under real concurrent load.
