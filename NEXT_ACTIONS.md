# Next actions (ordered)

**Production closure mode.** No new model hunts, benchmarks or features. Human-only work is in
**HUMAN_ACTIONS_REQUIRED.md**. The authoritative blocker list is **PRODUCTION_BLOCKERS.md**, and the acceptance
rule is **PRODUCTION_ACCEPTANCE.md**. Run `apex-one release check` at any time.

## The moment a required human input lands (no code changes needed)

| when this appears | run | result |
|---|---|---|
| the brand folder (BRAND_PACKAGE_INTAKE.md) | `apex-one brand checksums <folder>` → `apex-one brand import <folder> --dry-run` → `apex-one brand import <folder>` → `apex-one brand validate` | BRAND_ASSETS_VALIDATED |
| an approver (APPROVER_SETUP.md) | `apex-one auth add-approver "<name>"` → `apex-one auth verify-ledger` | AUTHORIZED_APPROVER_CONFIGURED |
| official evidence for one opportunity (REAL_OPPORTUNITY_PILOT.md) | `apex-one evidence check <pack>` → `apex-one evidence run <pack> --quality ultra` → approve → `apex-one release export` → `apex-one release verify` | REAL_OPPORTUNITY_VALIDATED; first FINAL |

The full sequence is FIRST_PRODUCTION_RUNBOOK.md.

## EXPERIMENTAL / OPTIONAL IMPROVEMENT (not needed for production; not scheduled)

These need no work until someone chooses them:
- Gemini judge (`apex-one vision validate-gemini` once a key exists);
- GraphicDesignBench at full size (needs huggingface.co);
- Qwen3-VL 8B Q8_K_XL and larger models (need ≥ 24 GB RAM);
- remote providers;
- licence decisions for evaluation-only models;
- model-page stability sampling;
- a long load soak.

Any routing change after these needs new evidence on the identical contract, a verified licence, passing tests,
`apex-one reports` and a reasoned baseline update (PRODUCTION_ACCEPTANCE.md).
