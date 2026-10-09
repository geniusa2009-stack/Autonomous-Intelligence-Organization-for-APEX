# ARCHITECTURE

```
                         ┌──────────── ONE Governor (plans, budgets, gates — never does the work) ───────────┐
 mission ──► MissionAnalyzer ─► ExecutionPlan ─► JobRunner (declarative state machine, checkpoint per state) │
                         └───────────────────────────────────────────────────────────────────────────────────┘
   ONE Compute: CapabilityRouter ─► ZeroCostFirewall ─► Health/Quota/RateLimit ─► Adapter   (else LOCAL_FALLBACK/WAIT/QUEUE/DEGRADE)
   ONE Research ─► ONE Evidence ─► FACT_LOCK ─► ONE Knowledge (graph) ─► ONE Opportunity Intelligence
   Reader model ─► NarrativeArchitect ─► APEXEgyptianWriter ─► critics ─► semantic diff ─► Document AST
   Design Genome ─► Design Intent ─► Creative directions ─► Layout search + tournament ─► Compiler (HTML/CSS)
   Chromium render ─► Deterministic QA ─► Vision judges ─► Design jury ─► Mutation ─► Document QA (contact sheet + Reader Lab)
   Research re-check ─► Quality Court + gates + Licence guard ─► RELEASE_CANDIDATE ─► HUMAN ─► FINAL ─► LEARN (Memory)
```

## Package map
| Package | Responsibility |
|---|---|
| `apex_one.core.schemas` | Typed contracts (Pydantic v2): Mission, Job, JobPolicy, RiskProfile, ComputePolicy, QualityProfile, ExecutionPlan, StageResult, Failure, RetryPolicy, HumanGate, Claim, Evidence, Source, Contradiction, Verification, FactLock, OpportunityModel, DocumentAST, Genes, DesignIntent, LayoutCandidate, Metric (with `NOT_MEASURED`), QualityReport |
| `apex_one.core.state_machine` | 33 top-level states, allowed transitions, failure→recovery map, ~200 explicit checks |
| `apex_one.core.governor` | MissionAnalyzer, Governor (plan), JobRunner (state handlers, recovery, human actions) |
| `apex_one.persistence` | SQLAlchemy models, sessions, Alembic migrations (`migrations/`) |
| `apex_one.compute` | registry loader, firewall, router, fallback planner, quotas, health, providers, broker, benchmark, hardware planner |
| `apex_one.research` | discovery (SearXNG, browser-use, local manifests, fixtures), fetchers (HTTP robots-aware, Playwright, local, fixture), parsers (bs4, PyMuPDF, Docling optional), extractor, contradiction hunter, verifier + FactLocker, swarm |
| `apex_one.knowledge` | ontology, relational graph with traversal/provenance, retrieval |
| `apex_one.opportunity` | OpportunityModel builder (facts cite locks; opinions labelled) |
| `apex_one.editorial` | voice genome, architect, writer, critics, fact guard (semantic diff, lock registry) |
| `apex_one.document` | AST runs/builder, compiler (HTML/CSS, fonts, bidi isolation, fact spans) |
| `apex_one.design` | genome, intent, mutation, repair, tournament, assets (SVG), models (arsenal adapters + router) |
| `apex_one.vision` | renderer (Playwright), DOM metrics probe, derived images, contact sheet, judges |
| `apex_one.qa` | geometry, typography, rtl, accessibility, brand, print, facts_dom, hierarchy, court, deterministic |
| `apex_one.reader_lab` | personas, reader model, simulator |
| `apex_one.memory` | Semantic/Episodic/Evidence/Design/Voice/Failure/Approval memories + Preference memory/scorer |
| `apex_one.lab` | Design Bench, golden benchmark, experiments, research-only inventory |
| `apex_one.release` | licence guard, artifact completeness, secret scan, approval record, export |
| `apex_one.apps` | CLI (Typer), API (FastAPI), worker, studio |

## Why these choices
* **Explicit state machine, not a framework**: every transition is a table entry and a test; resumable from
  `job.json` checkpoints. LangGraph/Prefect were not needed for durable semantics at this scale.
* **Facts as slots**: copy contains `{{slot}}` tokens rendered from FactLocks into
  `<span data-slot data-lock-hash>`; QA re-reads the *rendered DOM* and compares to the locks. A writer or
  designer cannot silently change a locked value.
* **Native engines everywhere a model could be missing**: deterministic writer, layout grammar, compiler, SVG,
  reward heuristics and vision proxies keep the pipeline working at $0 with no model; models only add.
* **Metrics are honest**: anything not actually measured is `NOT_MEASURED` and never counts as a pass.

## Failure-specific recovery
FACT/RESEARCH → SOURCE_EXPANSION · VOICE → DRAFT · RTL → HTML_BUILD · GEOMETRY → LAYOUT_SEARCH (only failing pages) ·
AESTHETIC → MUTATION · READER → CONTENT_ARCHITECTURE (with missed slots as emphasis) · RHYTHM → CREATIVE_DIRECTIONS ·
COMPUTE → wait/queue · LICENSE → block for a human. Each kind has its own retry budget.

## Observability artifacts (per job)
`job.json, execution_plan.json, mission.json, sources.json, evidence.json, claims.json, contradictions.json,
verifications.json, fact_locks.json, knowledge_graph.json, opportunity_model.json, reader_model.json,
content_plan.json, draft_nodes.json, document_ast.json, design_intent.json, design_routes.json,
creative_directions.json, layout_search.json, design_decisions.json, design_candidates/, final.html, final.pdf,
screenshots/ (+derived/, mobile-preview.png), contact_sheet.png, qa/*, quality_report.json, license_report.json,
model_routing.json, model_calls.jsonl, routing_decisions.jsonl, checks.jsonl, events.jsonl, reproducibility.json`.
