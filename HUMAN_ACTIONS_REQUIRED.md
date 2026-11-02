# Human actions required

_Generated 2026-11-02 13:12 UTC by `apex-one reports` at commit `9b7b854` from measured artifacts._

Only what a person must do. Everything Claude can still do autonomously is in NEXT_ACTIONS.md. Generated from `config/production_blockers.yaml`; an action disappears when its probe sees it done.

## A. Create a Gemini free-tier API key  (`GEMINI-KEY-MISSING`, MEDIUM)

**WHY** — No local model is a robust visual judge (Qwen3-VL 8B is canonical-640-only; larger local judges do not fit 16 GB). Gemini is the only reachable free route left to test. It may still fail calibration.

**WHAT EXACTLY IS NEEDED** — (1) A free-tier key from Google AI Studio in a project with NO billing account, stored as the environment secret GEMINI_API_KEY (environment settings → secrets). (2) Your attestation that it is free-tier with billing disabled — the $0 firewall refuses every remote route without one: apex-one providers attest gemini --by "<your name>" --note "AI Studio key, no billing".

**COMMAND AVAILABLE AFTERWARD** — `apex-one vision validate-gemini  (exit 0 = completed with a verdict, 2 = still blocked, 3 = infrastructure error; re-run resumes)`

_Done when:_ GEMINI_API_KEY present, a free_tier_no_billing attestation recorded, AND `apex-one vision validate-gemini` passes its live test (the calibration outcome itself may be UNQUALIFIED — that still unblocks)

## B. Supply the official APEX brand package  (`BRAND-ASSETS-MISSING`, CRITICAL)

**WHY** — Real guides cannot become release candidates with placeholder branding (Brand Production Gate FAIL), and placeholders are never embedded in FINAL artifacts.

**WHAT EXACTLY IS NEEDED** — A folder with logo.svg, logo-on-dark.svg, robot.svg (vector SVG, viewBox, no raster, palette colours only), the font files, and brand.yaml declaring approved_by, approved_at, palette {name: '#RRGGBB'}, fonts {role: family}, font_files {family: file}, font_licences {family: licence}, usage {min_logo_width_px, clear_space_ratio, allowed_backgrounds} and checksums {file: sha256}. Contract: config/asset_contract.yaml.

**COMMAND AVAILABLE AFTERWARD** — `apex-one brand import <folder>  →  apex-one brand validate (VALID)`

_Done when:_ `apex-one brand validate` prints VALID (every required asset present, vector, on-palette, not a placeholder, checksums match, fingerprint recorded)

## C. Create (or name) the authorised release approver  (`APPROVER-MISSING`, CRITICAL)

**WHY** — Approval identity comes only from an authenticated token; a typed name is never accepted. Without an approver no guide can reach FINAL.

**WHAT EXACTLY IS NEEDED** — The full name of the person who may approve releases, who then runs the command below themselves and stores the token (shown once) in a password manager.

**COMMAND AVAILABLE AFTERWARD** — `APEX_APPROVER_TOKEN=<token> apex-one approve <job_id> --artifact-sha256 <sha of final.pdf>`

_Done when:_ `apex-one auth list` shows at least one active release_approver AND `apex-one auth verify-ledger` reports the ledger intact

## D. Provide authoritative opportunity evidence  (`REAL-OPPORTUNITY-UNVALIDATED`, CRITICAL)

**WHY** — The guide's critical facts (deadline, eligibility, funding) must come from official sources; this container cannot reach them.

**WHAT EXACTLY IS NEEDED** — For ONE opportunity: the official pages saved as HTML/PDF (deadline, eligibility, funding/stipend pages), their URLs, and — for any fact that only one source states — your written confirmation (name + date). Put them in an evidence pack (layout: `apex-one evidence init <dir>` creates it).

**COMMAND AVAILABLE AFTERWARD** — `apex-one evidence run <pack-dir>  (source extraction → Fact Lock → validations → guide → QA → release candidate)`

_Done when:_ a non-synthetic job built from an evidence pack (`apex-one evidence run <pack>`) reaches RELEASE_CANDIDATE with every critical fact locked from ≥ 2 sources or human-confirmed

## E. Decide the pending model licences  (`LICENCE-VERIFICATION-PENDING`, MEDIUM)

**WHY** — Gemma 3 4B is the only local model that clears the Egyptian-Arabic guide floor, and it cannot be deployed while its licence is unverified. The others only add fallbacks.

**WHAT EXACTLY IS NEEDED** — A yes/no per model (Gemma 3 4B, Gemma 3 12B, Nemotron 3 Nano 4B, gpt-oss 20B) after reading the licence evidence prepared in docs/evidence/licence_review_pack.md — by a person entitled to make that call.

**COMMAND AVAILABLE AFTERWARD** — `apex-one license verify <licence-id> --license "<licence name>" --state PRODUCTION_ALLOWED --source <URL of the licence text you read> --by "<name>"  (or --state BLOCKED)`

_Done when:_ each pending licence (lic-gemma, lic-gemma3-12b, lic-nvidia-nemotron-nano, lic-gpt-oss) recorded by a named human with `apex-one license verify` as PRODUCTION_ALLOWED or BLOCKED (BLOCKED also resolves the blocker: the decision is what is missing)

## F. Allow the free-provider hosts (optional)  (`REMOTE-PROVIDERS-EGRESS-DENIED`, MEDIUM)

**WHY** — Remote free models are a capacity and vision-judge fallback; every one is denied by the egress policy today.

**WHAT EXACTLY IS NEEDED** — Environment settings → Network access → allowed domains: integrate.api.nvidia.com, api.groq.com, openrouter.ai, api.cloudflare.com, huggingface.co (and its CDN). Plus any provider key the provider requires (free tier only).

**COMMAND AVAILABLE AFTERWARD** — `apex-one providers live-test`

_Done when:_ at least one remote $0 provider LIVE_TESTED by `apex-one providers live-test` with a correct structured answer

