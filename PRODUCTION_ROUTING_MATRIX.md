# Production routing matrix

_Generated 2026-10-31 00:41 UTC by `apex-one reports build` from measured artifacts._

Built ONLY from measured evidence (`artifacts/bench/council_scores.json`, checker v2) and licence records. No global best model, no cross-task average. A task's score is the weakest of the capabilities it REQUIRES; a model measured below the floor (50, pre-registered) on any of them is rejected. **Primary / fallback must also be production-licensed and installed**; the best evaluation-only model is shown separately. Ties are broken by measured latency on the same evidence tasks (lower first).

## Rules

* **date arithmetic: DETERMINISTIC ENGINE ONLY** (`apex_one/core/dates.py`). The $0 firewall refuses every `date.*` task for every model. A model may EXPLAIN a date that code computed; it never computes one. Regression case: latest Saturday before a 1 Nov 2026 deadline with 10-day results = 2026-10-17.
* layout: APEX native engines; repair: native failure-specific repair; SVG: vector specialist when reachable, else native SVG assets
* vision: only judges that passed calibration in that mode (see below)

## Capability vector (measured, per model — bad results stay visible)

| capability | evidence task | gemma-multimodal | gemma3-12b | gpt-oss-20b | nemotron-nano-omni | qwen-vl-current | qwen3-vl-8b |
|---|---|---|---|---|---|---|---|
| editorial.write.general | english_factual_writing | NOT_MEASURED | 100 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | 100 |
| editorial.write.egyptian_arabic | egyptian_arabic | 75 | 25 | 50 | 0 | 0 | 0 |
| editorial.write.fact_preserving | fact_preservation | 50 | 100 | 100 | 100 | 100 | 100 |
| editorial.write.bilingual | en_ar_mixing | 100 | 100 | 100 | 100 | 100 | 67 |
| editorial.write.structured | structured_editorial | NOT_MEASURED | 100 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | 100 |
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
| editorial.write.english | editorial.write.general | qwen3-vl-8b (100, 12 s) | — | gemma3-12b (100, 16 s) | — | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current |
| editorial.write.bilingual | editorial.write.bilingual, editorial.write.fact_preserving | qwen-vl-current (100, 16 s) | qwen3-vl-8b (67, 35 s) | gemma3-12b (100, 46 s) | — | — |
| editorial.write.checklist | editorial.write.structured | qwen3-vl-8b (100, 11 s) | — | gemma3-12b (100, 17 s) | — | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current |
| editorial.write | editorial.write.egyptian_arabic, editorial.write.fact_preserving | NONE passes → APEX native engine | — | gemma-multimodal (50, 10 s) | gemma3-12b (egyptian_arabic=25); nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| editorial.critique | editorial.write.egyptian_arabic | NONE passes → APEX native engine | — | gemma-multimodal (75, 4 s) | gemma3-12b (egyptian_arabic=25); nemotron-nano-omni (egyptian_arabic=0); qwen-vl-current (egyptian_arabic=0); qwen3-vl-8b (egyptian_arabic=0) | — |
| evidence.extract | extract.structured_json | qwen-vl-current (100, 9 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 11 s) | — | — |
| live.structured | extract.structured_json | qwen-vl-current (100, 9 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 11 s) | — | — |
| retrieval.long | editorial.write.long_context | qwen-vl-current (100, 91 s) | qwen3-vl-8b (100, 271 s) | gemma-multimodal (100, 61 s) | — | — |
| mission.analyze | reasoning.general | NONE passes → APEX native engine | — | gpt-oss-20b (100, 162 s) | gemma-multimodal (reasoning=0); gemma3-12b (reasoning=0); nemotron-nano-omni (reasoning=0); qwen-vl-current (reasoning=0); qwen3-vl-8b (reasoning=0) | — |
| opportunity.model | reasoning.general | NONE passes → APEX native engine | — | gpt-oss-20b (100, 162 s) | gemma-multimodal (reasoning=0); gemma3-12b (reasoning=0); nemotron-nano-omni (reasoning=0); qwen-vl-current (reasoning=0); qwen3-vl-8b (reasoning=0) | — |
| design.html | design.html_css | qwen-vl-current (100, 11 s) | qwen3-vl-8b (100, 20 s) | gemma-multimodal (100, 15 s) | — | — |
| design.reward | design.criticism | qwen-vl-current (100, 80 s) | qwen3-vl-8b (100, 165 s) | gpt-oss-20b (100, 77 s) | — | — |
| design.critique | design.criticism | qwen-vl-current (100, 80 s) | qwen3-vl-8b (100, 165 s) | gpt-oss-20b (100, 77 s) | — | — |

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

Frozen at commit `b61868b` against evidence `council_scores.json`=ddf126b0894d, `calibration_results.json`=858592959e12, `page_compare.json`=119855e92746, `vision_robustness/gemma3-12b.json`=49a120afa9ed, `vision_robustness/qwen3-vl-8b.json`=da9ee24665d7 (`docs/evidence/production_routing_policy.json`). Any change to that evidence requires regenerating and re-reviewing this table. A model is never routed to merely because it is installed.

| task | decision | primary | fallback | why |
|---|---|---|---|---|
| critical date arithmetic (date.*) | **DETERMINISTIC_ENGINE** | apex_one.core.dates | — | permanently outside model reasoning; the $0 firewall refuses date.* for every model |
| critical locked facts (deadline, eligibility, funding) | **DETERMINISTIC_ENGINE** | evidence system + fact locks | HUMAN_REQUIRED for single-source critical claims | models may phrase a locked fact, never change it |
| editorial.write.egyptian_guide | **NO_QUALIFIED_MODEL** | APEX native engine | — | no production-licensed model passes editorial.write.egyptian_arabic, editorial.write.fact_preserving at the floor |
| editorial.write.english | **PRIMARY** | qwen3-vl-8b (100) | — | requires editorial.write.general; production-licensed, installed, ≥ floor |
| editorial.write.bilingual | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (67) | requires editorial.write.bilingual, editorial.write.fact_preserving; production-licensed, installed, ≥ floor |
| editorial.write.checklist | **PRIMARY** | qwen3-vl-8b (100) | — | requires editorial.write.structured; production-licensed, installed, ≥ floor |
| editorial.write | **NO_QUALIFIED_MODEL** | APEX native engine | — | no production-licensed model passes editorial.write.egyptian_arabic, editorial.write.fact_preserving at the floor |
| editorial.critique | **NO_QUALIFIED_MODEL** | APEX native engine | — | no production-licensed model passes editorial.write.egyptian_arabic at the floor |
| evidence.extract | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | requires extract.structured_json; production-licensed, installed, ≥ floor |
| live.structured | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | requires extract.structured_json; production-licensed, installed, ≥ floor |
| retrieval.long | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | requires editorial.write.long_context; production-licensed, installed, ≥ floor |
| mission.analyze | **NO_QUALIFIED_MODEL** | APEX native engine | — | no production-licensed model passes reasoning.general at the floor |
| opportunity.model | **NO_QUALIFIED_MODEL** | APEX native engine | — | no production-licensed model passes reasoning.general at the floor |
| design.html | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | requires design.html_css; production-licensed, installed, ≥ floor |
| design.reward | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | requires design.criticism; production-licensed, installed, ≥ floor |
| design.critique | **PRIMARY** | qwen-vl-current (100) | qwen3-vl-8b (100) | requires design.criticism; production-licensed, installed, ≥ floor |
| visual finalist comparison (A/B) | **PRIMARY** | qwen3-vl-8b as SECONDARY_FINALIST_PAIRWISE_JUDGE (CANONICAL_640_ONLY) | deterministic tournament order | advisory only; canonical 640 px A4 renders of QA-passed finalists; never facts, dates, Arabic quality |
| visual quality scores (absolute council) | **NO_QUALIFIED_MODEL** | — | — | needs absolute calibration ≥ 4/5 AND ROBUSTLY_CALIBRATED; otherwise Vision Quality = NOT_MEASURED |
| SVG / vector assets | **NO_QUALIFIED_MODEL** | native SVG assets | — | specialist vector models (StarVector / OmniSVG) not activated: weights host egress-denied |
| document layout | **DETERMINISTIC_ENGINE** | APEX native layout engine + tournament | — | specialist layout models not activated |
| page design (HTML writing) | **DETERMINISTIC_ENGINE** | APEX native engine | — | no model page beat native without a safety loss |
| release approval | **HUMAN_REQUIRED** | authenticated approver (token) | — | hash-chained approval ledger |
| brand assets | **HUMAN_REQUIRED** | apex-one brand import | — | original APEX package; placeholders fail |
