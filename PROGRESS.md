# APEX ONE ULTRA — Progress log

Last updated: 2026-10-09 (end of build session 1)

| Phase | Status | Evidence |
|---|---|---|
| 0 Repository audit | DONE | docs/APEX_ONE_ULTRA_AUDIT.md |
| 1 Schemas + state machine + persistence | DONE | 33 states, 199 checks, Alembic 0001/0002, tests/test_state_machine.py, test_persistence.py |
| 2 Compute broker + registries + $0 firewall | DONE | 55 models/engines, 13 providers, 42 licence records; tests/test_zero_cost.py (19 tests) |
| 3 Research + evidence + fact lock + KG | DONE | swarm, extractor, contradictions, verifier, FactLock, semantic diff, KG; tests/test_research.py |
| 4 Editorial + Voice Genome + Document AST | DONE | voice/, writer, critics; tests/test_editorial.py |
| 5 Design Genome + intent + compiler | DONE | config/apex_brand.yaml, 9 archetypes, compiler with fact spans + bidi |
| 6 Design model arsenal adapters | DONE (honest levels) | endpoint adapters CONFIGURED_BUT_UNTESTED, methods NOT_YET_SUPPORTED, native IMPLEMENTED |
| 7 Playwright renderer + deterministic QA | DONE | geometry/typography/RTL/contrast/brand/print/DOM-facts; tests/test_render_qa.py |
| 8 Vision + PosterReward interface + tournament | DONE | native vision proxy; model judge + PosterReward return NOT_MEASURED without a route |
| 9 Reader Lab + Quality Court | DONE | 9 personas, disagreement resolver, gates |
| 10 Memory + preference learning | DONE | 8 stores, APEXPreferencePair, Bradley-Terry scorer (approval-gated) |
| 11 CLI + API | DONE | apex-one (doctor, providers, models, license, create-guide, resume, inspect, approve, reject, export, prefer, facts, benchmark, lab, reproduce, api, worker); FastAPI + studio |
| 12 Benchmarks + docs | DONE | APEX Design Bench 19/19 measured pass, 2 NOT_MEASURED; docs/* |
| 13 End-to-end demo | DONE | golden ultra benchmark: RELEASE_CANDIDATE at human gate; reproduction identical |

Test status: `python -m pytest` → 111 passed (75.9 s).
Push status: BLOCKED — GitHub 403 (Claude GitHub App lacks access); commits are local.
