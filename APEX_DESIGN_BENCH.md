# APEX Design Bench (Phase 17)

_Generated 2026-10-10 17:46 UTC by `apex-one reports build` from measured artifacts._

Fifteen page types (every semantic page type of the Document AST), content from a real pipeline run (golden job AST + fact locks). Each system produces one page per type; all pages are rendered by the same Chromium and measured by the same deterministic page QA. **No single score is reported by design.**

Systems: `native-baseline` (fixed editorial-column genes, no search), `native-tournament` (layout search, ULTRA-like budget), `llm:<model>` (a local model writes the page HTML itself under the APEX DOM contract; evaluation only).

## Per-system summary (mean / min over pages)

| system | pages | produced | critical pages | contract violations | median latency | hierarchy | typography | brand_fit | quality | contrast | critical_accuracy | alignment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| native-baseline | 15 | 15 | 0 | 0 | 0.3 s | 100.0 / 100.0 | 98.3 / 85.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 92.7 / 50.0 |
| native-tournament | 15 | 15 | 0 | 0 | 1.7 s | 99.3 / 90.0 | 99.0 / 85.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 97.8 / 80.0 |

## Per page type

| page type | system | critical | hierarchy | typography | brand | alignment | whitespace (descriptive) | detail |
|---|---|---|---|---|---|---|---|---|
| ApexTake | native-baseline | False | 100 | 100 | 100 | 100 | 84 | editorial-column defaults |
| ApexTake | native-tournament | False | 100 | 100 | 100 | 100 | 70 | checklist-sheet/light; evaluated 42 |
| ApplicationJourney | native-baseline | False | 100 | 90 | 100 | 100 | 79 | editorial-column defaults |
| ApplicationJourney | native-tournament | False | 100 | 100 | 100 | 100 | 64 | ledger/light; evaluated 42 |
| Breath | native-baseline | False | 100 | 100 | 100 | 50 | 93 | editorial-column defaults |
| Breath | native-tournament | False | 100 | 100 | 100 | 100 | 89 | quiet-breath/silver; evaluated 42 |
| Checklist | native-baseline | False | 100 | 100 | 100 | 100 | 84 | editorial-column defaults |
| Checklist | native-tournament | False | 100 | 100 | 100 | 100 | 68 | checklist-sheet/light; evaluated 42 |
| Closing | native-baseline | False | 100 | 100 | 100 | 100 | 85 | editorial-column defaults |
| Closing | native-tournament | False | 100 | 100 | 100 | 100 | 73 | manifesto/silver; evaluated 42 |
| Comparison | native-baseline | False | 100 | 100 | 100 | 100 | 90 | editorial-column defaults |
| Comparison | native-tournament | False | 100 | 100 | 100 | 100 | 81 | checklist-sheet/dark; evaluated 42 |
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
| OpportunitySnapshot | native-baseline | False | 100 | 85 | 100 | 100 | 74 | editorial-column defaults |
| OpportunitySnapshot | native-tournament | False | 100 | 85 | 100 | 100 | 63 | ledger/light; evaluated 42 |
| ProfileStory | native-baseline | False | 100 | 100 | 100 | 100 | 92 | editorial-column defaults |
| ProfileStory | native-tournament | False | 100 | 100 | 100 | 100 | 85 | editorial-column/light; evaluated 52 |
| Timeline | native-baseline | False | 100 | 100 | 100 | 100 | 75 | editorial-column defaults |
| Timeline | native-tournament | False | 90 | 100 | 100 | 100 | 67 | timeline-rail/light; evaluated 42 |
| Warning | native-baseline | False | 100 | 100 | 100 | 100 | 85 | editorial-column defaults |
| Warning | native-tournament | False | 100 | 100 | 100 | 100 | 74 | manifesto/silver; evaluated 42 |

## Reading the results

* The deterministic metrics are a **correctness floor**, not a beauty ranking: both native systems saturate most of them, so they cannot tell a good page from a great one. Ranking among valid pages needs the calibrated Vision Council and human A/B/C preferences.
* `whitespace` is 100×(1 − ink coverage): descriptive, not a quality score. The tournament deliberately fills pages closer to each page's density target.
* LLM page writers are measured under the same contract; content they produce never ships (licence UNKNOWN → evaluation only).

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
