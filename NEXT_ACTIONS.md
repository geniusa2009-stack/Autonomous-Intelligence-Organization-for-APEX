# Next actions (ordered)

## Needs a human (nothing below can be done honestly by the system alone)

1. **Supply the original APEX brand assets** into `assets/apex/` per `config/asset_contract.yaml`
   (`logo.svg`, `logo-on-dark.svg`, `robot.svg`, `brand.yaml` with `approved_by/approved_at/palette/fonts`), then
   `apex-one assets validate`. Until then every real job is blocked by the Brand Production Gate.
2. **Primary sources for a real job** — this container cannot reach any official site (egress 403). Either run on a
   machine whose network allows the official hosts and set `SEARXNG_URL`, or save the official Berea Fall 2027
   pages/PDFs with a `sources.yaml` and run
   `apex-one create-guide --opportunity "Berea College Fall 2027" --quality ultra --sources <dir>`.
   The job must stop at HUMAN_APPROVAL; approve with `apex-one approve <job> --by <name>`.
3. **Licence verification** for local models you want to use for PRODUCTION (content), after reading each licence:
   `apex-one license verify lic-gemma --license "Gemma Terms of Use" --state PRODUCTION_ALLOWED --source <url> --by <name>`
   (same for lic-qwen-open — the Qwen3-VL artifact ships an Apache-2.0 LICENSE file —, lic-gpt-oss,
   lic-nvidia-nemotron-nano). Until then they are evaluation-only.
4. **Approved reference documents** (ALA, TGS, FLEX, Berea guides you consider excellent; PDFs or screenshots):
   `apex-one genome ingest <files> --verdict approved --reason "..."`; rejected examples with `--verdict rejected`.
5. **A/B/C preferences**: `apex-one preference sheet <job>` then `apex-one preference record ...` for important
   pages; train a CANDIDATE scorer only with explicit approval once ≥ 30 pairs exist.

## System work (continue)

6. Let `scripts/run_local_council.py` → `scripts/run_local_design_evals.py` finish (chained, detached; logs in the
   session scratchpad), then `apex-one reports` and commit `docs/evidence/` + regenerated reports.
7. If any vision judge is calibrated RELIABLE: run golden ULTRA again (`apex-one benchmark --suite golden --quality
   ultra`) — the Vision Council and pairwise finalists then run for real; record council-vs-DOM disagreements.
8. If no judge calibrates reliably: try a larger local VLM only if it fits RAM (≤ ~10 GB GGUF) — e.g. Qwen3-VL 8B
   Q4 — and re-calibrate; never lower the reliability bar.
9. API authentication for `/jobs/*/approve` before exposing the API beyond 127.0.0.1.
10. Cloud free tiers (NVIDIA NIM, Groq, OpenRouter, Cloudflare, HF): on a network that allows them, add keys,
    `apex-one providers attest <id> --by <name>`, then `apex-one providers live-test`.
11. Specialist design checkpoints (PosterCopilot, WebGenAgent, MarkupDM, OmniSVG, StarVector, PosterReward): need
    Hugging Face access + a GPU; serve behind `APEX_DESIGN_ENDPOINT_*`, verify licences, benchmark with
    `apex-one benchmark --suite apex-design --job <job> --llm <id>`.
