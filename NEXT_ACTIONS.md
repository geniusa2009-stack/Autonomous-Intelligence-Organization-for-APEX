# Next actions (ordered)

The local validation queue is finished: every planned step either ran, or ended in a recorded RESOURCE_BLOCKED or
SKIPPED decision. No model step can go further on this machine without one of the human actions below.

## Needs a human

1. **Gemini free-tier key**: the only legal $0 vision route that answers from this container. Put it in the environment's
   secrets as `GEMINI_API_KEY`. Never enable billing. Then run
   `apex-one providers live-test` and the same calibration suite (absolute, order-swapped pairwise, 3 repeats, legibility).
   This is the only path to a ROBUSTLY_CALIBRATED judge here.
2. **Brand package**: `apex-one brand import <folder>` (logo.svg, logo-on-dark.svg, robot.svg, and a brand.yaml that sets
   approved_by / approved_at / palette / fonts / font_files). Until then, BRAND_PRODUCTION_GATE = FAIL for real jobs.
3. **Approver**: `apex-one auth add-approver "<your name>"` (the token is shown once). Approve with
   `APEX_APPROVER_TOKEN=<token> apex-one approve <job>`.
4. **Network access** (environment settings → Network access → allowed domains), as needed:
   - `huggingface.co` (+ CDN), for the full GraphicDesignBench dataset and specialist design weights;
   - `integrate.api.nvidia.com`, `api.groq.com`, `openrouter.ai`, `api.cloudflare.com`, for free remote models;
   - the official sites of the target opportunity.
5. **Real job J-2fe410878683 (CNCF LFX 2027 Term 1)**: confirm the single-source deadline with
   `apex-one facts confirm J-2fe410878683 deadline.application --claim <id> --by "<name>"`. Supply the
   stipend and eligibility pages, then run `apex-one resume J-2fe410878683`.
6. **Licence reviews**: Gemma 3 (4B/12B), Nemotron and gpt-oss stay evaluation-only until a person runs
   `apex-one license verify ... --by <name>`.

## System work (no human needed)

7. A machine with ≥ 24 GB RAM would admit Qwen3-VL 8B Q8_K_XL (expected peak 21.0 GB) and gpt-oss 20B. The
   blocked steps are terminal. Re-open them with `APEX_RETRY_BLOCKED=1 scripts/snapshot_run.sh <commit>
   scripts/validation_queue.py --max-steps 3`. The pre-acquisition admission still decides.
8. Measure the run-to-run stability of model-written pages: two more samples per page type. A model page can be
   promoted over native only if it wins without a safety loss and is stable. Today, native wins or ties every
   page type.
