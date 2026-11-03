# Production acceptance

**Machine-readable rule:** `config/production_acceptance.yaml`. It is read by `apex-one release check`,
`apex-one reports` and the test suite. This page explains the rule; if the two ever disagree, the YAML file wins.

## The rule

**PRODUCTION_READY = YES only if every one of these is YES:**

| required dimension | what makes it YES | how to get there |
|---|---|---|
| BRAND_ASSETS_VALIDATED | `apex-one brand validate` prints VALID | BRAND_PACKAGE_INTAKE.md |
| AUTHORIZED_APPROVER_CONFIGURED | at least one active release approver and an intact approval ledger | APPROVER_SETUP.md |
| REAL_OPPORTUNITY_VALIDATED | a real (non-synthetic, non-test-domain) job reached RELEASE_CANDIDATE from authoritative evidence | REAL_OPPORTUNITY_PILOT.md |
| PRODUCTION_LOAD_VALIDATED | every load-test scenario PASS in PRODUCTION_MODE with the real production model | already YES |
| OFFLINE_PIPELINE_VALIDATED | golden ULTRA passes every quality target, guarded by a regression test | already YES |
| LOCAL_MODEL_ROUTING_VALIDATED | every deployed model route rests on identical measurements and a verified licence | already YES |

Each status comes from a live probe (`config/production_blockers.yaml` → `apex_one/lab/blockers.py`), never from
text someone wrote.

## Not required for production (may stay PARTIAL or NO)

| dimension | why it is not a release dependency |
|---|---|
| VISION_GATE | No release decision depends on a model judge. Absolute visual quality is reported as NOT_MEASURED on the release candidate, and the human approver reviews the final PDF. |
| DESIGN_MODEL_VALIDATION | Native APEX design is primary on every page type. |
| REMOTE_FREE_COMPUTE_VALIDATED | The $0 local route serves every production model task. |
| ARCHITECTURE_COMPLETE | Structural; already YES and covered by the test suite. |

These belong under **EXPERIMENTAL / OPTIONAL IMPROVEMENT**: Gemini, GraphicDesignBench expansion, Qwen3-VL 8B Q8_K_XL,
larger models, remote providers and pending licences for evaluation-only models. They are listed in
PRODUCTION_BLOCKERS.md under that heading. `apex-one release check` never shows them.

## The check

```
apex-one release check
```

It prints `READY` (exit 0), or `BLOCKED` (exit 1) followed only by the required dimensions that are not YES, each with
its next action.

## The validated baseline

`docs/evidence/APEX_ONE_OFFLINE_VALIDATED_BASELINE.json` records the validated system:
- the baseline commit and its test count;
- the hash of the routing decisions;
- the hash of the memory policy;
- the hash of the acceptance rule;
- the brand-contract, approval-contract, evidence-pack and load-test versions.

`apex-one release baseline` reports UNCHANGED or DRIFT, and the test suite fails on drift.

**Routing is frozen.** A routing change requires all of the following:
- new measured evidence, on the identical benchmark contract (same tasks, token budgets and checker version);
- a verified licence for any deployed model;
- passing regression tests;
- regeneration of the policy from evidence (`apex-one reports`);
- a deliberate baseline update with a reason (`apex-one release baseline --write --reason "..." --tests <n>`).

There is no manual model promotion: the policy file is generated, never edited.

Changing this acceptance rule is the same kind of deliberate change: edit the YAML with a reason, regenerate the
reports, pass the tests, and re-record the baseline.
