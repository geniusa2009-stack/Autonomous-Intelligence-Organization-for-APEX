# APEX ONE ULTRA — Quality Report (Phases 14–30)

_Session 2, 2026-10-10. Every number below comes from an artifact produced in this container; sources in
`docs/evidence/` and the per-topic reports (LIVE_PROVIDER_REPORT.md, MODEL_ACTIVATION_REPORT.md,
DESIGN_MODEL_ACTIVATION.md, APEX_DESIGN_BENCH.md)._

## Verdict

**NOT FINISHED.** Maturity: *foundation complete + partial real activation*. Checked against the completion rule:

| Completion condition | State |
|---|---|
| Models mock-only? | **No** — 4 open-weight models run for real on local llama.cpp ($0); LIVE_TESTED per model as measured |
| Design systems registry-only? | **Partly** — native engines run; every specialist checkpoint is unreachable (HF denied) → recorded per system |
| Vision NOT_MEASURED? | **Until a judge calibrates reliably, yes** — the council is wired and refuses to score with uncalibrated judges |
| Targets missed? | **No** on the golden benchmark — all 10 targets PASS (ULTRA) |
| Assets placeholders? | **Yes** — original APEX logo/robot/brand manifest missing → Brand Production Gate blocks every real job |
| Licence blockers? | **Yes** — all local model licences UNKNOWN in the registry → evaluation-only until a human verifies |
| Live routing never run? | **No** — live routing runs on local routes; all cloud free tiers NETWORK_BLOCKED from here |
| Real job reached human approval? | **No** — official sources unreachable (egress 403); the job blocks at SOURCE_DISCOVERY |

## Golden benchmark (synthetic, ULTRA) — J-9aee654ead70

State HUMAN_APPROVAL / RELEASE_CANDIDATE (never FINAL without a human). 844 layout candidates evaluated
(64 seeded per important page). Critical gates PASS; `brand_production_assets` NOT_APPLICABLE_SYNTHETIC (would block
a real job).

| Target | Threshold | Measured |
|---|---|---|
| reader_comprehension | 95 | **98.9** (was 93.3 at end of session 1) |
| cross_page_rhythm | 93 | **94.0** (was 92.0) |
| arabic_typography (new) | 98 | **100.0** |
| typography | 95 | 98.8 |
| visual_hierarchy | 95 | 99.2 |
| apex_brand_fit | 95 | 100 |
| editorial_quality | 95 | 100 |
| rtl_visual_quality | 98 | 100 |
| print_fidelity | 98 | 100 |
| novelty | 90 | 98.5 |

How comprehension and rhythm were fixed without lowering thresholds (Phase 20): snapshot money/eligibility facts
became scannable `stat` blocks; opening/APEX Take no longer reuse the loud manifesto archetype (hero fatigue);
the document-level tournament penalises flat visual weight measured from real screenshots (ink density).

## What is real now

* **$0 local inference**: llama.cpp built from source; Gemma 3 4B, Qwen3-VL 4B, Nemotron 3 Nano 4B, gpt-oss 20B
  pulled as OCI artifacts with sha256 verification; one model in RAM at a time.
* **Live provider test**: real structured-output task per route; LIVE_TESTED only when the answer is correct.
* **Council benchmark** with deterministic checkers (no model grades another); scores overwrite registry priors.
* **Vision Council**: six roles, structured problems with severity/region/repair/confidence, median across models,
  disagreements stored; **only calibration-reliable judges count** (good vs 5 broken pages, all checks valid,
  stamped by model digest).
* **Pairwise (PosterReward protocol)**: order-swapped, consistency-required, strict majority; failures ≠ bias.
* **Design**: 15-page-type APEX Design Bench; ultra evolution (64–256 candidates); mixture of design experts with
  semantic routing + margin rule; anti-copy with brand vs layout similarity reported separately per job.
* **Learning inputs**: genome extraction from approved/rejected documents (principles, never copies); A/B/C
  preference sheets and records (winner, ranking, reason, tags); nothing trains automatically.
* **Arabic typography**: letter-spacing (critical: breaks joining), synthetic italics, Arabic leading, Latin
  punctuation, tatweel stretching (the «الـ + English term» convention is correctly allowed).

## Adversarial audit (Phase 30)

An independent read-only audit found 13 issues (5 major); 12 are fixed, 1 partial — see the commit
"Phase 30 adversarial audit fixes". The majors were: the brand gate validated files the compiler did not embed;
a judge could be "reliable" on one data point and calibration results were unstamped; pairwise said MEASURED when
nothing ran; a stale vision report could survive a mutation; report prose was not derived from data. Sound by
audit: the $0 path (every adapter asserts the firewall decision before any network call), production licence
enforcement, fact locking, and the human gate.

## Blockers that need a human or another network

1. Original APEX brand assets → `assets/apex/` (contract in `config/asset_contract.yaml`).
2. Network access to official sources (or saved official sources) for a real opportunity.
3. Licence verification for any model you want to write content (`apex-one license verify`).
4. Cloud free-tier keys on a network that allows those providers.
5. A GPU + HF access for specialist design checkpoints.
6. Authentication on the local API before exposing it.

See NEXT_ACTIONS.md for the exact commands.
