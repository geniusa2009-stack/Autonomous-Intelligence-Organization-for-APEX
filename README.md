# APEX ONE ULTRA

**Autonomous Research, Editorial, Design & Quality Intelligence Organization** for APEX — the Egyptian
student-opportunity platform.

```
apex-one create-guide --opportunity "Berea College Fall 2027" --quality ultra --budget 0
```

APEX ONE researches an opportunity from primary sources, builds an evidence graph, resolves contradictions,
**locks** critical facts, models the opportunity and the Egyptian reader, writes natural Egyptian-Arabic +
English copy, compiles a Document AST into editorial HTML/CSS, evolves competing layouts, renders real pages
in Chromium, runs deterministic geometry/typography/RTL/print/fact QA, simulates readers, judges quality in a
court of independent judges, and stops at a **human release gate**. It runs with a hard **$0.00 API budget**.

> APEX is not any model. Models are replaceable compute engines. APEX intelligence = knowledge + evidence +
> memory + decision history + APEX Voice + Design Genome + workflow + evaluation + preference data.

## Honest status (verified in this repository)

| Area | Status |
|---|---|
| Schemas, declarative 33-state machine, ~200 explicit checks | Working, tested |
| SQLite/PostgreSQL persistence + Alembic migrations | Working (SQLite tested; PostgreSQL via `docker compose`, untested here) |
| ZeroCostFirewall, capability router, quotas, fallback, broker | Working, tested (incl. mandatory zero-cost suite) |
| Provider adapters (NVIDIA NIM, Groq, Gemini, OpenRouter, Cloudflare, HF, Ollama, llama.cpp, MLX, vLLM, SGLang) | Code implemented, **tested only against mocked HTTP**; no live provider reachable from the build container |
| Research swarm, HTML/PDF parsing, evidence extraction, contradictions, verification, FACT_LOCK, KG | Working on local + synthetic sources; live search needs `SEARXNG_URL` |
| Editorial (Voice Genome, writer, critics), Document AST | Working (native deterministic writer; model polish optional) |
| Design Genome, intent, grammar, compiler, evolutionary tournament | Working, tested with real Chromium renders |
| Deterministic QA (geometry, typography, RTL/bidi, contrast, brand, print, DOM fact integrity) | Working, tested |
| Vision judges | Measurable proxies working; subjective judgements `NOT_MEASURED` without a $0 vision model |
| Specialist design models (PosterCopilot, OmniDocLayout, WebGenAgent, PosterReward, ...) | **Registered**; endpoint adapters for LLM-style models are `CONFIGURED_BUT_UNTESTED`; pipelines/methods `NOT_YET_SUPPORTED`; none licence-verified, so none used in production |
| Reader Lab, Quality Court, Memory (8 stores), preference learning, ONE Lab | Working, tested |
| CLI, FastAPI, worker, studio page | Working, tested |
| Golden end-to-end benchmark (SYNTHETIC Berea-style) | Reaches `RELEASE_CANDIDATE` and stops at the human gate |

See `docs/BLOCKERS.md` for exactly what could not be verified and why.

## Start

```bash
./scripts/bootstrap.sh          # venv, deps, Chromium check, migrations, doctor
source .venv/bin/activate
apex-one doctor
apex-one benchmark --suite golden --quality ultra     # offline, synthetic, ~1 min
apex-one create-guide --opportunity "Berea College Fall 2027" --quality ultra --budget 0
```

The real Berea job needs a research route (`SEARXNG_URL`) or saved official sources (`--sources DIR`). Without
either it stops at `SOURCE_DISCOVERY` with a clear blocker — it never invents facts.

## Documentation

`QUICKSTART.md` · `docs/ARCHITECTURE.md` · `docs/MODEL_ARSENAL.md` · `docs/DESIGN_FOUNDRY.md` ·
`docs/ZERO_COST_COMPUTE.md` · `docs/SECURITY.md` · `docs/LICENSE_POLICY.md` · `docs/TESTING.md` ·
`docs/BLOCKERS.md` · `docs/APEX_ONE_ULTRA_AUDIT.md` · `PROGRESS.md` · `NEXT_ACTIONS.md`
