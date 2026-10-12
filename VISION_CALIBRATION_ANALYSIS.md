# Vision Calibration Analysis

_Generated 2026-10-12 12:08 UTC by `apex-one reports build` from measured artifacts._

**Question.** Qwen3-VL 4B scored 100 on the council's visual-hierarchy benchmark but passed only 1/5 absolute calibration cases. Which is right, and why do they disagree?

**Rule kept throughout:** a vision model enters a quality gate only if it passes calibration (≥ 4/5, every case valid). No bar was lowered; absolute (six-role scoring) and pairwise (A/B) are separate qualifications measured on the same five cases.

## The benchmark result being questioned

* gemma-multimodal: score 50.0 — order-swapped answers correct=[True, False] (one pair: good vs no_hierarchy)
* qwen-vl-current: score 100.0 — order-swapped answers correct=[True, True] (one pair: good vs no_hierarchy)

PENDING: investigation experiments have not run yet (scripts/validation_queue.py steps calib/pcalib/invest).
