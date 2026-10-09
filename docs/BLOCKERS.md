# BLOCKER REPORT (what could not be verified in the build environment, and why)

| Blocker | Cause | Effect | How to unblock |
|---|---|---|---|
| No remote model was ever called | Egress proxy returned HTTP 403 for NVIDIA, Groq, OpenRouter, Hugging Face; no API keys in the environment | All provider adapters are `CONFIGURED_BUT_UNTESTED` (tested only with mocked HTTP). Model-dependent steps used native engines or reported `NOT_MEASURED` | Add keys to `.env`, `apex-one providers attest <id> --by <name>`, `apex-one providers --probe` |
| No licence could be verified | Hugging Face / arXiv / GitHub unreachable | Every external model (incl. all design specialists) is production-blocked (`UNKNOWN`/`NON_COMMERCIAL`) | Read each licence, then `apex-one license verify ...` |
| No specialist design model executed | No GPU, no weights, licences unverified | Design routes resolve to native APEX engines; PosterReward-class reward is `NOT_MEASURED` | Serve the model behind `APEX_DESIGN_ENDPOINT_*`, verify its licence, run the Design Bench |
| Subjective vision judgements | No $0 vision-capable route | "memorable", "AI-generated look", "Arabic visually natural", "belongs to APEX" are `NOT_MEASURED`; the human release gate covers them | Configure a free vision route (e.g. Gemini free tier, local qwen2.5vl via Ollama) |
| Live web research | No SearXNG instance, no outbound web access | A real "Berea College Fall 2027" job stops at `SOURCE_DISCOVERY` (BLOCKED) — by design it never invents facts | `docker compose --profile research up -d searxng` + `SEARXNG_URL`, or `--sources DIR` with saved official pages |
| PostgreSQL + pgvector | No running server in the container | Tested on SQLite only; schema is portable (JSON columns) | `docker compose --profile db up -d postgres`, set `APEX_DATABASE_URL`, `apex-one db-upgrade` |
| Original APEX logo | Not provided | A placeholder wordmark/robot is used and brand QA reports it | Put the logo file at `apex_one/assets/brand/…`, set `is_placeholder: false` |
| Real Berea facts | Not fetchable and must not be fabricated | The golden benchmark uses a fictional, clearly labelled synthetic corpus | Run a real job with sources |
| GitHub push | Claude GitHub App lacks access to this repository (HTTP 403) | Commits exist locally on `claude/charming-archimedes-2guzc9` only | Connect GitHub / install the Claude GitHub App, then push |
| Model download / local inference | 4 vCPU, 15.7 GB RAM, no GPU; deliberately no automatic downloads | No local model run | `apex-one doctor` lists runnable models (e.g. gpt-oss-20b needs ≥16 GB) |
