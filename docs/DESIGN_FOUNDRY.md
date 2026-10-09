# DESIGN FOUNDRY

## Same DNA, different organism
`config/apex_brand.yaml` holds the **invariant DNA** (deep navy, metallic silver, white, restrained signal
accent, warning red for money/eligibility warnings only; IBM Plex Sans Arabic + Readex Pro + IBM Plex Mono; logo
and robot-signature rules; forbidden effects: gradients, glassmorphism, radius > 4px, shadows, more than 2
card-like boxes per page) and the **evolvable gene space** (archetype, grid/column structure, asymmetry, type
scale, base size, weight, density, whitespace, margins, hero/number treatment, section division, timeline style,
data-viz, visual metaphor, tone, Arabic wrapping). Mutation can only touch genes.

The bundled wordmark and robot are **placeholders**; brand QA reports this until the original APEX logo file is
placed at the path in `apex_brand.yaml` (`is_placeholder: false`).

## Archetypes (layout grammar)
`cover-monument`, `editorial-column`, `split-asymmetric`, `hero-number`, `ledger`, `manifesto`, `timeline-rail`,
`checklist-sheet`, `quiet-breath`. Each places Document-AST blocks into explicit, non-overlapping grid zones
(RTL grid, column 1 = right edge) with archetype-specific vertical anchoring. Covers, breaths and timelines are
archetype-strict; other node types prefer (92%) their editorial archetypes.

## Pipeline
1. **Design intent** per page from the AST: reading mode, rhythm role, density target, tone hint, first fixation, rationale.
2. **Creative directions** (`quiet-precision`, `monumental`, `blueprint`): in high/ultra mode each direction runs a
   mini-tournament on the cover, snapshot and funding pages; the best mean fitness wins.
3. **Layout search** per page: N seeded candidates (ultra: 32 for importance ≥ 4, 16 otherwise) compiled into a
   single batch HTML, rendered once in Chromium, measured per candidate.
4. **Deterministic filter**: any critical geometry/RTL/fact issue rejects the candidate (repair genes are tried
   for all-rejected populations: failure-specific shrink, single column, margins, tone).
5. **Scoring** with measured metrics only: hierarchy (DOM saliency vs intended first fixation), typography, brand,
   RTL, contrast, alignment, density fit vs intent, sequence-aware novelty (adjacent archetype, repeated
   structure, consecutive dark pages, hero fatigue, DesignMemory verdicts), specialist reward **only if it ran**.
6. **Evolution**: tournament selection (k=3), elitism, uniform crossover, weakness-targeted mutation operators
   (typography, grid, whitespace, hierarchy, density, hero, number treatment, image balance, section division,
   Arabic wrapping, data-viz, metaphor, archetype), stop on convergence (ε) or generation budget.
7. **Document-level tournament**: dynamic programming over each page's top-3 to maximise total fitness minus
   cross-page rhythm penalties.
8. **Build** final HTML (fonts embedded, responsive mobile reflow, print CSS) → render → screenshots, derived
   images, PDF, mobile preview, contact sheet → QA → vision judges → design jury → targeted mutation of weak pages
   → document QA (rhythm + Reader Lab).

## Specialist models
`config/design_capability_matrix.yaml` maps roles to specialists in preference order with a native fallback, and
page types to DAGs (dense information, cover, narrative, sequence, emphasis, repair, reverse engineering). The
DesignRouter takes a specialist only if it is runtime-available **and** licence-eligible for the job's purpose;
every choice and every rejected alternative is written to `design_routes.json` / `design_decisions.json`.

To bring a specialist online (example PosterCopilot-7B):
1. Serve it behind an OpenAI-compatible endpoint on hardware you control (vLLM/SGLang): `APEX_DESIGN_ENDPOINT_POSTERCOPILOT=http://gpu:8000`.
2. Read its licence and record it: `apex-one license verify lic-postercopilot --license ... --state PRODUCTION_ALLOWED --source <url> --by <name>`.
3. Run `apex-one benchmark --suite design` and a ONE Lab experiment before relying on it.

## Measured vs not measured
Geometry, typography, RTL/bidi, contrast, palette/brand invariants, print structure, DOM fact integrity, saliency
hierarchy, rhythm statistics and novelty are measured deterministically. "Memorable", "looks AI-generated",
"Arabic visually natural" and "belongs to APEX" are **NOT_MEASURED** unless a $0 vision model or a human judges them.
