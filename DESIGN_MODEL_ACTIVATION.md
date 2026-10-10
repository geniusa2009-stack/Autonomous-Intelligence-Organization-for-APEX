# Design Model Activation (Phases 16, 19, 26)

_Generated 2026-10-10 16:42 UTC by `apex-one reports build` from measured artifacts._

Every design system named in the APEX spec, with the evidence actually gathered here. Statuses: ACTIVATED, PROTOCOL_REIMPLEMENTED, PACKAGE_INSTALLABLE, WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED, ARCHITECTURE_REFERENCE, NOT_RELEASED_OR_UNFOUND, LICENSE_BLOCKED, RESEARCH_ONLY. Nothing is marked ACTIVATED without a stored smoke-test artifact.

Environment facts behind most rows: huggingface.co / GitHub releases / arXiv are denied by the egress policy (weights unreachable); 4 vCPU + 15.7 GB RAM + no GPU (7B+ VLMs blocked without GGUF builds).

| system | source (evidence) | reported licence | checkpoint host | hardware | local | $0 remote | adapter | smoke test / artifacts | status |
|---|---|---|---|---|---|---|---|---|---|
| OmniDocLayout-LLM | paper: arXiv 2510.26213 (CVPR 2026); code: github.com/opendatalab/OmniDocLayout (per CVPR  (secondary) | not found | huggingface (release announced in paper) | 0.5B — CPU-runnable here if weights were reachable | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE** |
| ↳ APEX use | page_architecture specialist; native apex-native-layout performs the role meanwhile | | | | | | | | |
| PosterCopilot-7B | model_card: huggingface.co/void-2024/PosterCopilot (qwen2_5_vl, eccv2026 tags) (secondary) | not found on card snippet | huggingface | 7B VLM fp16 ~16 GB: HARDWARE_BLOCKED on CPU without a GGUF c | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| SEGA-7B | paper: arXiv 2510.15749 (SEGA: stepwise evolution, content-aware layout) (secondary) | not found | unknown | 7B: HARDWARE_BLOCKED on CPU | no | no | registry entry (UNAVAILABLE) | — | **NOT_RELEASED_OR_UNFOUND, ARCHITECTURE_REFERENCE** |
| ↳ APEX use | stepwise coarse->fine refinement idea mirrored by the tournament's targeted mutation | | | | | | | | |
| SEGA-13B | paper: arXiv 2510.15749 (secondary) | not found | unknown | 13B: HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | **NOT_RELEASED_OR_UNFOUND, HARDWARE_BLOCKED** |
| WebGenAgent-LM-7B | paper: arXiv 2509.22644 (WebGen-Agent); model_card: huggingface.co/luzimu/WebGenAgent-LM-7 (secondary) | MIT (SFT card) | huggingface | 7B fp16: HARDWARE_BLOCKED on CPU without GGUF | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| WebGenAgent-LM-8B | paper: arXiv 2509.22644 (secondary) | MIT expected (family); not confirmed | huggingface | HARDWARE_BLOCKED on CPU without GGUF | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| WebGenAgent-Step-GRPO | paper: arXiv 2509.22644 (Step-GRPO with screenshot + GUI-agent feedback) (secondary) | not confirmed for Step-GRPO checkpoint | huggingface | HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, ARCHITECTURE_REFERENCE** |
| ↳ APEX use | screenshot-feedback loop is exactly APEX's render->QA->mutate loop (implemented natively) | | | | | | | | |
| ScreenCoder | repo_found: unofficial mirror github.com/syntax-syndicate/ScreenCoder-agent (secondary) | not found | github | depends on chosen VLM | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, ARCHITECTURE_REFERENCE** |
| ↳ APEX use | screenshot->structure extraction is done by apex-native-decomposer on DOM; VLM path via local Qwen3-VL possible | | | | | | | | |
| DCGen | paper: arXiv 2406.16386 (FSE 2025) (secondary) | code licence not found | n/a | runs on any VLM | no | no | registry entry (UNAVAILABLE) | — | **PROTOCOL_REIMPLEMENTABLE, ARCHITECTURE_REFERENCE** |
| MarkupDM | model_card: huggingface.co/cyberagent/markupdm; paper: arXiv 2409.19051 (secondary) | Apache-2.0 (repo) — base model StarCoderBase carries BigCode OpenRAIL-M terms; training data crello | huggingface | 7B fp16: HARDWARE_BLOCKED on CPU without GGUF | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| PosterReward | paper: arXiv 2603.29855 (CVPR 2026); variants pairwise / lite / full, all Qwen3-VL-8B base (secondary) | not found | huggingface (assumed) | 8B VLM: CPU GGUF Q4 would be ~5 GB and slow (minutes per pai | no | no | apex_one/vision/pairwise.py (protocol) | pairwise unit tests; live judges: NONE yet (no calibrated-reliable vision judge) — the protocol does not run in jobs | **WEIGHTS_UNREACHABLE, PROTOCOL_REIMPLEMENTED** |
| ↳ APEX use | PosterReward-style PAIRWISE protocol (order-swapped twice, consistency required) runs on local vision judges ONLY when calibration marks them reliable — clearly labelled as protocol, not PosterReward weights | | | | | | | | |
| LayerD | paper: ICCV 2025 (CyberAgent, Tohoku); code: github.com/CyberAgentAILab/LayerD (secondary) | not found | github/huggingface | CPU feasible (slow) | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE** |
| OmniSVG-4B | model_card: huggingface.co/OmniSVG/OmniSVG1.1_4B (7.6 GB) (secondary) | Apache-2.0 (code/model); MMSVG dataset CC non-commercial | huggingface | 4B fp16 7.6 GB: CPU-feasible but slow | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE** |
| OmniSVG-8B | model_card: OmniSVG org on huggingface (secondary) | Apache-2.0 (code/model); dataset non-commercial | huggingface | HARDWARE_BLOCKED (fp16 ~16 GB) | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| StarVector-1B | model_card: starvector/starvector-1b-im2svg (secondary) | Apache-2.0 (secondary source only) | huggingface | CPU-feasible | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE** |
| StarVector-8B | model_card: starvector/starvector-8b-im2svg (secondary) | Apache-2.0 (secondary source only) | huggingface | HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| PosterOmni |  (none) | not found | unknown | — | no | no | registry entry (UNAVAILABLE) | — | **NOT_RELEASED_OR_UNFOUND** |
| PosterCraft | model_card: huggingface.co/PosterCraft/PosterCraft-v1_RL (secondary) | not found | huggingface | HARDWARE_BLOCKED (diffusion without GPU) | no | no | registry entry (UNAVAILABLE) | — | **WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED** |
| PosterMaker |  (none) | not found | unknown | diffusion: HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | **NOT_RELEASED_OR_UNFOUND, HARDWARE_BLOCKED** |
| PosterVerse | paper: arXiv 2601.03993 (blueprint LLM -> diffusion background -> MLLM HTML text rendering (secondary) | not found | unknown | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| ↳ APEX use | HTML-rendered text over generated background == APEX policy: facts are never rasterised | | | | | | | | |
| PosterGen |  (none (agent framework per spec)) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| BannerAgency |  (none (multi-agent banner framework per spec)) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| PosterO |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| Scan-and-Print |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| Uni-Layout |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| SlidePoise |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| SlideGen |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | **ARCHITECTURE_REFERENCE** |
| Qwen-Image-2.1 |  (none found for 2.1) | not found |  | 20B+ diffusion: HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | **NOT_RELEASED_OR_UNFOUND, HARDWARE_BLOCKED** |
| UI-TARS-2 |  (only UI-TARS-1.5 / 7B-DPO found) | not found for UI-TARS-2 |  | — | no | no | registry entry (UNAVAILABLE) | — | **NOT_RELEASED_OR_UNFOUND** |
| GraphicDesignBench | paper: arXiv 2604.04192 (LICA; 50 tasks, 5 axes); package: PyPI lica-gdb 0.2.1 (Apache-2.0 (primary-pypi) | package Apache-2.0 (PyPI metadata); paper CC BY 4.0; dataset terms unconfirmed | dataset: LICA layered-composition data (host to be determined by the package) | — | yes (package) | no | apex_one/lab/benchmarks/gdb_provider.py | `gdb verify` (stub) passed; local-model run pending | **PACKAGE_INSTALLABLE** |

## What actually runs

* **Design generation:** the native APEX engines (layout genome, compiler, tournament) — licence-clean.
* **Design judging:** calibrated-reliable local vision judges: NONE — no judge has passed calibration, so the Vision Council and the pairwise protocol report NOT_MEASURED in jobs.
* **Design benchmarking:** APEX Design Bench (15 page types) and the GraphicDesignBench smoke bundle through the $0 broker.
* **Not running:** every specialist checkpoint above whose weights are unreachable or too large; their roles are filled by native engines and recorded as such in each job's `design_routes.json`.

