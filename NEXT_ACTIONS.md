# Next actions (ordered)

## Needs a human

1. **Brand package** → `apex-one brand import <folder>` (logo.svg, logo-on-dark.svg, robot.svg, brand.yaml with
   approved_by / approved_at / palette / fonts / font_files). Until then BRAND_PRODUCTION_GATE = FAIL for real jobs.
2. **Approver** → `apex-one auth add-approver "<your name>"` (token shown once); approve with
   `APEX_APPROVER_TOKEN=<token> apex-one approve <job>`. Verify the ledger: `apex-one auth verify-ledger`.
3. **Network access** (environment settings → Network access → allowed domains), as needed:
   `huggingface.co` (+ its CDN) for specialist design weights and the full GraphicDesignBench dataset;
   `integrate.api.nvidia.com`, `api.groq.com`, `openrouter.ai`, `api.cloudflare.com` for free remote models;
   the official sites of the opportunity you want (e.g. `docs.linuxfoundation.org`, `www.berea.edu`).
4. **Real job J-2fe410878683 (CNCF LFX 2027 Term 1)**: confirm the single-source deadline if you agree it is
   right — `apex-one facts list J-2fe410878683` then `apex-one facts confirm J-2fe410878683 deadline.application
   --claim <id> --by "<name>"` — and supply the LF stipend/eligibility pages (saved, with sources.yaml) so the
   funding and eligibility facts can lock; then `apex-one resume J-2fe410878683`.
5. **Optional**: a Gemini API key (free tier) to calibrate a remote vision judge; licence reviews for Gemma /
   Nemotron / gpt-oss usage policy (`apex-one license verify ... --by <name>`).

## System work

6. Let `scripts/validation_queue.py` finish (resumable: re-run the same command after any restart), then
   `apex-one reports`, update CURRENT_STATE.json, commit `docs/evidence/`.
7. If a vision judge passes calibration (≥ 4/5): re-run golden ULTRA so the Vision Council and pairwise finalists
   run for real; record council-vs-DOM disagreements. If none passes: Vision Quality stays NOT_MEASURED.
8. Compare model-written pages vs native (`page_compare.remeasure`) once all LLM page rows exist; keep native
   unless a model wins without safety losses.
