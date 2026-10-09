# APEX ONE ULTRA — Phase 0 Repository Audit

Audit date: 2026-10-09
Auditor: Claude Code session (cloud container)

## 1. Current repository state

| Item | Finding |
|---|---|
| Git state | Repository initialised, **zero commits**, no tracked or untracked files |
| Branch | `claude/charming-archimedes-2guzc9` (the designated isolated feature branch; no `main` exists yet) |
| Existing architecture | None. The repository is empty. |
| Package/dependency files | None |
| Environment files | None (no `.env`, nothing to leak) |
| Tests | None |
| Docs | None |
| Migrations/storage | None |
| Uncommitted user work | None — nothing can be destroyed by building here |

Because the repository is empty, there is **no existing code to reuse or to
protect**. The build is greenfield. The designated branch
`claude/charming-archimedes-2guzc9` is already an isolated feature branch, so
no extra `feature/apex-one-ultra` branch is created (the session rules require
pushing to the designated branch).

## 2. Execution environment (measured, not assumed)

| Capability | Measured result |
|---|---|
| OS | Linux 6.18 (x86_64 container), 4 vCPU, 15 GB RAM, no GPU |
| Python | 3.13.16 (project supports 3.12+) |
| Package managers | `uv`, `pip`, `poetry` |
| Node | 22 |
| Chromium | Pre-installed at `/opt/pw-browsers/chromium-1194`; Playwright 1.63 expects a newer headless-shell build, so the renderer resolves an explicit executable path (verified: Chromium launches, renders Arabic RTL, prints PDF) |
| Fonts | System has no Arabic UI font except DejaVu Sans. IBM Plex Sans Arabic, Readex Pro and IBM Plex Mono (SIL OFL 1.1) were downloaded from Google Fonts and bundled in `apex_one/assets/fonts/` |
| Network: PyPI, Google Fonts | Reachable |
| Network: NVIDIA, Groq, OpenRouter, Hugging Face, arXiv, GitHub API | **Blocked by the egress proxy (HTTP 403 CONNECT)** |
| Provider credentials | None present in the environment |
| Docker / psql binaries | Present, but no running PostgreSQL server; SQLite is used as the development database |

Consequences that shape the build:

1. No remote model can be called from this container. All provider adapters are
   implemented against their documented HTTP APIs and are exercised with mocked
   transports in tests; their live status will honestly report
   `CONFIGURATION_REQUIRED` / `UNAVAILABLE` here.
2. No model licence can be verified online from this container. Every external
   model therefore starts as `UNKNOWN` (production-blocked) until a human records
   a verification with `apex-one license verify`. The licence name that is
   believed from prior knowledge is stored separately as `reported_license` and
   is never used to grant production rights.
3. Live web research cannot run here. The research pipeline is real (HTTP/
   Playwright fetching, HTML/PDF parsing, evidence extraction, contradiction
   detection, verification, fact locks) and runs end-to-end on a **clearly
   synthetic** offline corpus, plus on any local source files the user supplies.

## 3. What already exists / what can be reused

Nothing in the repository. Reusable external building blocks chosen:

| Need | Reused library |
|---|---|
| Schemas | Pydantic v2 |
| API | FastAPI + Uvicorn |
| CLI | Typer + Rich |
| Persistence | SQLAlchemy 2 + Alembic (SQLite dev, PostgreSQL prod, pgvector optional) |
| Templates | Jinja2 |
| Rendering | Playwright/Chromium (primary), WeasyPrint (fallback PDF) |
| Parsing | BeautifulSoup/lxml, PyMuPDF; Docling optional |
| Images | Pillow, NumPy |
| HTTP | httpx |

## 4. What is missing (everything) — and the honest boundary

Everything in the APEX ONE specification is missing and is built in this branch.
The honest boundary of what *can* be verified in this container:

* Verifiable here: schemas, state machine, governor, persistence + migrations,
  $0 firewall, routing, quotas, fallback/queueing, research pipeline on local and
  synthetic sources, evidence graph, contradiction resolution, fact locks,
  semantic diff, editorial pipeline (deterministic writer + critics), Document AST,
  Design Genome, design DAG routing, evolutionary layout search, Chromium rendering,
  DOM geometry/typography/RTL/contrast/print QA, contact sheet, reader simulation,
  quality court, memory, preference learning, lab/benchmark, CLI, API, release gate.
* Not verifiable here: any real remote model call, any specialist design model
  (PosterCopilot, OmniDocLayout, WebGenAgent, ...), any live licence check, live
  web search. These are registered, adapters are written where an inference
  interface is known, and their status is reported truthfully.

## 5. Risk areas

| Risk | Mitigation |
|---|---|
| Accidental paid API usage | `ZeroCostFirewall` on every call; immutable policy flags; unknown price = block; mandatory zero-cost test suite |
| Licence contamination of production output | Provenance on every artifact; release `LicenseGuard` blocks any artifact touched by a non-`PRODUCTION_ALLOWED` model |
| Fabricated facts | Writer emits fact *slots* bound to `FactLock`s; semantic diff over all text; DOM-level `data-claim-id` re-verification after render; offline benchmark is explicitly synthetic and labelled |
| Fake metrics | `Metric` type has an explicit `NOT_MEASURED` state; subjective metrics need a real judge |
| Over-claiming integrations | Two separate statuses: `IntegrationStatus` (code maturity) and runtime `Availability` (probe) |
| Arabic/RTL rendering defects | Bundled Arabic fonts, `<bdi>` isolation in the compiler, DOM-level bidi QA |
| Heavy downloads | Model acquisition planner only recommends; nothing auto-downloads |
| Session interruption | `PROGRESS.md`, `CURRENT_STATE.json`, `NEXT_ACTIONS.md`; jobs checkpoint after every state and are resumable |

## 6. Integration plan

Phases 1–13 of the specification are implemented in order inside a single Python
package `apex_one` (see §7). Each phase is committed after its tests pass.

## 7. Proposed final architecture (adapted)

The specification's tree uses top-level packages named `core`, `compute`, `memory`,
`qa`, ... Installing those as top-level Python packages would collide with other
libraries and with each other's generic names, so they live under one namespace:

```
apex_one/
  core/        governor/ state_machine/ schemas/ events/ policies/
  persistence/ SQLAlchemy models, session, repositories
  compute/     broker/ router/ registry/ providers/ quotas/ firewall/ benchmark/ hardware
  research/    discovery/ browser/ documents/ evidence/ contradiction/ verification/ swarm
  knowledge/   ontology/ graph/ retrieval/
  opportunity/ OpportunityModel builder
  editorial/   architect/ writer/ language/ voice/ fact_guard/
  document/    ast/ compiler/
  design/      genome/ intent/ grammar/ models/ layout/ tournament/ mutation/ repair/ assets/
  vision/      render/ page/ contact_sheet/ judges/
  reader_lab/
  qa/          geometry/ typography/ rtl/ accessibility/ print/ brand/ release/ court
  memory/      semantic/ episodic/ evidence/ design/ voice/ failure/ approval/ preference/
  lab/         benchmarks/ experiments/ research_only_models/
  release/
  apps/        api/ cli/ worker/ studio/
config/        model_registry.yaml design_capability_matrix.yaml license_registry.yaml
               providers.yaml quality_gates.yaml apex_brand.yaml voice.yaml readers.yaml
voice/         approved/ rejected/ warnings/ transitions/ jokes/ calls_to_action/
               bilingual_patterns/ jake_patterns/
migrations/    Alembic
tests/  docs/  artifacts/ (git-ignored job outputs)
```
