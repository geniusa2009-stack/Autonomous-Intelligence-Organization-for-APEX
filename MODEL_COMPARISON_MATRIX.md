# Model Comparison Matrix

_Generated 2026-10-30 21:39 UTC by `apex-one reports build` from measured artifacts._

One row per (model, task). **No overall ranking**: models were measured on different task sets (text-only models cannot run the vision task; some outputs were empty because the token budget ran out inside hidden reasoning), so averages across tasks are not comparable. Winners are declared per task, only among models measured on that same task.

Hardware for every row: 4 vCPU x86-64, 16.5 GB RAM, no GPU, llama.cpp CPU. Checker version: 2.

| model | task | measured? | score | latency | output complete? | checker | token budget | notes |
|---|---|---|---|---|---|---|---|---|
| gemma-multimodal | structured_json | yes | 100 | 11.1 s | yes | v1 | 500 (task default) | 4/4 fields exact |
| gemma-multimodal | fact_preservation | yes | 50 | 6.7 s | yes | v1 | 500 (task default) | dates=[] money=[('USD', 50.0)] |
| gemma-multimodal | egyptian_arabic | yes | 75 | 3.5 s | yes | v1 | 500 (task default) | dialect_markers=0 msa=0 number_kept=True |
| gemma-multimodal | html_css | yes | 100 | 15.0 s | yes | v1 | 700 (task default) | {"rtl": true, "h2": true, "p": true, "no_script": true, "no_gradient": true, "bdi_or_ltr": |
| gemma-multimodal | long_context | yes | 100 | 61.0 s | yes | v1 | 300 (task default) | got 2027-01-20 |
| gemma-multimodal | design_criticism | yes | 100 | 78.7 s | truncated in log | v1 | 600 (task default) | {"hierarchy": true, "contrast": true, "line_length": true, "cards": true} |
| gemma-multimodal | visual_hierarchy | yes | 50 | 106.4 s | n/a (vision A/B) | v1 | 60 (A/B) | order-swapped answers correct=[True, False] |
| gemma-multimodal | reasoning | yes | 0 | 3.9 s | yes | v1 | 900 (task default) | expected 2026-10-17, got 2026-10-26 |
| gpt-oss-20b | structured_json | yes | 100 | 35.5 s | yes | v1 | 500 (task default) | 4/4 fields exact |
| gpt-oss-20b | fact_preservation | yes | 100 | 95.2 s | yes | v2 | 4096 | dates=['2026-11-01'] money=[('USD', 50.0)] |
| gpt-oss-20b | egyptian_arabic | yes | 50 | 28.8 s | yes | v1 | 500 (task default) | dialect_markers=1 msa=0 number_kept=True |
| gpt-oss-20b | html_css | yes | 100 | 36.0 s | yes | v1 | 700 (task default) | {"rtl": true, "h2": true, "p": true, "no_script": true, "no_gradient": true, "bdi_or_ltr": |
| gpt-oss-20b | long_context | yes | 100 | 205.4 s | yes | v1 | 300 (task default) | got 2027-01-20 |
| gpt-oss-20b | design_criticism | yes | 100 | 76.6 s | truncated in log | v1 | 600 (task default) | {"hierarchy": true, "contrast": true, "line_length": true, "cards": true} |
| gpt-oss-20b | visual_hierarchy | no | — | — | — | — | — | text-only model: vision task not applicable |
| gpt-oss-20b | reasoning | yes | 100 | 162.4 s | yes | v2 | 4096 | expected 2026-10-17, got 2026-10-17 |
| nemotron-nano-omni | structured_json | yes | 100 | 39.1 s | yes | v1 | 500 (task default) | 4/4 fields exact |
| nemotron-nano-omni | fact_preservation | yes | 100 | 20.9 s | yes | v1 | 500 (task default) | dates=['2026-11-01'] money=[('USD', 50.0)] |
| nemotron-nano-omni | egyptian_arabic | yes | 0 | 29.5 s | yes | v1 | 500 (task default) | dialect_markers=0 msa=0 number_kept=True |
| nemotron-nano-omni | html_css | yes | 100 | 37.1 s | yes | v1 | 700 (task default) | {"rtl": true, "h2": true, "p": true, "no_script": true, "no_gradient": true, "bdi_or_ltr": |
| nemotron-nano-omni | long_context | yes | 100 | 140.7 s | yes | v1 | 300 (task default) | got 2027-01-20 |
| nemotron-nano-omni | design_criticism | yes | 100 | 84.5 s | yes | v1 | 600 (task default) | {"hierarchy": true, "contrast": true, "line_length": true, "cards": true} |
| nemotron-nano-omni | visual_hierarchy | no | — | — | — | — | — | text-only model: vision task not applicable |
| nemotron-nano-omni | reasoning | yes | 0 | 146.1 s | yes | v2 | 4096 | expected 2026-10-17, got 2026-10-21 |
| qwen-vl-current | structured_json | yes | 100 | 8.9 s | yes | v1 | 500 (task default) | 4/4 fields exact |
| qwen-vl-current | fact_preservation | yes | 100 | 5.0 s | yes | v1 | 500 (task default) | dates=['2026-11-01'] money=[('USD', 50.0)] |
| qwen-vl-current | egyptian_arabic | yes | 0 | 3.8 s | yes | v1 | 500 (task default) | dialect_markers=0 msa=0 number_kept=True |
| qwen-vl-current | html_css | yes | 100 | 10.7 s | yes | v1 | 700 (task default) | {"rtl": true, "h2": true, "p": true, "no_script": true, "no_gradient": true, "bdi_or_ltr": |
| qwen-vl-current | long_context | yes | 100 | 90.8 s | yes | v1 | 300 (task default) | got 2027-01-20 |
| qwen-vl-current | design_criticism | yes | 100 | 80.3 s | truncated in log | v1 | 600 (task default) | {"hierarchy": true, "contrast": true, "line_length": true, "cards": true} |
| qwen-vl-current | visual_hierarchy | yes | 100 | 63.6 s | n/a (vision A/B) | v1 | 60 (A/B) | order-swapped answers correct=[True, True] |
| qwen-vl-current | reasoning | yes | 0 | 3.8 s | yes | v1 | 900 (task default) | expected 2026-10-17, got 2026-10-02 |
| qwen3-vl-8b | structured_json | yes | 100 | 19.8 s | yes | v2 | 500 | 4/4 fields exact |
| qwen3-vl-8b | fact_preservation | yes | 100 | 12.4 s | yes | v2 | 500 | dates=['2026-11-01'] money=[('USD', 50.0)] |
| qwen3-vl-8b | egyptian_arabic | yes | 0 | 8.6 s | yes | v2 | 500 | dialect_markers=0 msa=0 number_kept=True |
| qwen3-vl-8b | html_css | yes | 100 | 20.3 s | yes | v2 | 700 | {"rtl": true, "h2": true, "p": true, "no_script": true, "no_gradient": true, "bdi_or_ltr": |
| qwen3-vl-8b | long_context | yes | 100 | 271.4 s | yes | v2 | 300 | got 2027-01-20 |
| qwen3-vl-8b | design_criticism | yes | 100 | 164.9 s | truncated in log | v2 | 600 | {"hierarchy": true, "contrast": true, "line_length": true, "cards": true} |
| qwen3-vl-8b | visual_hierarchy | yes | 100 | 157.5 s | n/a (vision A/B) | v2 | 60 (A/B) | order-swapped answers correct=[True, True] |
| qwen3-vl-8b | reasoning | yes | 0 | 8.1 s | yes | v2 | 900 | expected 2026-10-17, got 2026-10-18 |

## Task-specific winners (same task, measured models only)

| task | winner(s) | score | measured models | not measured |
|---|---|---|---|---|
| best structured output | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b | 100 | 5 | — |
| best fact preservation | gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b | 100 | 5 | — |
| best Egyptian Arabic | gemma-multimodal | 75 | 5 | — |
| best HTML/CSS | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b | 100 | 5 | — |
| best long-context retrieval | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b | 100 | 5 | — |
| best design criticism | gemma-multimodal, gpt-oss-20b, nemotron-nano-omni, qwen-vl-current, qwen3-vl-8b | 100 | 5 | — |
| best vision hierarchy (pairwise, single pair) | qwen-vl-current, qwen3-vl-8b — NOT a judge qualification; see calibration below | 100 | 3 | gpt-oss-20b, nemotron-nano-omni |
| best date reasoning | gpt-oss-20b — production date arithmetic is deterministic (apex_one/core/dates.py) regardless | 100 | 5 | — |

## Vision judge qualification (calibration, not benchmark)

* absolute six-role council — **gemma-multimodal**: 1/5 cases passed (valid 5); qualified: **False**
* absolute six-role council — **qwen-vl-current**: 1/5 cases passed (valid 5); qualified: **False**
* absolute six-role council — **qwen3-vl-8b**: 3/5 cases passed (valid 5); qualified: **False**
* pairwise A/B (both orders) — **qwen-vl-current**: 0/5 cases passed (valid 5); qualified: **False**
* pairwise A/B (both orders) — **gemma-multimodal**: 0/5 cases passed (valid 5); qualified: **False**
* pairwise A/B (both orders) — **qwen3-vl-8b**: 4/5 cases passed (valid 5); qualified: **True**

A model enters a quality gate only by passing calibration (≥ 4/5, all cases valid). Benchmark wins never qualify a judge.
