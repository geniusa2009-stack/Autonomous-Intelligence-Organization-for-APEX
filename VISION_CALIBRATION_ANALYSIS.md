# Vision Calibration Analysis

_Generated 2026-10-26 08:43 UTC by `apex-one reports build` from measured artifacts._

**Question.** Qwen3-VL 4B scored 100 on the council's visual-hierarchy benchmark but passed only 1/5 absolute calibration cases. Which is right, and why do they disagree?

**Rule kept throughout:** a vision model enters a quality gate only if it passes calibration (≥ 4/5, every case valid). No bar was lowered; absolute (six-role scoring) and pairwise (A/B) are separate qualifications measured on the same five cases.

## The benchmark result being questioned

* gemma-multimodal: score 50.0 — order-swapped answers correct=[True, False] (one pair: good vs no_hierarchy)
* qwen-vl-current: score 100.0 — order-swapped answers correct=[True, True] (one pair: good vs no_hierarchy)

## gemma-multimodal

**E0 absolute (production protocol):** 1/5 passed; ties on targeted role: 1; inversions: 3; distinct scores used across all pages/roles: [60.0, 65.0, 70.0, 75.0, 78.0, 80.0, 85.0, 88.0, 90.0, 92.0, 95.0]

| case | role | good | broken | pass |
|---|---|---|---|---|
| low_contrast | TypographyJudge | 85 | 92 | False |
| card_overuse | AIClicheJudge | 95 | 70 | True |
| gradient | APEXBrandJudge | 90 | 95 | False |
| cramped | EditorialDesignJudge | 65 | 78 | False |
| no_hierarchy | VisualHierarchyJudge | 75 | 75 | False |

Parser/execution errors: none

**E1 pairwise 640 px:** 0/5 order-consistent wins; position-biased cases: 5

| case | good shown as A → pick | good shown as B → pick | pass |
|---|---|---|---|
| low_contrast | first | second | False |
| card_overuse | first | second | False |
| gradient | first | second | False |
| cramped | first | second | False |
| no_hierarchy | first | second | False |

**E2 pairwise 1024 px:** 0/5 order-consistent wins; position-biased cases: 5

| case | good shown as A → pick | good shown as B → pick | pass |
|---|---|---|---|
| low_contrast | first | second | False |
| card_overuse | first | second | False |
| gradient | first | second | False |
| cramped | first | second | False |
| no_hierarchy | first | second | False |

**E3 single-role absolute:** 1/5 passed

| case | role | good | broken | pass |
|---|---|---|---|---|
| low_contrast | TypographyJudge | 85 | 85 | False |
| card_overuse | AIClicheJudge | 85 | 90 | False |
| gradient | APEXBrandJudge | 85 | 85 | False |
| cramped | EditorialDesignJudge | 65 | 65 | False |
| no_hierarchy | VisualHierarchyJudge | 85 | 75 | True |

**E4 single-role repeat:** 1/5 passed

| case | role | good | broken | pass |
|---|---|---|---|---|
| low_contrast | TypographyJudge | 85 | 85 | False |
| card_overuse | AIClicheJudge | 85 | 90 | False |
| gradient | APEXBrandJudge | 85 | 85 | False |
| cramped | EditorialDesignJudge | 65 | 65 | False |
| no_hierarchy | VisualHierarchyJudge | 85 | 75 | True |

Stability: 5/5 cases gave identical scores on repeat.

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

**E2 pairwise 1024 px:** 2/5 order-consistent wins; position-biased cases: 3

| case | good shown as A → pick | good shown as B → pick | pass |
|---|---|---|---|
| low_contrast | first | second | False |
| card_overuse | first | second | False |
| gradient | first | first | True |
| cramped | first | second | False |
| no_hierarchy | first | first | True |

**E3 single-role absolute:** 3/5 passed

| case | role | good | broken | pass |
|---|---|---|---|---|
| low_contrast | TypographyJudge | 95 | 95 | False |
| card_overuse | AIClicheJudge | 95 | 85 | True |
| gradient | APEXBrandJudge | 95 | 10 | True |
| cramped | EditorialDesignJudge | 85 | 75 | True |
| no_hierarchy | VisualHierarchyJudge | 95 | 95 | False |

**E4 single-role repeat:** 3/5 passed

| case | role | good | broken | pass |
|---|---|---|---|---|
| low_contrast | TypographyJudge | 95 | 95 | False |
| card_overuse | AIClicheJudge | 95 | 85 | True |
| gradient | APEXBrandJudge | 95 | 10 | True |
| cramped | EditorialDesignJudge | 85 | 75 | True |
| no_hierarchy | VisualHierarchyJudge | 95 | 95 | False |

Stability: 5/5 cases gave identical scores on repeat.

## Hypotheses — verdicts derived from the experiments

| model | hypothesis | evidence | verdict |
|---|---|---|---|
| gemma-multimodal | scoring schema: absolute scores tie | ties on targeted role 1/5, inversions 3/5 | **not the main cause** |
| gemma-multimodal | model ranks broken pages HIGHER | inversions 3/5 | **CONFIRMED** |
| gemma-multimodal | output parser / truncation | 0 review(s) with parse/execution errors | **RULED OUT** |
| gemma-multimodal | rubric overload (six roles in one call) | six-role 1/5 vs single-role 1/5 | **RULED OUT** |
| gemma-multimodal | pair-order sensitivity / position bias | 5/5 cases picked the same POSITION in both orders | **CONFIRMED** |
| gemma-multimodal | image scaling | pairwise 640 px 0/5 vs 1024 px 0/5 | **RULED OUT** |
| gemma-multimodal | model instability (temperature 0) | 5/5 cases identical on repeat | **RULED OUT** |
| gemma-multimodal | prompt leakage | rubric text never contains the case name or the expected answer | **RULED OUT by construction** |
| gemma-multimodal | qualifies as a judge in ANY tested mode (>= 4/5) | best mode 1/5 | **NO — stays out of every gate** |
| qwen-vl-current | scoring schema: absolute scores tie | ties on targeted role 4/5, inversions 0/5 | **CONFIRMED** |
| qwen-vl-current | model ranks broken pages HIGHER | inversions 0/5 | **no** |
| qwen-vl-current | output parser / truncation | 0 review(s) with parse/execution errors | **RULED OUT** |
| qwen-vl-current | rubric overload (six roles in one call) | six-role 1/5 vs single-role 3/5 | **CONFIRMED (partial)** |
| qwen-vl-current | pair-order sensitivity / position bias | 5/5 cases picked the same POSITION in both orders | **CONFIRMED** |
| qwen-vl-current | image scaling | pairwise 640 px 0/5 vs 1024 px 2/5 | **CONFIRMED (helps)** |
| qwen-vl-current | model instability (temperature 0) | 5/5 cases identical on repeat | **RULED OUT** |
| qwen-vl-current | prompt leakage | rubric text never contains the case name or the expected answer | **RULED OUT by construction** |
| qwen-vl-current | qualifies as a judge in ANY tested mode (>= 4/5) | best mode 3/5 | **NO — stays out of every gate** |

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

* absolute — gemma-multimodal: 1/5 → **NOT QUALIFIED**
* absolute — qwen-vl-current: 1/5 → **NOT QUALIFIED**
* pairwise — qwen-vl-current: 0/5 → **NOT QUALIFIED**
* pairwise — gemma-multimodal: 0/5 → **NOT QUALIFIED**
