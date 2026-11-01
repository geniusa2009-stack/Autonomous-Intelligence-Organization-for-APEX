# Next actions (ordered)

Everything Claude can still do on its own. Human-only work is in **HUMAN_ACTIONS_REQUIRED.md**. The authoritative
blocker list, with live status, is **PRODUCTION_BLOCKERS.md** (source: `config/production_blockers.yaml`).

## The moment a human action lands (no code changes needed)

| when this appears | Claude runs | result |
|---|---|---|
| `GEMINI_API_KEY` + `apex-one providers attest gemini` | `apex-one vision validate-gemini` (re-run to resume; ~200 requests/day on the free tier) | Gemini verdict (ROBUSTLY_CALIBRATED / CANONICAL_640_ONLY / UNQUALIFIED), pinned to the exact model version; reports regenerated |
| an evidence pack for one real opportunity | `apex-one evidence check <pack>` then `apex-one evidence run <pack>` | Fact Lock, deadline / eligibility / funding validation, guide, QA, release candidate (or the exact missing source) |
| the APEX brand folder | `apex-one brand import <folder> --dry-run`, then `apex-one brand import <folder>` and `apex-one brand validate` | BRAND_ASSETS_VALIDATED |
| an approver exists | `apex-one auth verify-ledger`; on approval, FINAL re-checks that the approved artifact hash still matches | HUMAN_APPROVAL_VALIDATED |
| licence decisions recorded | `apex-one reports` | EVALUATION_ONLY routes become deployable (or stay native) |
| `huggingface.co` allowed | the queue's GDB steps at n ≥ 20 | DESIGN_MODEL_VALIDATION evidence |

## Autonomous work still open

1. **Model-page stability.** Two more samples per model-written page type. Measure run-to-run stability. Promote
   only a loss-free, stable lead over native. Native stays primary until then.
2. **Load test with longer duration.** The current harness runs about 50 jobs. A soak run (hundreds of jobs,
   several hours) would expose fragmentation and page-cache churn. Command:
   `python -m apex_one.lab.load_test --only concurrent_safe` in a loop under the queue lock.
3. **Hardware-bound candidates.** On a machine with ≥ 24 GB RAM, Qwen3-VL 8B Q8_K_XL and gpt-oss 20B would be
   admitted. Run `APEX_RETRY_BLOCKED=1 scripts/snapshot_run.sh <commit> scripts/validation_queue.py --max-steps 3`.
   The pre-acquisition admission still decides.
