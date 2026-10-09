# TESTING

```bash
source .venv/bin/activate
python -m pytest                      # full suite (~70 s; real Chromium renders included)
python -m pytest -m "not browser"     # skip rendering tests
python -m pytest tests/test_zero_cost.py   # mandatory $0 suite
apex-one benchmark --suite design     # APEX Design Bench (21 cases)
apex-one benchmark --suite golden --quality ultra
```

| File | Covers |
|---|---|
| test_zero_cost.py | paid primary/fallback, price change, quota (self-imposed, 429), unknown price/licence, budget, attestation expiry, 402, privacy, exhaustive registry sweep |
| test_compute.py | OpenAI-compatible/Gemini/Cloudflare adapters (mock transport), local /v1 normalisation, OpenRouter price feed, capability routing, broker logging, hardware planner, circuit breaker, model bench on mock |
| test_registry.py | every spec-named model in all three registries; licence invariants; IMPLEMENTED only for in-repo engines |
| test_state_machine.py | transitions, human-only FINAL, failure-specific recovery, budgets |
| test_persistence.py | migrations, tables, sessions |
| test_research.py | normalisers (Arabic digits/months), rule extractor, full synthetic research (stale cycle, blog, forum), NEEDS_HUMAN, official disagreement, model extractor anti-hallucination, semantic diff + lock immutability, KG traversal/persistence, robots, SearXNG, authority, live-without-route block, local manifests |
| test_editorial.py | rhythm plan, fact-bound writer, opinions labelled, missing lock drops sentence, Latin isolation, critics (MSA, cliché, wrong date, certainty, humor in warning, missing hedge), AST tamper, opportunity model, reader misunderstanding |
| test_design.py | genome sampling, mutation invariants, compiler fact binding/bidi/no forbidden CSS, signatures, repair, design router fallback + licence/availability gating, endpoint adapter (mock), intent |
| test_render_qa.py | real render (pages, PDF, mobile, fonts), document QA, tampered DOM fact detection, contact sheet/rhythm/derived images, tournament, Design Bench |
| test_pipeline.py | mission analysis, budget refusal, live-without-route BLOCKED (no facts invented), missing cycle, golden end-to-end + resume + human approval + learning, fact conflict → human confirm → resume |
| test_api_cli.py | health/ready/providers/models, job lifecycle, traversal guard, budget refusal, CLI doctor/models/providers/attest/licence verify |
| test_memory_lab.py | 8 memories separated, preference pairs + scorer approval gate, ONE Lab promotion gate, research-only inventory, licence guard, court disagreement + NOT_MEASURED gates |

Live tests: none of the provider tests hit the network. Set `APEX_LIVE_TESTS=1` with real keys to add your own
live checks; they are disabled by default.
