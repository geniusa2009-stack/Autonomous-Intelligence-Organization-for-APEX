# Production routing matrix

_Generated 2026-11-03 17:14 UTC by `apex-one reports` at commit `17c6ca3` from measured artifacts._

Built ONLY from measured evidence (`artifacts/bench/council_scores.json`, checker v2) and licence records. No global best model, no cross-task average. A task's score is the weakest of the capabilities it REQUIRES; a model measured below the floor (50, pre-registered) on any of them is rejected. **Primary / fallback must also be production-licensed and installed**; the best evaluation-only model is shown separately. Ties are broken by measured latency on the same evidence tasks (lower first).

## Rules

* **date arithmetic: DETERMINISTIC ENGINE ONLY** (`apex_one/core/dates.py`). The $0 firewall refuses every `date.*` task for every model. A model may EXPLAIN a date that code computed; it never computes one. Regression case: latest Saturday before a 1 Nov 2026 deadline with 10-day results = 2026-10-17.
* layout: APEX native engines; repair: native failure-specific repair; SVG: vector specialist when reachable, else native SVG assets
* vision: only judges that passed calibration in that mode (see below)

## Capability vector (measured, per model — bad results stay visible)

| capability | evidence task | gemma-multimodal | gemma3-12b | gpt-oss-20b | nemotron-nano-omni | qwen-vl-current | qwen3-vl-8b |
|---|---|---|---|---|---|---|---|
| editorial.write.general | english_factual_writing | 100 | 100 | NOT_MEASURED | 100 | 100 | 100 |
| editorial.write.egyptian_arabic | egyptian_arabic | 75 | 25 | 50 | 0 | 0 | 0 |
| editorial.write.fact_preserving | fact_preservation | 50 | 100 | 100 | 100 | 100 | 100 |
| editorial.write.bilingual | en_ar_mixing | 100 | 100 | 100 | 100 | 100 | 67 |
| editorial.write.structured | structured_editorial | 100 | 100 | NOT_MEASURED | 100 | 100 | 100 |
| editorial.write.long_context | long_context | 100 | 100 | 100 | 100 | 100 | 100 |
| extract.structured_json | structured_json | 100 | 100 | 100 | 100 | 100 | 100 |
| design.html_css | html_css | 100 | 100 | 100 | 100 | 100 | 100 |
| design.criticism | design_criticism | 100 | 50 | 100 | 100 | 100 | 100 |
| reasoning.general | reasoning | 0 | 0 | 100 | 0 | 0 | 0 |

| model | production licence | weights installed |
|---|---|---|
| gemma-multimodal | BLOCKED — DECLARED_BUT_UNVERIFIED | yes |
| gemma3-12b | BLOCKED — DECLARED_BUT_UNVERIFIED | yes |
| gpt-oss-20b | BLOCKED — UNKNOWN | no |
| nemotron-nano-omni | BLOCKED — DECLARED_BUT_UNVERIFIED | yes |
| qwen-vl-current | ALLOWED | yes |
| qwen3-vl-8b | ALLOWED | yes |

## Per-task routing

| task | requires (mandatory) | primary | fallback | best evaluation-only (licence-blocked) | rejected (below floor) | unmeasured |
|---|---|---|---|---|---|---|
| editorial.write.egyptian_guide | editorial.write.egyptian_arabic, editorial.write.fact_preserving | NONE passes → APEX native engine | — | gemma-multimodal (50, 10 s) | gemma3-12b (egyptian_arabic=25); nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| editorial.write.english | editorial.write.general | qwen-vl-current (100, 5 s) | qwen3-vl-8b (100, 12 s) | gemma-multimodal (100, 7 s) | — | gpt-oss-20b |
| editorial.write.bilingual | editorial.write.bilingual, editorial.write.fact_preserving | qwen-vl-current (100, 14 s) | qwen3-vl-8b (67, 35 s) | gemma3-12b (100, 46 s) | — | — |
| editorial.write.checklist | editorial.write.structured | qwen-vl-current (100, 6 s) | qwen3-vl-8b (100, 11 s) | gemma-multimodal (100, 6 s) | — | gpt-oss-20b |
| editorial.write | editorial.write.egyptian_arabic, editorial.write.fact_preserving | NONE passes → APEX native engine | — | gemma-multimodal (50, 10 s) | gemma3-12b (egyptian_arabic=25); nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| editorial.critique | editorial.write.egyptian_arabic | NONE passes → APEX native engine | — | gemma-multimodal (75, 4 s) | gemma3-12b (egyptian_arabic=25); nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| evidence.extract | extract.structured_json | qwen-vl-current (100, 10 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 11 s) | — | — |
| live.structured | extract.structured_json | qwen-vl-current (100, 10 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 11 s) | — | — |
| retrieval.long | editorial.write.long_context | qwen-vl-current (100, 113 s) | qwen3-vl-8b (100, 271 s) | gemma-multimodal (100, 61 s) | — | — |
| mission.analyze | reasoning.general | NONE passes → APEX native engine | — | gpt-oss-20b (100, 162 s) | gemma-multimodal (reasoning=0); gemma3-12b (reasoning=0); nemotron-nano-omni (reasoning=0); qwen-vl-current (reasoning=0); qwen3-vl-8b (reasoning=0) | — |
| opportunity.model | reasoning.general | NONE passes → APEX native engine | — | gpt-oss-20b (100, 162 s) | gemma-multimodal (reasoning=0); gemma3-12b (reasoning=0); nemotron-nano-omni (reasoning=0); qwen-vl-current (reasoning=0); qwen3-vl-8b (reasoning=0) | — |
| design.html | design.html_css | qwen-vl-current (100, 11 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 15 s) | — | — |
| design.reward | design.criticism | qwen-vl-current (100, 86 s) | qwen3-vl-8b (100, 165 s) | gpt-oss-20b (100, 77 s) | — | — |
| design.critique | design.criticism | qwen-vl-current (100, 86 s) | qwen3-vl-8b (100, 165 s) | gpt-oss-20b (100, 77 s) | — | — |

## Vision

* scoring council (absolute): none qualified → **Vision Quality scores = NOT_MEASURED**
* finalist A/B (pairwise, canonical input only): qwen3-vl-8b
  * qwen-vl-current: robustness **NOT_RUN** (failed canonical pairwise calibration (0/5)); not admitted — calibration not reliable
  * gemma-multimodal: robustness **NOT_RUN** (failed canonical pairwise calibration (0/5)); not admitted — calibration not reliable
  * qwen3-vl-8b: robustness **CANONICAL_640_ONLY** (unreliable at 320, 768, native, 1024; illegible (so not counted) at 480); ADMITTED
  * gemma3-12b: robustness **NOT_RUN** (failed canonical pairwise calibration (0/5)); not admitted — calibration not reliable

## Remote models

Remote free-tier routes were never measured here (provider hosts are network-blocked from this environment), so they appear in no primary/fallback cell. They stay routable only through the runtime prior, below every measured model, and are reported as unmeasured.


## Frozen production routing policy

Frozen at commit `17c6ca3` against evidence `council_scores.json`=7b6e9f78349f, `calibration_results.json`=858592959e12, `page_compare.json`=b8304f951193, `vision_robustness/gemma3-12b.json`=49a120afa9ed, `vision_robustness/qwen3-vl-8b.json`=da9ee24665d7 (`docs/evidence/production_routing_policy.json`). Any change to that evidence requires regenerating and re-reviewing this table. A model is never routed to merely because it is installed. There is no global best model: every route is decided on that task's mandatory capabilities only. **EVALUATION_ONLY** = the best measured model is not production-licensed; production runs the native engine (or nothing) instead.

| task | decision | primary | fallback | minimum requirement | licence state | deployment | reason |
|---|---|---|---|---|---|---|---|
| critical date arithmetic (date.*) | **DETERMINISTIC_ENGINE** | apex_one.core.dates | — | exact calendar arithmetic | n/a | PRODUCTION | permanently outside model reasoning; the $0 firewall refuses date.* for every model |
| critical locked facts (deadline, eligibility, funding) | **DETERMINISTIC_ENGINE** | evidence system + fact locks | HUMAN_REQUIRED for single-source critical claims | ≥ 2 independent sources or human confirmation | n/a | PRODUCTION | models may phrase a locked fact, never change it |
| editorial.write.egyptian_guide | **EVALUATION_ONLY** | gemma-multimodal (50) | APEX native engine | ≥ 50 on each of editorial.write.egyptian_arabic, editorial.write.fact_preserving | gemma-multimodal: DECLARED_BUT_UNVERIFIED | EVALUATION_ONLY | gemma-multimodal passes the floor but its licence is DECLARED_BUT_UNVERIFIED: NOT deployable (single qualified candidate). In production the APEX native engine runs this task. |
| editorial.write.english | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of editorial.write.general | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| editorial.write.bilingual | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (67) | ≥ 50 on each of editorial.write.bilingual, editorial.write.fact_preserving | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | qwen-vl-current measured higher (100 vs 67) on identical measurements |
| editorial.write.checklist | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of editorial.write.structured | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| editorial.write | **EVALUATION_ONLY** | gemma-multimodal (50) | APEX native engine | ≥ 50 on each of editorial.write.egyptian_arabic, editorial.write.fact_preserving | gemma-multimodal: DECLARED_BUT_UNVERIFIED | EVALUATION_ONLY | gemma-multimodal passes the floor but its licence is DECLARED_BUT_UNVERIFIED: NOT deployable (single qualified candidate). In production the APEX native engine runs this task. |
| editorial.critique | **EVALUATION_ONLY** | gemma-multimodal (75) | APEX native engine | ≥ 50 on each of editorial.write.egyptian_arabic | gemma-multimodal: DECLARED_BUT_UNVERIFIED | EVALUATION_ONLY | gemma-multimodal passes the floor but its licence is DECLARED_BUT_UNVERIFIED: NOT deployable (single qualified candidate). In production the APEX native engine runs this task. |
| evidence.extract | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of extract.structured_json | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| live.structured | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of extract.structured_json | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| retrieval.long | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of editorial.write.long_context | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| mission.analyze | **NO_QUALIFIED_MODEL** | APEX native engine | — | ≥ 50 on each of reasoning.general | n/a | PRODUCTION | no installed model passes reasoning.general at the floor |
| opportunity.model | **NO_QUALIFIED_MODEL** | APEX native engine | — | ≥ 50 on each of reasoning.general | n/a | PRODUCTION | no installed model passes reasoning.general at the floor |
| design.html | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of design.html_css | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| design.reward | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of design.criticism | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| design.critique | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | ≥ 50 on each of design.criticism | qwen-vl-current: PRODUCTION_ALLOWED (verified) / qwen3-vl-8b: PRODUCTION_ALLOWED (verified) | PRODUCTION | tie at 100 on identical measurements → the cheaper model (qwen-vl-current) |
| visual finalist comparison (A/B) | **PRIMARY** | qwen3-vl-8b as SECONDARY_FINALIST_PAIRWISE_JUDGE (CANONICAL_640_ONLY) | deterministic tournament order | pairwise ≥ 4/5, position bias ≤ 0.2, legible, stable repeats — at the canonical width | Apache-2.0 (PRODUCTION_ALLOWED) | PRODUCTION (advisory) | advisory only; canonical 640 px A4 renders of QA-passed finalists; never facts, dates, Arabic quality |
| visual quality scores (absolute council) | **NO_QUALIFIED_MODEL** | — | — | absolute ≥ 4/5 + ROBUSTLY_CALIBRATED | n/a | n/a | needs absolute calibration ≥ 4/5 AND ROBUSTLY_CALIBRATED; otherwise Vision Quality = NOT_MEASURED |
| SVG / vector assets | **NO_QUALIFIED_MODEL** | native SVG assets | — | GDB svg tasks at n ≥ 20 | n/a | PRODUCTION | specialist vector models (StarVector / OmniSVG) not activated: weights host egress-denied |
| document layout | **DETERMINISTIC_ENGINE** | APEX native layout engine + tournament | — | — | n/a | PRODUCTION | specialist layout models not activated |
| page design (HTML writing) | **DETERMINISTIC_ENGINE** | APEX native engine | — | win without a safety loss AND measured stability | n/a | PRODUCTION | no model page beat native without a safety loss |
| release approval | **HUMAN_REQUIRED** | authenticated approver (token) | — | token-authenticated approver bound to job id + artifact hash | n/a | PRODUCTION | hash-chained approval ledger |
| brand assets | **HUMAN_REQUIRED** | apex-one brand import | — | `apex-one brand validate` = VALID | n/a | PRODUCTION | original APEX package; placeholders fail |

### Measured evidence and abstention per route

| task | measured evidence (task=score @ token budget / checker) | abstention behaviour |
|---|---|---|
| critical date arithmetic (date.*) | tests/test_dates.py; every model's date task is irrelevant here | no model fallback exists by design |
| critical locked facts (deadline, eligibility, funding) | Fact Lock + deterministic QA | unlockable fact → AWAITING_HUMAN |
| editorial.write.egyptian_guide | gemma-multimodal egyptian_arabic=0 (contract not recorded); gemma-multimodal fact_preservation=50 (contract not recorded) | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| editorial.write.english | qwen-vl-current english_factual_writing=100 @500 tok/checker v2 | qwen3-vl-8b english_factual_writing=100 @500 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| editorial.write.bilingual | qwen-vl-current en_ar_mixing=100 @500 tok/checker v2; qwen-vl-current fact_preservation=100 @500 tok/checker v2 | qwen3-vl-8b en_ar_mixing=67 @500 tok/checker v2; qwen3-vl-8b fact_preservation=100 @500 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| editorial.write.checklist | qwen-vl-current structured_editorial=100 @500 tok/checker v2 | qwen3-vl-8b structured_editorial=100 @500 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| editorial.write | gemma-multimodal egyptian_arabic=0 (contract not recorded); gemma-multimodal fact_preservation=50 (contract not recorded) | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| editorial.critique | gemma-multimodal egyptian_arabic=0 (contract not recorded) | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| evidence.extract | qwen-vl-current structured_json=100 @500 tok/checker v2 | qwen3-vl-8b structured_json=100 @500 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| live.structured | qwen-vl-current structured_json=100 @500 tok/checker v2 | qwen3-vl-8b structured_json=100 @500 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → the stage pauses AWAITING_HUMAN (no native engine for this task); never a guessed answer |
| retrieval.long | qwen-vl-current long_context=100 @300 tok/checker v2 | qwen3-vl-8b long_context=100 @300 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → the stage pauses AWAITING_HUMAN (no native engine for this task); never a guessed answer |
| mission.analyze | — | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| opportunity.model | — | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| design.html | qwen-vl-current html_css=100 @700 tok/checker v2 | qwen3-vl-8b html_css=100 @700 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| design.reward | qwen-vl-current design_criticism=100 @600 tok/checker v2 | qwen3-vl-8b design_criticism=100 @600 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → APEX native engine (deterministic); never a silent empty section |
| design.critique | qwen-vl-current design_criticism=100 @600 tok/checker v2 | qwen3-vl-8b design_criticism=100 @600 tok/checker v2 | primary unavailable or its output fails validation → fallback model; both fail → the stage pauses AWAITING_HUMAN (no native engine for this task); never a guessed answer |
| visual finalist comparison (A/B) | VISION_JUDGE_ROBUSTNESS.md | judge unavailable or disagrees with itself across orders → deterministic tournament order |
| visual quality scores (absolute council) | VISION_JUDGE_ROBUSTNESS.md | Vision Quality = NOT_MEASURED (never a guessed score) |
| SVG / vector assets | — | native SVG assets |
| document layout | golden ULTRA (deterministic) | — |
| page design (HTML writing) | APEX_DESIGN_BENCH.md | — |
| release approval | — | job stays RELEASE_CANDIDATE |
| brand assets | — | Brand Production Gate FAIL |

### Qwen3-VL 4B vs Qwen3-VL 8B, per route (identical measurements only)

Rule: a higher measured score wins; an exact tie goes to the cheaper model (lower measured peak RAM, then latency); a model the machine would not admit in PRODUCTION_MODE never ranks above one it would; scores measured under different or unrecorded contracts are NOT compared (order provisional).

| task | 4B score | 8B score | identical measurements | 4B latency | 8B latency | 4B peak RAM | 8B peak RAM | 4B licence | 8B licence | 4B reliability | 8B reliability | production admission 4B / 8B | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| editorial.write.english | 100 | 100 | yes | 5.0 s | 12.3 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| editorial.write.bilingual | 100 | 67 | yes | 6.9 s | 17.4 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| editorial.write.checklist | 100 | 100 | yes | 6.0 s | 11.4 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| evidence.extract | 100 | 100 | yes | 10.1 s | 19.8 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| live.structured | 100 | 100 | yes | 10.1 s | 19.8 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| retrieval.long | 100 | 100 | yes | 112.6 s | 271.4 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| design.html | 100 | 100 | yes | 10.7 s | 20.3 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| design.reward | 100 | 100 | yes | 86.5 s | 164.9 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |
| design.critique | 100 | 100 | yes | 86.5 s | 164.9 s | 7.55 GB | 12.51 GB | PRODUCTION_ALLOWED (verified) | PRODUCTION_ALLOWED (verified) | 0 infrastructure errors in 11 council samples; 3/3 scheduled cycles clean | 0 infrastructure errors in 11 council samples; 1/1 scheduled cycles clean | ADMIT / ADMIT | 4B primary |

