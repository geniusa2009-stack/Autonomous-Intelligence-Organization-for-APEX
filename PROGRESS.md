# APEX ONE ULTRA — Progress log

Last updated: 2026-10-12 (session 3: real intelligence validation)

**Overall maturity: FOUNDATION COMPLETE + PARTIAL ACTIVATION. Not finished.** Real local model inference runs
($0, llama.cpp), but every cloud free tier is network-blocked here, no local model licence is verified for
production, no specialist design checkpoint is reachable, original APEX brand assets are missing, and no real
opportunity job can reach its primary sources from this container. See ULTRA_QUALITY_REPORT.md.

## Session 1 (foundation) — phases 0–13: DONE (111 tests) — see git history up to 7th commit.

## Session 2 — phases 14–30

| Phase | Status | Evidence |
|---|---|---|
| 14 Live providers | DONE (honest statuses) | LIVE_PROVIDER_REPORT.md; `apex-one providers live-test`; 5 cloud providers NETWORK_BLOCKED, Gemini CREDENTIALS_REQUIRED, local llama.cpp LIVE_TESTED per model (stored in artifacts/live/local_live_results.json) |
| 14b Local inference | DONE | llama.cpp built from source; 4 GGUF models acquired from Docker Hub `ai/` (sha256 verified): Gemma 3 4B, Qwen3-VL 4B, Nemotron 3 Nano 4B, gpt-oss 20B; `apex-one local status|acquire|serve|stop` |
| 15 General council benchmark | RUNNING (CPU, sequential) | apex_one/compute/benchmark/council.py, scripts/run_local_council.py; results → artifacts/bench/council_scores.json → registry overlay (`capability_source: apex-benchmark`) |
| 16 Design arsenal activation | DONE (evidence per system) | DESIGN_MODEL_ACTIVATION.md, config/design_activation.yaml — 30 systems; none of the specialist checkpoints is reachable (HF denied) |
| 17 APEX design bench (15 page types) | NATIVE DONE, LLM RUNNING | APEX_DESIGN_BENCH.md, apex_one/lab/benchmarks/apex_design_bench.py; native baseline vs tournament measured on all 15 types; local LLM page writers queued (5 key types each) |
| 18 Vision Council | WIRED; JUDGE CALIBRATION RUNNING | apex_one/vision/council.py; VISION_QA runs only calibrated-reliable judges (stamped by model digest), else NOT_MEASURED; weak pages → MUTATION |
| 19 PosterReward | PROTOCOL_REIMPLEMENTED (weights unreachable) | apex_one/vision/pairwise.py: order-swapped, consistency-required, strict-majority pairwise; disagreements + failures stored |
| 20 Comprehension ≥ 95, rhythm ≥ 93 | DONE | golden ULTRA J-9aee654ead70: comprehension 98.9, rhythm 94.0, all 10 targets PASS (incl. new arabic_typography 100) |
| 21 Genome extraction | DONE (no approved APEX documents supplied yet) | apex_one/design/genome_extraction.py, `apex-one genome ingest|principles`; tested on our own PDF only |
| 22 Anti-copy / anti-repetition | DONE | apex_one/design/similarity.py; tournament novelty; per-job qa/anti_copy.json (brand vs layout similarity separate) |
| 23 Ultra evolution | DONE | ULTRA = 64 seeded candidates for important pages (APEX_ULTRA_CANDIDATES ≤ 256), 844 candidates in golden ULTRA; pairwise finalists when reliable judges exist |
| 24 Mixture of design experts | DONE | apex_one/design/models/moe.py: semantic gate (type → reading family → default), measured evidence, margin rule, licence-gated |
| 25 A/B/C preference dataset | DONE (no human labels yet) | `apex-one preference sheet|record`; winner, ranking, reason, controlled tags; never auto-trained |
| 26 GraphicDesignBench | PACKAGE + PROVIDER DONE; LOCAL RUN QUEUED | lica-gdb 0.2.1; apex_one/lab/benchmarks/gdb_provider.py via the $0 broker; full dataset on HF is unreachable → smoke bundle only |
| 27 Asset contracts | DONE; ASSETS MISSING | assets/apex/, config/asset_contract.yaml, `apex-one assets validate`; compiler embeds what validates; Brand Production Gate blocks real jobs (currently 4 assets MISSING) |
| 28 Arabic typography | DONE (deterministic) + council TypographyJudge when calibrated | qa/typography: letter-spacing, italics, leading, punctuation, tatweel; rendered detect cases 4/4 |
| 29 Real opportunity job | BLOCKED (environment) | `create-guide "Berea College Fall 2027"` → BLOCKED at SOURCE_DISCOVERY; berea.edu, educationusa, studyinthestates, commonapp, travel.state.gov all denied by egress proxy (403) |
| 30 Adversarial audit | DONE; 12 of 13 findings fixed, 1 partial | independent audit → commit "Phase 30 adversarial audit fixes"; partial: approval now needs a named approver, but the local API still has no authentication (bind to 127.0.0.1 only) |

Test status: `.venv/bin/python -m pytest` → 146 passed.
Push status: pushed to origin/claude/charming-archimedes-2guzc9.


## Session 3 — real intelligence validation (2026-10-12)

| Item | Status | Evidence |
|---|---|---|
| 1 Background evaluations | RUNNING (resumable queue) | scripts/validation_queue.py, artifacts/bench/queue_state.json; restarted after a container move (native llama.cpp build died with SIGILL → portable rebuild) |
| 2 No blind overall ranking | DONE | MODEL_COMPARISON_MATRIX.md (per task, same-task winners only); router has no "overall" fallback |
| 3 Qwen3-VL contradiction | INVESTIGATING | VISION_CALIBRATION_ANALYSIS.md; experiments E0–E4 in the queue |
| 4 Stronger vision judge | RUNNING | remote vision routes all blocked/keyless; Qwen3-VL 8B and Gemma 3 12B queued with the same 5-case calibration + pairwise order inversion |
| 5 Design activation states | DONE | DESIGN_MODEL_ACTIVATION.md: one final_state per system (LIVE_TESTED 1, ADAPTER_TESTED_ONLY 1, NETWORK_BLOCKED 6, HARDWARE_BLOCKED 7, DEPENDENCY_MISSING 6, RESEARCH_ONLY 8, NOT_IMPLEMENTED 1) |
| 6 Licence verification | DONE | config/license_verifications.yaml (`apex-one license verify-local`): Qwen3-VL 4B Apache-2.0 allowed; others blocked with reasons |
| 7 Authentication | DONE | apex_one/core/auth.py, tests/test_auth.py; token identity, forged-name rejection, hash-chained ledger |
| 8 Brand asset gate | DONE (assets still missing → FAIL) | `apex-one brand import`, brand fingerprint |
| 9 Model writing vs native | NATIVE MEASURED, MODELS RUNNING | apex_one/lab/benchmarks/page_compare.py, APEX_DESIGN_BENCH.md |
| 10 Date reasoning | DONE | apex_one/core/dates.py; firewall blocks date.* for models; regression test |
| 11 Task-specific routing | DONE | config/task_routing.yaml |
| 12 GraphicDesignBench | DONE (n=2 smoke) | 6/39 tasks runnable offline; 33 skipped (HF dataset) — not scored as zero |
| 13 Real opportunity job | PARTIAL (research stage) | CNCF LFX Mentorship 2027 Term 1 from CNCF's repository: deadline 2027-02-16 extracted; AWAITING_HUMAN |
| 14 Maturity | DONE | ULTRA_QUALITY_REPORT.md |
| 15 Regression guard | DONE | tests/test_pipeline.py::test_golden_ultra_quality_never_regresses |
