# Design Model Activation (Phases 16, 19, 26)

_Generated 2026-10-30 11:59 UTC by `apex-one reports build` from measured artifacts._

Every design system named in the APEX spec, with the evidence actually gathered here. Statuses: ACTIVATED, PROTOCOL_REIMPLEMENTED, PACKAGE_INSTALLABLE, WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED, ARCHITECTURE_REFERENCE, NOT_RELEASED_OR_UNFOUND, LICENSE_BLOCKED, RESEARCH_ONLY. Nothing is marked ACTIVATED without a stored smoke-test artifact.

Environment facts behind most rows: huggingface.co / GitHub releases / arXiv are denied by the egress policy (weights unreachable); 4 vCPU + 15.7 GB RAM + no GPU (7B+ VLMs blocked without GGUF builds).

| system | **final state** | source (evidence) | reported licence | checkpoint host | hardware | local | $0 remote | adapter | smoke test / artifacts | detail statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| OmniDocLayout-LLM | **NETWORK_BLOCKED** | paper: arXiv 2510.26213 (CVPR 2026); code: github.com/opendatalab/OmniDocLayout (per CVPR  (secondary) | not found | huggingface (release announced in paper) | 0.5B — CPU-runnable here if weights were reachable | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE |
| ↳ | weights host huggingface.co denied by the egress proxy (re-checked 2026-10-12); page_architecture specialist; native apex-native-layout performs the role meanwhile | | | | | | | | | |
| PosterCopilot-7B | **HARDWARE_BLOCKED** | model_card: huggingface.co/void-2024/PosterCopilot (qwen2_5_vl, eccv2026 tags) (secondary) | not found on card snippet | huggingface | 7B VLM fp16 ~16 GB: HARDWARE_BLOCKED on CPU without a GGUF c | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| SEGA-7B | **DEPENDENCY_MISSING** | paper: arXiv 2510.15749 (SEGA: stepwise evolution, content-aware layout) (secondary) | not found | unknown | 7B: HARDWARE_BLOCKED on CPU | no | no | registry entry (UNAVAILABLE) | — | NOT_RELEASED_OR_UNFOUND, ARCHITECTURE_REFERENCE |
| ↳ | no public checkpoint/code could be confirmed; stepwise coarse->fine refinement idea mirrored by the tournament's targeted mutation | | | | | | | | | |
| SEGA-13B | **DEPENDENCY_MISSING** | paper: arXiv 2510.15749 (secondary) | not found | unknown | 13B: HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | NOT_RELEASED_OR_UNFOUND, HARDWARE_BLOCKED |
| ↳ | no public checkpoint/code could be confirmed | | | | | | | | | |
| WebGenAgent-LM-7B | **HARDWARE_BLOCKED** | paper: arXiv 2509.22644 (WebGen-Agent); model_card: huggingface.co/luzimu/WebGenAgent-LM-7 (secondary) | MIT (SFT card) | huggingface | 7B fp16: HARDWARE_BLOCKED on CPU without GGUF | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| WebGenAgent-LM-8B | **HARDWARE_BLOCKED** | paper: arXiv 2509.22644 (secondary) | MIT expected (family); not confirmed | huggingface | HARDWARE_BLOCKED on CPU without GGUF | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| WebGenAgent-Step-GRPO | **NETWORK_BLOCKED** | paper: arXiv 2509.22644 (Step-GRPO with screenshot + GUI-agent feedback) (secondary) | not confirmed for Step-GRPO checkpoint | huggingface | HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, ARCHITECTURE_REFERENCE |
| ↳ | weights host huggingface.co denied by the egress proxy (re-checked 2026-10-12); screenshot-feedback loop is exactly APEX's render->QA->mutate loop (implemented natively) | | | | | | | | | |
| ScreenCoder | **NETWORK_BLOCKED** | repo_found: unofficial mirror github.com/syntax-syndicate/ScreenCoder-agent (secondary) | not found | github | depends on chosen VLM | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, ARCHITECTURE_REFERENCE |
| ↳ | weights host huggingface.co denied by the egress proxy (re-checked 2026-10-12); screenshot->structure extraction is done by apex-native-decomposer on DOM; VLM path via local Qwen3-VL possible | | | | | | | | | |
| DCGen | **NOT_IMPLEMENTED** | paper: arXiv 2406.16386 (FSE 2025) (secondary) | code licence not found | n/a | runs on any VLM | no | no | registry entry (UNAVAILABLE) | — | PROTOCOL_REIMPLEMENTABLE, ARCHITECTURE_REFERENCE |
| ↳ | prompting method (screenshot->code) could run on local VLMs; not implemented — the APEX pipeline compiles HTML natively and never needs screenshot->code | | | | | | | | | |
| MarkupDM | **HARDWARE_BLOCKED** | model_card: huggingface.co/cyberagent/markupdm; paper: arXiv 2409.19051 (secondary) | Apache-2.0 (repo) — base model StarCoderBase carries BigCode OpenRAIL-M terms; training data crello | huggingface | 7B fp16: HARDWARE_BLOCKED on CPU without GGUF | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| PosterReward | **ADAPTER_TESTED_ONLY** | paper: arXiv 2603.29855 (CVPR 2026); variants pairwise / lite / full, all Qwen3-VL-8B base (secondary) | not found | huggingface (assumed) | 8B VLM: CPU GGUF Q4 would be ~5 GB and slow (minutes per pai | no | no | apex_one/vision/pairwise.py (protocol) | pairwise unit tests; live judges: NONE yet (no calibrated-reliable vision judge) — the protocol does not run in jobs | WEIGHTS_UNREACHABLE, PROTOCOL_REIMPLEMENTED |
| ↳ | pairwise PROTOCOL runs with tests and real local judges; original Qwen3-VL-8B reward weights NETWORK_BLOCKED (huggingface.co denied); PosterReward-style PAIRWISE protocol (order-swapped twice, consistency required) runs on local vision judges ONLY when calibration marks them reliable — clearly labelled as protocol, not PosterReward weights | | | | | | | | | |
| LayerD | **NETWORK_BLOCKED** | paper: ICCV 2025 (CyberAgent, Tohoku); code: github.com/CyberAgentAILab/LayerD (secondary) | not found | github/huggingface | CPU feasible (slow) | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE |
| ↳ | weights host huggingface.co denied by the egress proxy (re-checked 2026-10-12) | | | | | | | | | |
| OmniSVG-4B | **NETWORK_BLOCKED** | model_card: huggingface.co/OmniSVG/OmniSVG1.1_4B (7.6 GB) (secondary) | Apache-2.0 (code/model); MMSVG dataset CC non-commercial | huggingface | 4B fp16 7.6 GB: CPU-feasible but slow | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE |
| ↳ | weights host huggingface.co denied by the egress proxy (re-checked 2026-10-12) | | | | | | | | | |
| OmniSVG-8B | **HARDWARE_BLOCKED** | model_card: OmniSVG org on huggingface (secondary) | Apache-2.0 (code/model); dataset non-commercial | huggingface | HARDWARE_BLOCKED (fp16 ~16 GB) | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| StarVector-1B | **NETWORK_BLOCKED** | model_card: starvector/starvector-1b-im2svg (secondary) | Apache-2.0 (secondary source only) | huggingface | CPU-feasible | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE |
| ↳ | weights host huggingface.co denied by the egress proxy (re-checked 2026-10-12) | | | | | | | | | |
| StarVector-8B | **HARDWARE_BLOCKED** | model_card: starvector/starvector-8b-im2svg (secondary) | Apache-2.0 (secondary source only) | huggingface | HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| PosterOmni | **DEPENDENCY_MISSING** |  (none) | not found | unknown | — | no | no | registry entry (UNAVAILABLE) | — | NOT_RELEASED_OR_UNFOUND |
| ↳ | no public checkpoint/code could be confirmed | | | | | | | | | |
| PosterCraft | **HARDWARE_BLOCKED** | model_card: huggingface.co/PosterCraft/PosterCraft-v1_RL (secondary) | not found | huggingface | HARDWARE_BLOCKED (diffusion without GPU) | no | no | registry entry (UNAVAILABLE) | — | WEIGHTS_UNREACHABLE, HARDWARE_BLOCKED |
| ↳ | 7B+ model needs a GPU or a GGUF build; weights also NETWORK_BLOCKED (huggingface.co denied) | | | | | | | | | |
| PosterMaker | **DEPENDENCY_MISSING** |  (none) | not found | unknown | diffusion: HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | NOT_RELEASED_OR_UNFOUND, HARDWARE_BLOCKED |
| ↳ | no public checkpoint/code could be confirmed | | | | | | | | | |
| PosterVerse | **RESEARCH_ONLY** | paper: arXiv 2601.03993 (blueprint LLM -> diffusion background -> MLLM HTML text rendering (secondary) | not found | unknown | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run; HTML-rendered text over generated background == APEX policy: facts are never rasterised | | | | | | | | | |
| PosterGen | **RESEARCH_ONLY** |  (none (agent framework per spec)) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| BannerAgency | **RESEARCH_ONLY** |  (none (multi-agent banner framework per spec)) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| PosterO | **RESEARCH_ONLY** |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| Scan-and-Print | **RESEARCH_ONLY** |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| Uni-Layout | **RESEARCH_ONLY** |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| SlidePoise | **RESEARCH_ONLY** |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| SlideGen | **RESEARCH_ONLY** |  (none) | — |  | — | no | no | registry entry (UNAVAILABLE) | — | ARCHITECTURE_REFERENCE |
| ↳ | method folded into native engines; no model is run | | | | | | | | | |
| Qwen-Image-2.1 | **DEPENDENCY_MISSING** |  (none found for 2.1) | not found |  | 20B+ diffusion: HARDWARE_BLOCKED | no | no | registry entry (UNAVAILABLE) | — | NOT_RELEASED_OR_UNFOUND, HARDWARE_BLOCKED |
| ↳ | no public checkpoint/code could be confirmed | | | | | | | | | |
| UI-TARS-2 | **DEPENDENCY_MISSING** |  (only UI-TARS-1.5 / 7B-DPO found) | not found for UI-TARS-2 |  | — | no | no | registry entry (UNAVAILABLE) | — | NOT_RELEASED_OR_UNFOUND |
| ↳ | no public checkpoint/code could be confirmed | | | | | | | | | |
| GraphicDesignBench | **LIVE_TESTED** | paper: arXiv 2604.04192 (LICA; 50 tasks, 5 axes); package: PyPI lica-gdb 0.2.1 (Apache-2.0 (primary-pypi) | package Apache-2.0 (PyPI metadata); paper CC BY 4.0; dataset terms unconfirmed | dataset: LICA layered-composition data (host to be determined by the package) | — | yes (package) | no | apex_one/lab/benchmarks/gdb_provider.py | qwen3-vl-4b-q4kxl-full: {"metadata": {}, "results": {"category-1": {"custom:apex_one.lab.benchmarks.gdb_provider:APEXBrokerModel": {"scores": {"; gemma3-4b-q4km | ACTIVATED (smoke bundle) |
| ↳ | lica-gdb 0.2.1 ran the verification bundle against a real local model through the $0 broker; full dataset NETWORK_BLOCKED (Hugging Face) | | | | | | | | | |

**Final states:** ADAPTER_TESTED_ONLY 1, DEPENDENCY_MISSING 6, HARDWARE_BLOCKED 7, LIVE_TESTED 1, NETWORK_BLOCKED 6, NOT_IMPLEMENTED 1, RESEARCH_ONLY 8


## What actually runs

* **Design generation:** the native APEX engines (layout genome, compiler, tournament) — licence-clean.
* **Design judging:** calibrated-reliable local vision judges: NONE — no judge has passed calibration, so the Vision Council and the pairwise protocol report NOT_MEASURED in jobs.
* **Design benchmarking:** APEX Design Bench (15 page types) and the GraphicDesignBench smoke bundle through the $0 broker.
* **Not running:** every specialist checkpoint above whose weights are unreachable or too large; their roles are filled by native engines and recorded as such in each job's `design_routes.json`.

## GraphicDesignBench (lica-gdb) — real runs

Benchmarks registered by the package: 39. Ran here: 6 (category-1, layout-4, layout-5, svg-1, template-1, typography-1). Skipped: 33 — their data lives on the Hugging Face Hub, which the egress proxy denies (dependency missing). Skipped tasks are NOT scored as zero and supported tasks are not passes: only the numbers below were measured.

The offline verification bundle ships **2 samples per task**, so every score below is an n=2 smoke measurement — enough to prove the pipeline runs a real model end-to-end, far too small to rank models.

| run | task | n | ok | failed | scores | runtime |
|---|---|---|---|---|---|---|
| gemma3-4b-q4km | category-1 | 2 | 2 | 0 | top1_accuracy=0.00, top5_accuracy=0.00, macro_f1=0.00 | — s total |
| gemma3-4b-q4km | layout-4 | 2 | 2 | 0 | accuracy=0.50, f1=0.33, precision=0.33, recall=0.33 | — s total |
| gemma3-4b-q4km | layout-5 | 2 | 2 | 0 | mae=20.00, mse=481.00 | — s total |
| gemma3-4b-q4km | svg-1 | 2 | 2 | 0 | accuracy=0.50 | — s total |
| gemma3-4b-q4km | template-1 | 2 | 2 | 0 | accuracy=0.50, precision=0.50, recall=0.50, f1=0.50, auc_roc=0.00, average_precision=0.00 | — s total |
| gemma3-4b-q4km | typography-1 | 2 | 2 | 0 | accuracy_top1=0.50, f1_montserrat=0.67, f1_macro=0.67 | — s total |
| gemma3-4b-q4km-full | category-1 | 2 | 2 | 0 | top1_accuracy=0.00, top5_accuracy=0.00, macro_f1=0.00 | 795 s total |
| gemma3-4b-q4km-full | layout-4 | 2 | 2 | 0 | accuracy=0.50, f1=0.33, precision=0.33, recall=0.33 | 795 s total |
| gemma3-4b-q4km-full | layout-5 | 2 | 2 | 0 | mae=20.00, mse=481.00 | 795 s total |
| gemma3-4b-q4km-full | svg-1 | 2 | 2 | 0 | accuracy=0.50 | 795 s total |
| gemma3-4b-q4km-full | template-1 | 2 | 2 | 0 | accuracy=0.50, precision=0.50, recall=0.50, f1=0.50, auc_roc=0.00, average_precision=0.00 | 795 s total |
| gemma3-4b-q4km-full | typography-1 | 2 | 2 | 0 | accuracy_top1=0.50, f1_montserrat=0.67, f1_macro=0.67 | 795 s total |
| qwen3-vl-4b-q4kxl-full | category-1 | 2 | 2 | 0 | top1_accuracy=0.00, top5_accuracy=0.50, macro_f1=0.00 | 491 s total |
| qwen3-vl-4b-q4kxl-full | layout-4 | 2 | 2 | 0 | accuracy=0.50, f1=0.33, precision=0.33, recall=0.33 | 491 s total |
| qwen3-vl-4b-q4kxl-full | layout-5 | 2 | 2 | 0 | mae=24.50, mse=690.50 | 491 s total |
| qwen3-vl-4b-q4kxl-full | svg-1 | 2 | 2 | 0 | accuracy=1.00 | 491 s total |
| qwen3-vl-4b-q4kxl-full | template-1 | 2 | 2 | 0 | accuracy=0.50, precision=0.50, recall=0.50, f1=0.50, auc_roc=0.00, average_precision=0.00 | 491 s total |
| qwen3-vl-4b-q4kxl-full | typography-1 | 2 | 2 | 0 | accuracy_top1=0.00, f1_montserrat=0.00, f1_macro=0.00 | 491 s total |

