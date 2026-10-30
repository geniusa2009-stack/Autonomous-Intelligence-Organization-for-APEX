# Vision judge robustness

_Generated 2026-10-30 11:58 UTC by `apex-one reports build` from measured artifacts._

Does a pairwise judge's calibration survive a change of input resolution? Same five calibration cases (good page vs each deliberately broken variant), both orders, 3 repeats per width.

## Judge-input contract (canonical normalized input)

* **canonical judge width: 640 px** — `PairwiseJudge` default (`CALIBRATED_MAX_W`); production finalist judging and calibration call the SAME `PairwiseJudge.compare` → `encode_png` → `normalize_for_judge` path
* preprocessing `width-bound-thumbnail-bicubic-v1`: width-bound (every candidate scaled to the same width, so two pages of different heights share one scale), aspect ratio preserved, never capped by height, Pillow default bicubic resampling; each input's sha256 is stored with every result
* native render: 794 px wide (A4 at device scale 1). Widths above native are RE-RENDERED at device scale width/native — never upscaled
* smallest text on the calibration page: 9 CSS px → effective 320 px: 3.6 px, 480 px: 5.4 px, 640 px: 7.3 px, 768 px: 8.7 px (legibility is measured directly by the probe below, not assumed)
* confidence = consistency across the 2 × repeats answers per case, |2p − 1| (the judge is not asked to self-report confidence, so the calibrated prompt is unchanged)
* correction: the earlier investigation experiment labelled “E2 1024 px” actually ran at the native 794 px — `thumbnail()` never upscales. The sweep below renders a real 1024 px input.

Pre-registered rules (`apex_one/lab/benchmarks/vision_robustness.py`, fixed before results): reliable at a width = every repeat all-valid and ≥ 4/5; legible = both probe facts read exactly; ROBUSTLY_CALIBRATED = reliable at every legible width and legible at canonical, native and 1024; CANONICAL_640_ONLY = reliable and legible at 640 only; UNQUALIFIED = not reliable or not legible at 640.

_No robustness results yet._

