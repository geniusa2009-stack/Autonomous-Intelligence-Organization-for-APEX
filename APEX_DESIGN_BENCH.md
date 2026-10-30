# APEX Design Bench (Phase 17)

_Generated 2026-10-30 11:28 UTC by `apex-one reports build` from measured artifacts._

Fifteen page types (every semantic page type of the Document AST), content from a real pipeline run (golden job AST + fact locks). Each system produces one page per type; all pages are rendered by the same Chromium and measured by the same deterministic page QA. **No single score is reported by design.**

Systems: `native-baseline` (fixed editorial-column genes, no search), `native-tournament` (layout search, ULTRA-like budget), `llm:<model>` (a local model writes the page HTML itself under the APEX DOM contract; evaluation only).

## Per-system summary (mean / min over pages)

| system | pages | produced | critical pages | contract violations | median latency | hierarchy | typography | brand_fit | quality | contrast | critical_accuracy | alignment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm:gemma-multimodal | 5 | 5 | 2 | 0 | 143.8 s | 87.3 / 82.1 | 73.0 / 35.0 | 100.0 / 100.0 | 94.8 / 79.0 | 100.0 / 100.0 | 96.9 / 87.5 | 100.0 / 100.0 |
| llm:gpt-oss-20b | 5 | 1 | 5 | 4 | 617.3 s | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | — | 100.0 / 100.0 |
| llm:nemotron-nano-omni | 5 | 4 | 4 | 1 | 352.9 s | 94.7 / 88.9 | 92.5 / 85.0 | 95.0 / 90.0 | 97.5 / 95.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 |
| llm:qwen-vl-current | 5 | 5 | 5 | 0 | 97.1 s | 89.0 / 88.3 | 88.0 / 85.0 | 100.0 / 100.0 | 97.8 / 94.0 | 100.0 / 100.0 | 0.0 / 0.0 | 100.0 / 100.0 |
| native-baseline | 15 | 15 | 0 | 0 | 0.3 s | 100.0 / 100.0 | 98.3 / 85.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 92.7 / 50.0 |
| native-tournament | 15 | 15 | 0 | 0 | 1.8 s | 99.3 / 90.0 | 99.0 / 85.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 97.8 / 80.0 |

## Per page type

| page type | system | critical | hierarchy | typography | brand | alignment | whitespace (descriptive) | detail |
|---|---|---|---|---|---|---|---|---|
| ApexTake | llm:gemma-multimodal | False | 82 | 35 | 100 | 100 | 97 | 1842 chars; re-measured on neutral canvas |
| ApexTake | llm:gpt-oss-20b | True | 100 | 100 | 100 | 100 | 82 | 2558 chars |
| ApexTake | llm:nemotron-nano-omni | False | 100 | 100 | 100 | 100 | 80 | 1215 chars |
| ApexTake | llm:qwen-vl-current | True | 89 | 85 | 100 | 100 | 79 | 1173 chars; re-measured on neutral canvas; re-measured on neutral canvas |
| ApexTake | native-baseline | False | 100 | 100 | 100 | 100 | 84 | editorial-column defaults |
| ApexTake | native-tournament | False | 100 | 100 | 100 | 100 | 70 | checklist-sheet/light; evaluated 42 |
| ApplicationJourney | native-baseline | False | 100 | 90 | 100 | 100 | 79 | editorial-column defaults |
| ApplicationJourney | native-tournament | False | 100 | 100 | 100 | 100 | 64 | ledger/light; evaluated 42 |
| Breath | native-baseline | False | 100 | 100 | 100 | 50 | 93 | editorial-column defaults |
| Breath | native-tournament | False | 100 | 100 | 100 | 100 | 89 | quiet-breath/silver; evaluated 42 |
| Checklist | llm:gemma-multimodal | False | 89 | 85 | 100 | 100 | 83 | 1895 chars; re-measured on neutral canvas |
| Checklist | llm:gpt-oss-20b | True | — | — | — | — | — | EXECUTE; no <section> produced |
| Checklist | llm:nemotron-nano-omni | True | 90 | 85 | 90 | 100 | 80 | 1832 chars |
| Checklist | llm:qwen-vl-current | True | 89 | 85 | 100 | 100 | 80 | 1195 chars; re-measured on neutral canvas; re-measured on neutral canvas |
| Checklist | native-baseline | False | 100 | 100 | 100 | 100 | 84 | editorial-column defaults |
| Checklist | native-tournament | False | 100 | 100 | 100 | 100 | 68 | checklist-sheet/light; evaluated 42 |
| Closing | native-baseline | False | 100 | 100 | 100 | 100 | 85 | editorial-column defaults |
| Closing | native-tournament | False | 100 | 100 | 100 | 100 | 73 | manifesto/silver; evaluated 42 |
| Comparison | native-baseline | False | 100 | 100 | 100 | 100 | 90 | editorial-column defaults |
| Comparison | native-tournament | False | 100 | 100 | 100 | 100 | 83 | editorial-column/dark; evaluated 42 |
| Cover | llm:gemma-multimodal | True | 90 | 75 | 100 | 100 | 95 | 1653 chars; re-measured on neutral canvas |
| Cover | llm:gpt-oss-20b | True | — | — | — | — | — | EXECUTE; no <section> produced |
| Cover | llm:nemotron-nano-omni | True | 89 | 100 | 100 | 100 | 89 | 1603 chars |
| Cover | llm:qwen-vl-current | True | 89 | 100 | 100 | 100 | 89 | 753 chars; re-measured on neutral canvas; re-measured on neutral canvas |
| Cover | native-baseline | False | 100 | 100 | 100 | 80 | 76 | editorial-column defaults |
| Cover | native-tournament | False | 100 | 100 | 100 | 80 | 81 | cover-monument/dark; evaluated 42 |
| EligibilityChapter | native-baseline | False | 100 | 100 | 100 | 88 | 82 | editorial-column defaults |
| EligibilityChapter | native-tournament | False | 100 | 100 | 100 | 88 | 73 | editorial-column/light; evaluated 42 |
| FundingChapter | native-baseline | False | 100 | 100 | 100 | 90 | 81 | editorial-column defaults |
| FundingChapter | native-tournament | False | 100 | 100 | 100 | 100 | 66 | checklist-sheet/light; evaluated 42 |
| HeroFact | native-baseline | False | 100 | 100 | 100 | 100 | 94 | editorial-column defaults |
| HeroFact | native-tournament | False | 100 | 100 | 100 | 100 | 87 | manifesto/dark; evaluated 42 |
| Opening | native-baseline | False | 100 | 100 | 100 | 83 | 86 | editorial-column defaults |
| Opening | native-tournament | False | 100 | 100 | 100 | 100 | 79 | split-asymmetric/dark; evaluated 42 |
| OpportunitySnapshot | llm:gemma-multimodal | True | 87 | 85 | 100 | 100 | 79 | 3889 chars; re-measured on neutral canvas |
| OpportunitySnapshot | llm:gpt-oss-20b | True | — | — | — | — | — | EXECUTE; no <section> produced |
| OpportunitySnapshot | llm:nemotron-nano-omni | True | — | — | — | — | — | <section class="page" dir="rtl" lang="ar">
  <div class="page-body">
    <element data-blo |
| OpportunitySnapshot | llm:qwen-vl-current | True | 88 | 85 | 100 | 100 | 75 | 1621 chars; re-measured on neutral canvas; re-measured on neutral canvas |
| OpportunitySnapshot | native-baseline | False | 100 | 85 | 100 | 100 | 74 | editorial-column defaults |
| OpportunitySnapshot | native-tournament | False | 100 | 85 | 100 | 100 | 63 | ledger/light; evaluated 42 |
| ProfileStory | native-baseline | False | 100 | 100 | 100 | 100 | 92 | editorial-column defaults |
| ProfileStory | native-tournament | False | 100 | 100 | 100 | 100 | 85 | editorial-column/dark; evaluated 42 |
| Timeline | llm:gemma-multimodal | False | 88 | 85 | 100 | 100 | 86 | 1808 chars; re-measured on neutral canvas |
| Timeline | llm:gpt-oss-20b | True | — | — | — | — | — | EXECUTE; no <section> produced |
| Timeline | llm:nemotron-nano-omni | True | 100 | 85 | 90 | 100 | 82 | 1788 chars |
| Timeline | llm:qwen-vl-current | True | 88 | 85 | 100 | 100 | 86 | 998 chars; re-measured on neutral canvas; re-measured on neutral canvas |
| Timeline | native-baseline | False | 100 | 100 | 100 | 100 | 75 | editorial-column defaults |
| Timeline | native-tournament | False | 90 | 100 | 100 | 100 | 67 | timeline-rail/light; evaluated 42 |
| Warning | native-baseline | False | 100 | 100 | 100 | 100 | 85 | editorial-column defaults |
| Warning | native-tournament | False | 100 | 100 | 100 | 100 | 74 | manifesto/silver; evaluated 42 |

## Reading the results

* The deterministic metrics are a **correctness floor**, not a beauty ranking: both native systems saturate most of them, so they cannot tell a good page from a great one. Ranking among valid pages needs the calibrated Vision Council and human A/B/C preferences.
* `whitespace` is 100×(1 − ink coverage): descriptive, not a quality score. The tournament deliberately fills pages closer to each page's density target.
* LLM page writers are measured under the same contract; content they produce never ships (licence UNKNOWN → evaluation only).

## Model-written pages vs native (separate metrics)

Same content, same renderer, same checks. Means over the page types each system produced; `overflow` = issue count (lower is better); `repetition` = mean pairwise layout similarity between a system's own pages (lower = less repetitive).

| system | pages produced | text_fidelity | fact_preservation | html_validity | css_validity | rtl | overflow_issues | visual_hierarchy | editability | novelty_vs_native | apex_similarity | reader_comprehension | repetition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm:gemma-multimodal | 5/5 | 94.9 | 100.0 | 100.0 | 80.0 | 94.8 | 0.0 | 87.3 | 100.0 | 69.8 | 90.0 | 100.0 | 21.9 |
| llm:gpt-oss-20b | 1/5 | 100.0 | — | 100.0 | 100.0 | 100.0 | 4.0 | 100.0 | 100.0 | 13.3 | 100.0 | — | — |
| llm:nemotron-nano-omni | 4/5 | 98.8 | 100.0 | 100.0 | 100.0 | 97.5 | 0.2 | 94.7 | 100.0 | 67.2 | 90.0 | 100.0 | 67.9 |
| llm:qwen-vl-current | 5/5 | 93.0 | 100.0 | 100.0 | 100.0 | 97.8 | 1.0 | 89.0 | 100.0 | 71.2 | 100.0 | 100.0 | 73.3 |
| native-baseline | 15/15 | 97.9 | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | — | 100.0 | 97.9 | 51.5 |
| native-tournament | 15/15 | 97.9 | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 99.3 | 100.0 | 53.8 | 100.0 | 99.2 | 39.6 |

### Decision per model system (vs native-tournament, same page types)

* **llm:gemma-multimodal** — KEEP NATIVE (model page lost on safety metrics or never won). Wins: 1; safety losses (facts/RTL/text/overflow): 4; other losses: 8. Examples of safety losses: ['Checklist:text_fidelity 96.3 vs 100.0', 'Cover:text_fidelity 79.1 vs 100.0', 'OpportunitySnapshot:rtl 79.0 vs 100.0']
* **llm:gpt-oss-20b** — KEEP NATIVE (model page lost on safety metrics or never won). Wins: 0; safety losses (facts/RTL/text/overflow): 1; other losses: 4. Examples of safety losses: ['ApexTake:overflow_issues 4 vs 0']
* **llm:nemotron-nano-omni** — KEEP NATIVE (model page lost on safety metrics or never won). Wins: 1; safety losses (facts/RTL/text/overflow): 4; other losses: 5. Examples of safety losses: ['ApexTake:text_fidelity 95.0 vs 100.0', 'ApexTake:rtl 95.0 vs 100.0', 'Cover:overflow_issues 1 vs 0']
* **llm:qwen-vl-current** — KEEP NATIVE (model page lost on safety metrics or never won). Wins: 0; safety losses (facts/RTL/text/overflow): 9; other losses: 5. Examples of safety losses: ['ApexTake:overflow_issues 1 vs 0', 'Checklist:overflow_issues 1 vs 0', 'Cover:overflow_issues 1 vs 0']

## Targeted design risk cases

23/23 measured cases pass; 2 NOT_MEASURED.

| case | expectation | status | detail |
|---|---|---|---|
| arabic_rtl | pass:qa.rtl_direction | PASS | clean |
| arabic_english_mix | pass:qa.ltr_isolation | PASS | clean |
| arabic_dollar | pass:qa.currency | PASS | clean |
| arabic_percent | pass:qa.percent | PASS | clean |
| arabic_date | pass:qa.dom_fact_integrity | PASS | clean |
| very_long_arabic_title | pass:qa.overflow | PASS | clean |
| dense_funding_page | pass:qa.page_bounds | PASS | issues: qa.arabic_leading |
| deadline_visibility | pass:design.hierarchy>=80 | PASS | design.hierarchy=100.0 |
| brand_consistency | pass:brand.palette | PASS | clean |
| card_overuse | detect:vision.card_overuse | PASS | detected |
| gradient_forbidden | detect:brand.gradients | PASS | detected |
| mixed_direction_punctuation | detect:qa.mixed_runs | PASS | detected |
| unisolated_latin | detect:qa.ltr_isolation | PASS | detected |
| long_url | pass:qa.overflow | PASS | clean |
| beautiful_but_misleading | detect:qa.dom_fact_integrity | PASS | detected |
| boring_but_correct | pass:qa.dom_fact_integrity | PASS | clean |
| low_contrast_detect | detect:qa.contrast | PASS | detected |
| overflow_detect | detect:qa.overflow | PASS | detected |
| arabic_letter_spacing_detect | detect:qa.arabic_letter_spacing | PASS | detected |
| arabic_italic_detect | detect:qa.arabic_italic | PASS | detected |
| arabic_tight_leading_detect | detect:qa.arabic_leading | PASS | detected |
| arabic_typography_clean | pass:qa.arabic_letter_spacing | PASS | clean |
| print_fidelity | pass:print | PASS | print.fidelity=100.0 |
| screenshot_to_code_regression | not_measured:requires ScreenCoder/DCGen (not available on a  | NOT_MEASURED | requires ScreenCoder/DCGen (not available on a $0 licence-verified route) |
| graphic_design_bench_gdb | not_measured:GDB runs separately (apex-one bench gdb): lica- | NOT_MEASURED | GDB runs separately (apex-one bench gdb): lica-gdb is installed, but the full da |
