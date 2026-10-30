# Vision judge robustness

_Generated 2026-10-30 12:26 UTC by `apex-one reports build` from measured artifacts._

Does a pairwise judge's calibration survive a change of input resolution? Same five calibration cases (good page vs each deliberately broken variant), both orders, 3 repeats per width.

## Judge-input contract (canonical normalized input)

* **canonical judge width: 640 px** — `PairwiseJudge` default (`CALIBRATED_MAX_W`); production finalist judging and calibration call the SAME `PairwiseJudge.compare` → `encode_png` → `normalize_for_judge` path
* preprocessing `width-bound-thumbnail-bicubic-v1`: width-bound (every candidate scaled to the same width, so two pages of different heights share one scale), aspect ratio preserved, never capped by height, Pillow default bicubic resampling; each input's sha256 is stored with every result
* native render: 794 px wide (A4 at device scale 1). Widths above native are RE-RENDERED at device scale width/native — never upscaled
* smallest text on the calibration page: 9 CSS px → effective 320 px: 3.6 px, 480 px: 5.4 px, 640 px: 7.3 px, 768 px: 8.7 px (legibility is measured directly by the probe below, not assumed)
* confidence = consistency across the 2 × repeats answers per case, |2p − 1| (the judge is not asked to self-report confidence, so the calibrated prompt is unchanged)
* judging runs at temperature 0 (as in production), so repeats measure DETERMINISM of the serving stack, not sampling variance: identical repeats (variance 0, confidence 1.0) mean the verdict is reproducible, not that it is right — accuracy and the per-case results carry that
* correction: the earlier investigation experiment labelled “E2 1024 px” actually ran at the native 794 px — `thumbnail()` never upscales. The sweep below renders a real 1024 px input.

Pre-registered rules (`apex_one/lab/benchmarks/vision_robustness.py`, fixed before results): reliable at a width = every repeat all-valid and ≥ 4/5; legible = both probe facts read exactly; ROBUSTLY_CALIBRATED = reliable at every legible width and legible at canonical, native and 1024; CANONICAL_640_ONLY = reliable and legible at 640 only; UNQUALIFIED = not reliable or not legible at 640.

## qwen3-vl-8b — **CANONICAL_640_ONLY**

not yet measured: 320, 480, 768, native, 1024. Model digest `sha256:e3d1a6e87c5c…`.

| width | input | repeats | correct per repeat | accuracy | order sensitivity | run variance | cases flipping | always wrong | confidence | median call latency | legible (deadline / tuition) | reliable | input hash (good) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 320 | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |
| 480 | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |
| 640 (640 px) | calibration render, downscaled by the judge-input contract | 3 | [4, 4, 4] | 0.80 | 0.00 (0 case-runs) | 0 | — | cramped | 1.00 | 62.8 s | yes (True / True) | yes | `c694ad322e2c` |
| 768 | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |
| native | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |
| 1024 | — | 0 | NOT_MEASURED yet | — | — | — | — | — | — | — | — | — | — |

Raw answers, per-call latency and every input hash: `docs/evidence/vision_robustness_qwen3-vl-8b.json`.

**Limitation (stays visible):** qwen3-vl-8b is calibrated ONLY for the canonical 640 px normalized input. It is not a general-purpose vision judge; at other resolutions its verdicts are not trusted. Production uses it only for order-swapped finalist A/B judging at 640 px, and the deterministic DOM gates stay authoritative.

