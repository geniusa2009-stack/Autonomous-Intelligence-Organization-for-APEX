# Vision Calibration Analysis

_Generated 2026-10-13 11:35 UTC by `apex-one reports build` from measured artifacts._

**Question.** Qwen3-VL 4B scored 100 on the council's visual-hierarchy benchmark but passed only 1/5 absolute calibration cases. Which is right, and why do they disagree?

**Rule kept throughout:** a vision model enters a quality gate only if it passes calibration (≥ 4/5, every case valid). No bar was lowered; absolute (six-role scoring) and pairwise (A/B) are separate qualifications measured on the same five cases.

## The benchmark result being questioned

* gemma-multimodal: score 50.0 — order-swapped answers correct=[True, False] (one pair: good vs no_hierarchy)
* qwen-vl-current: score 100.0 — order-swapped answers correct=[True, True] (one pair: good vs no_hierarchy)

## qwen-vl-current

**E0 absolute (production protocol):** 1/5 passed; ties on targeted role: 4; inversions: 0; distinct scores used across all pages/roles: [40.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0]

| case | role | good | broken | pass |
|---|---|---|---|---|
| low_contrast | TypographyJudge | 95 | 95 | False |
| card_overuse | AIClicheJudge | 100 | 100 | False |
| gradient | APEXBrandJudge | 90 | 55 | True |
| cramped | EditorialDesignJudge | 80 | 80 | False |
| no_hierarchy | VisualHierarchyJudge | 85 | 85 | False |

Parser/execution errors: none

**E1 pairwise 640 px:** 0/5 order-consistent wins; position-biased cases: 5

| case | good shown as A → pick | good shown as B → pick | pass |
|---|---|---|---|
| low_contrast | first | second | False |
| card_overuse | first | second | False |
| gradient | first | second | False |
| cramped | first | second | False |
| no_hierarchy | first | second | False |

## Hypotheses checked

| hypothesis | evidence used |
|---|---|
| different prompting / role-rubric overload | E0 (six roles, one call) vs E3 (only the targeted role) |
| pair order sensitivity / position bias | E1 good-as-A vs good-as-B answers |
| scoring schema (absolute scores tie) | E0 ties_on_target, distinct_scores |
| image scaling | E1 (640 px) vs E2 (1024 px) |
| model instability | E3 vs E4 (identical prompts, temperature 0) |
| output parser | E0 reviews: parse errors / dropped roles vs raw text |
| context truncation | E0 raw text ends mid-JSON / missing roles |
| single easy pair vs five cases | benchmark pair = good vs no_hierarchy only |

## Qualification status

* absolute — gemma-multimodal: 0/5 → **NOT QUALIFIED**
* absolute — qwen-vl-current: 1/5 → **NOT QUALIFIED**
* pairwise — qwen-vl-current: 0/5 → **NOT QUALIFIED**
