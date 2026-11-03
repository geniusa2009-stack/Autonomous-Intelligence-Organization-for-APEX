# APEX ONE ULTRA — Quality Report (shortest path to a production candidate)

_Updated 2026-11-03. Every number comes from an artifact produced in this container (`docs/evidence/`). The
authoritative blocker list is PRODUCTION_BLOCKERS.md (live probes). Human-only work is in HUMAN_ACTIONS_REQUIRED.md.
Regenerate with `apex-one reports`._

## Maturity (independent dimensions; the acceptance rule is `config/production_acceptance.yaml`)

| dimension | status | required for production | why |
|---|---|---|---|
| BRAND_ASSETS_VALIDATED | **NO** | yes | `apex-one brand validate` → INCOMPLETE (no official package yet; intake spec BRAND_PACKAGE_INTAKE.md) |
| AUTHORIZED_APPROVER_CONFIGURED | **NO** | yes | authentication and artifact binding are complete and tested; no approver exists yet (APPROVER_SETUP.md) |
| REAL_OPPORTUNITY_VALIDATED | **NO** | yes | no real job has reached RELEASE_CANDIDATE; the offline evidence-pack path is ready (REAL_OPPORTUNITY_PILOT.md) |
| PRODUCTION_LOAD_VALIDATED | **YES** | yes | 10/10 load scenarios PASS in PRODUCTION_MODE with the real production model and real Chromium |
| OFFLINE_PIPELINE_VALIDATED | **YES** | yes | golden ULTRA: comprehension 98.9, rhythm 94.0, Arabic typography 100; hard regression test |
| LOCAL_MODEL_ROUTING_VALIDATED | **YES** | yes | 9 production model routes on identical measurements with verified licences; 3 EVALUATION_ONLY routes run native in production |
| ARCHITECTURE_COMPLETE | **YES** | no | every stage exists, is wired and tested |
| DESIGN_MODEL_VALIDATION | **PARTIAL** | no | GDB 6/39 tasks offline (n=2); native wins or ties every page type |
| VISION_GATE | **PARTIAL** | no | no robust judge; Qwen3-VL 8B is a canonical-640 advisory finalist judge only; absolute visual quality NOT_MEASURED |
| REMOTE_FREE_COMPUTE_VALIDATED | **NO** | no | remote free tiers egress-denied; Gemini keyless |
| PRODUCTION_READY | **NO** | — | `apex-one release check` → BLOCKED on BRAND_ASSETS_VALIDATED, AUTHORIZED_APPROVER_CONFIGURED, REAL_OPPORTUNITY_VALIDATED — all three need a person |

The not-required dimensions are EXPERIMENTAL / OPTIONAL IMPROVEMENT: no release decision depends on them
(PRODUCTION_ACCEPTANCE.md). The validated system is frozen as `APEX_ONE_OFFLINE_VALIDATED_BASELINE`
(`docs/evidence/APEX_ONE_OFFLINE_VALIDATED_BASELINE.json`).

## Memory safety

- **Evaluation headroom: 1.4 GB.** Previously 0.5 GB, which was smaller than a miss that had already happened. It is derived, not chosen: ceil_0.1(worst measured miss 1.06 GB + run-to-run peak spread 0.30 GB). The 1.06 GB miss is Qwen3-VL 8B, admitted at 11.45 GB and measured at 12.51 GB.
- **The requirement only rises.** New evidence can raise it, never lower it.
- **Production headroom: 2.02 GB** = max(2.0 GB, 12% of MemTotal, evaluation + 0.5 GB). It is always stricter than evaluation.
- **Consequence:** Gemma 3 12B (peak 14.1 GB) no longer fits this machine even for evaluation. Its earlier benchmarks ran under the old rule.
- **Peak used for admission:** the scheduler now uses the highest peak ever measured for an artifact.

## Routing (capability-specific; no global best model)

Qwen3-VL 4B vs 8B, on identical measurements only. The 4B's older rows were re-measured under the 8B's exact
contract.

| route | 4B | 8B | 4B / 8B latency | decision |
|---|---|---|---|---|
| English, checklist, extraction, live, long retrieval, HTML, design reward/critique | 100 | 100 | 5–113 s / 11–271 s | **tie → 4B (7.55 GB vs 12.51 GB, 2–2.4× faster)** |
| bilingual (EN/AR mixing) | 100 | 67 | 6.9 s / 17.4 s | **4B (measured higher)** |

- **Licences:** both Apache-2.0, verified.
- **Reliability:** 0 infrastructure errors in 11 samples each.
- **Admission:** both admitted in PRODUCTION_MODE.
- **The 8B** stays the fallback and the canonical-640 advisory finalist judge.

Routes whose best model is unlicensed are EVALUATION_ONLY; the native engine runs them in production:
- Egyptian guide: Gemma 3 4B, 50 (its weakest required capability is fact preservation 50, at the floor).
- Critique: Gemma 3 4B, 75.

## Load test (PRODUCTION_MODE, Qwen3-VL 4B, real Chromium renders, SQLite)

**10/10 PASS**, 0 failed jobs, no swap, memory floor held in every scenario.

| scenario | key results |
|---|---|
| saturation | 14 jobs rejected with back-pressure, never as failures |
| model busy | one server slot: model requests queue; no failures |
| database busy | 8 s exclusive lock; writes waited up to 4.1 s |
| server crash | our own SIGKILL classified MODEL_SERVER_CRASH; supervisor restarted once; recovered in 8.9 s; 4/4 jobs done |
| restart recovery | a fresh queue resumed in 10.8 s; exactly-once side effects |
| memory pressure | 63 DEFERs; renders waited instead of starting; at least 2.69 GB free throughout; all jobs completed after release |
| all scenarios | throughput ≈ 17 jobs/min, CPU-bound on the model |

Fixes the harness forced:
- **Supervisor recovery is serialized.** Concurrent workers restart a dead server exactly once.
- **OOM needs evidence:** the kernel `oom_kill` counter or an allocator failure in the log. A bare SIGKILL is not evidence.
- **Render admission reserves memory before Chromium allocates.**

## Release control and evidence

- **Approval binding.** An approval binds the token identity, job id, timestamp, final PDF/HTML hashes, decision and comment in the hash-chained ledger.
  - An approval for bytes the approver did not review is refused.
  - FINAL refuses an artifact changed after approval.
  - A typed name never authenticates.
- **Brand contract.** It now requires font licences, usage constraints and per-asset checksums. `apex-one brand validate` → VALID / INCOMPLETE / INVALID. Placeholders are never VALID.
- **Evidence packs.** `apex-one evidence init|check|run` validates a real opportunity from saved official pages/PDFs offline.
  - A test pack runs the whole pipeline. It stops only at the brand gate.
  - Packs on reserved test domains never count as real.
- **Gemini.** `apex-one vision validate-gemini` is ready and resumable. It exits 2 (BLOCKED_NO_KEY) today.

## Quality rule (never lowered)

Reader comprehension ≥ 95 · rhythm ≥ 93 · Arabic typography ≥ 98 — enforced by
`tests/test_pipeline.py::test_golden_ultra_quality_never_regresses`.

## NOT_MEASURED

- Absolute visual quality.
- Any Gemini or remote judge.
- Qwen3-VL 8B Q8_K_XL and gpt-oss 20B: RESOURCE_BLOCKED, never downloaded.
- 33/39 GDB tasks.
- Model-page run-to-run stability.
- Long-duration (soak) production load.
