# APEX ONE ULTRA — Quality Report (Real Intelligence Validation Phase)

_Updated 2026-10-12. Every number comes from an artifact produced in this container (see `docs/evidence/` and the
generated reports: LIVE_PROVIDER_REPORT, MODEL_ACTIVATION_REPORT, MODEL_COMPARISON_MATRIX,
VISION_CALIBRATION_ANALYSIS, DESIGN_MODEL_ACTIVATION, APEX_DESIGN_BENCH). Regenerate with `apex-one reports`._

## Maturity (explicit — not "finished")

| Level | Status | Why |
|---|---|---|
| ARCHITECTURE_COMPLETE | **YES** | every planned stage exists, is wired and tested (state machine, $0 compute, research, editorial, design, QA, release, learning) |
| OFFLINE_PIPELINE_VALIDATED | **YES** | golden ULTRA benchmark reaches the authenticated human gate with all 10 targets PASS (comprehension 98.9, rhythm 94.0, Arabic typography 100) — regression-protected by a hard test |
| LOCAL_MODELS_VALIDATED | **YES (evaluation scope)** | 4 open-weight models run on local llama.cpp; each LIVE_TESTED with a correct structured answer; council benchmark measured per task |
| DESIGN_MODELS_PARTIALLY_VALIDATED | **PARTIAL** | native design engines validated on 15 page types; GraphicDesignBench ran for real (6/39 tasks, n=2 smoke); every specialist design checkpoint is NETWORK/HARDWARE-blocked or unreleased |
| VISION_GATE_VALIDATED | **NOT_VALIDATED** | no vision model has passed calibration (Gemma 3 4B 0/5, Qwen3-VL 4B 1/5 absolute); larger candidates and pairwise calibration are being measured; until one passes, Vision Quality stays NOT_MEASURED |
| LIVE_REMOTE_ROUTING_VALIDATED | **NOT_VALIDATED** | NVIDIA NIM, Groq, OpenRouter, Cloudflare and Hugging Face are denied by the egress proxy; Gemini is reachable but no key was provided |
| REAL_OPPORTUNITY_VALIDATED | **NOT_VALIDATED (research stage only)** | real job on CNCF LFX Mentorship 2027 Term 1 (primary source: CNCF's own repository) extracted the real deadline 2027-02-16 and stopped AWAITING_HUMAN: single-source critical claim + funding/eligibility pages unreachable |
| PRODUCTION_READY | **NOT_PRODUCTION_READY** | original APEX brand assets missing (Brand Production Gate FAIL), no real opportunity has reached release candidate, vision gate not validated |

## What changed in this phase

* **Release control is authenticated.** Approver identity comes only from a token (hashes stored, never the
  token); forged names are rejected; every decision lands in a hash-chained, tamper-evident ledger.
* **Licences verified from artifact evidence, not memory.** Qwen3-VL 4B: Apache-2.0 declared by two independent
  local sources → PRODUCTION_ALLOWED. gpt-oss 20B (usage-policy text unavailable), Gemma 3 (Gemma terms), Nemotron
  (NVIDIA licence) stay production-blocked. Licences are per artifact (no sibling inheritance).
* **Empirical, task-specific routing.** Each task is ranked only on its measured evidence (`config/task_routing.yaml`);
  there is no "overall" fallback; date arithmetic is deterministic and models are blocked from it.
* **Brand import + fingerprint.** `apex-one brand import <folder>` validates and installs only a complete, valid
  package; edits after import fail the gate. Until real assets exist: BRAND_PRODUCTION_GATE = FAIL.
* **Model writing vs native.** Separate metrics (text fidelity, facts, HTML/CSS validity, RTL, overflow, hierarchy,
  editability, novelty, APEX similarity, layout repetition, page comprehension). Native stays the designer unless a
  model wins without a safety loss.
* **Real sources exposed real gaps** (table rows, yearless dates, application windows) — fixed and tested.
* **Infrastructure:** llama.cpp rebuilt portably after the native build died with SIGILL on a new host; the
  evaluation queue is resumable across container restarts.

## Quality rule (never lowered)

reader comprehension ≥ 95 · rhythm ≥ 93 · Arabic typography ≥ 98 — enforced by `tests/test_pipeline.py::
test_golden_ultra_quality_never_regresses` against `tests/baselines/golden_ultra.json`.

## Remaining blockers

1. Original APEX brand package (logo, logo-on-dark, robot, brand.yaml, fonts) → `apex-one brand import <folder>`.
2. Network: huggingface.co (model weights, GDB dataset), provider APIs, and official opportunity sites
   (e.g. docs.linuxfoundation.org, www.berea.edu) are denied by the environment's egress policy.
3. A human confirmation for single-source critical facts (`apex-one facts confirm`), and the funding/eligibility
   sources for the real job.
4. A calibrated vision judge (≥ 4/5) — none yet.
5. Gemini key (optional free multimodal route) if you want a remote judge candidate.
