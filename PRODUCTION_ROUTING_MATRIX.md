# Production routing matrix

_Generated 2026-10-30 13:14 UTC by `apex-one reports build` from measured artifacts._

Built ONLY from measured evidence (`artifacts/bench/council_scores.json`, checker v2) and licence records. No global best model, no cross-task average. A task's score is the weakest of the capabilities it REQUIRES; a model measured below the floor (50, pre-registered) on any of them is rejected. **Primary / fallback must also be production-licensed and installed**; the best evaluation-only model is shown separately. Ties are broken by measured latency on the same evidence tasks (lower first).

## Rules

* **date arithmetic: DETERMINISTIC ENGINE ONLY** (`apex_one/core/dates.py`). The $0 firewall refuses every `date.*` task for every model. A model may EXPLAIN a date that code computed; it never computes one. Regression case: latest Saturday before a 1 Nov 2026 deadline with 10-day results = 2026-10-17.
* layout: APEX native engines; repair: native failure-specific repair; SVG: vector specialist when reachable, else native SVG assets
* vision: only judges that passed calibration in that mode (see below)

## Capability vector (measured, per model — bad results stay visible)

| capability | evidence task | gemma-multimodal | gpt-oss-20b | nemotron-nano-omni | qwen-vl-current | qwen3-vl-8b |
|---|---|---|---|---|---|---|
| editorial.write.general | english_factual_writing | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| editorial.write.egyptian_arabic | egyptian_arabic | 75 | 50 | 0 | 0 | 0 |
| editorial.write.fact_preserving | fact_preservation | 50 | 100 | 100 | 100 | 100 |
| editorial.write.bilingual | en_ar_mixing | 100 | 100 | 100 | 100 | 67 |
| editorial.write.structured | structured_editorial | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| editorial.write.long_context | long_context | 100 | 100 | 100 | 100 | 100 |
| extract.structured_json | structured_json | 100 | 100 | 100 | 100 | 100 |
| design.html_css | html_css | 100 | 100 | 100 | 100 | 100 |
| design.criticism | design_criticism | 100 | 100 | 100 | 100 | 100 |
| reasoning.general | reasoning | 0 | 100 | 0 | 0 | 0 |

| model | production licence | weights installed |
|---|---|---|
| gemma-multimodal | BLOCKED | yes |
| gpt-oss-20b | BLOCKED | no |
| nemotron-nano-omni | BLOCKED | yes |
| qwen-vl-current | ALLOWED | yes |
| qwen3-vl-8b | ALLOWED | yes |

## Per-task routing

| task | requires (mandatory) | primary | fallback | best evaluation-only (licence-blocked) | rejected (below floor) | unmeasured |
|---|---|---|---|---|---|---|
| editorial.write.egyptian_guide | editorial.write.egyptian_arabic, editorial.write.fact_preserving | NONE passes → APEX native engine | — | gemma-multimodal (50, 10 s) | nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| editorial.write.english | editorial.write.general | NONE passes → APEX native engine | — | — | — | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b |
| editorial.write.bilingual | editorial.write.bilingual, editorial.write.fact_preserving | qwen-vl-current (100, 16 s) | qwen3-vl-8b (67, 35 s) | nemotron-nano-omni (100, 75 s) | — | — |
| editorial.write.checklist | editorial.write.structured | NONE passes → APEX native engine | — | — | — | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b |
| editorial.write | editorial.write.egyptian_arabic, editorial.write.fact_preserving | NONE passes → APEX native engine | — | gemma-multimodal (50, 10 s) | nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| editorial.critique | editorial.write.egyptian_arabic | NONE passes → APEX native engine | — | gemma-multimodal (75, 4 s) | nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| evidence.extract | extract.structured_json | qwen-vl-current (100, 9 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 11 s) | — | — |
| live.structured | extract.structured_json | qwen-vl-current (100, 9 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 11 s) | — | — |
| retrieval.long | editorial.write.long_context | qwen-vl-current (100, 91 s) | qwen3-vl-8b (100, 271 s) | gemma-multimodal (100, 61 s) | — | — |
| mission.analyze | reasoning.general | NONE passes → APEX native engine | — | gpt-oss-20b (100, 162 s) | gemma-multimodal (reasoning=0); nemotron-nano-omni (reasoning=0); qwen-vl-current (reasoning=0); qwen3-vl-8b (reasoning=0) | — |
| opportunity.model | reasoning.general | NONE passes → APEX native engine | — | gpt-oss-20b (100, 162 s) | gemma-multimodal (reasoning=0); nemotron-nano-omni (reasoning=0); qwen-vl-current (reasoning=0); qwen3-vl-8b (reasoning=0) | — |
| design.html | design.html_css | qwen-vl-current (100, 11 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 15 s) | — | — |
| design.reward | design.criticism | qwen-vl-current (100, 80 s) | qwen3-vl-8b (100, 165 s) | gpt-oss-20b (100, 77 s) | — | — |
| design.critique | design.criticism | qwen-vl-current (100, 80 s) | qwen3-vl-8b (100, 165 s) | gpt-oss-20b (100, 77 s) | — | — |

## Vision

* scoring council (absolute): none qualified → **Vision Quality scores = NOT_MEASURED**
* finalist A/B (pairwise, canonical input only): qwen3-vl-8b
  * qwen-vl-current: robustness **INCOMPLETE** (no robustness results); not admitted — calibration not reliable
  * gemma-multimodal: robustness **INCOMPLETE** (no robustness results); not admitted — calibration not reliable
  * qwen3-vl-8b: robustness **CANONICAL_640_ONLY** (not yet measured: 320, 480, 768, native, 1024); ADMITTED

## Remote models

Remote free-tier routes were never measured here (provider hosts are network-blocked from this environment), so they appear in no primary/fallback cell. They stay routable only through the runtime prior, below every measured model, and are reported as unmeasured.

