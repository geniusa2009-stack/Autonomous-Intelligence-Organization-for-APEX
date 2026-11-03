# First production runbook

Follow these steps in order. Every command runs from the APEX folder after `source .venv/bin/activate`.

**At any time:** `apex-one release check` says what is still missing. When it prints **READY**, production is
accepted (PRODUCTION_ACCEPTANCE.md).

---

## Step 1 — Install and validate the brand

1. Assemble the folder exactly as described in **BRAND_PACKAGE_INTAKE.md**.
2. Generate the checksums and paste them into `manifest.yaml`:
   ```
   apex-one brand checksums brand/
   ```
3. Run:
   ```
   apex-one brand import brand/ --dry-run      # fix everything it lists
   apex-one brand import brand/
   apex-one brand validate                     # must print VALID
   ```

## Step 2 — Configure the approver

```
apex-one auth add-approver "<full name>"       # copy the token into a password manager NOW (shown once)
apex-one auth list                             # the approver appears; tokens are never shown
apex-one auth verify-ledger                    # "ledger OK"
```

Details, rotation and revocation: **APPROVER_SETUP.md**.

## Step 3 — Create the real evidence pack

```
apex-one evidence init packs/<programme>-<cycle>
```

Save the official pages and PDFs into that folder, and fill in `pack.yaml` and `sources.yaml` (see
**REAL_OPPORTUNITY_PILOT.md**, steps 1–2). Then:

```
apex-one evidence check packs/<programme>-<cycle>      # must say "ready": true
```

## Step 4 — Run the pipeline

Start the production text model. It is refused with a reason if memory is not safe:

```
apex-one local status                          # nothing else large should be running
apex-one local serve qwen3-vl-4b-q4kxl
```

Run the guide:

```
apex-one evidence run packs/<programme>-<cycle> --quality ultra
```

The output names the job (`J-…`). If it lists `needs_human` facts, confirm them as described in
REAL_OPPORTUNITY_PILOT.md step 5 and run the same command again.

## Step 5 — Inspect QA

```
apex-one inspect <job_id>
```

- Every gate must be **PASS**.
- Open `final.pdf` in the job folder (the path is printed) and read it fully: facts, dates, Arabic, layout.
- Visual quality is marked NOT_MEASURED on purpose. Your review is the visual check.

## Step 6 — Approve the artifact

```
sha256sum <job folder>/final.pdf
APEX_APPROVER_TOKEN=<token> apex-one approve <job_id> --artifact-sha256 <sha256> --notes "<comment>"
```

If something is wrong, send it back instead:
`APEX_APPROVER_TOKEN=<token> apex-one reject <job_id> --notes "<what to fix>"`.

## Step 7 — Export FINAL

```
apex-one release export <job_id>
```

This writes three files to `artifacts/exports/`:
- `<job_id>-FINAL.zip`: the release;
- `<job_id>-FINAL.zip.sha256`: its checksum;
- `<job_id>-FINAL.zip.approval.json`: who approved which `final.pdf` hash, and when.

Export is refused unless the job is FINAL and still matches its approval.

## Step 8 — Verify the release hash

```
apex-one release verify <job_id>                       # "verified": true
(cd artifacts/exports && sha256sum -c <job_id>-FINAL.zip.sha256)   # "<job_id>-FINAL.zip: OK"
apex-one auth history --job <job_id>                   # who approved what, when, with which hash
apex-one release check                                 # READY once steps 1–8 are done
```

When you are done, stop the model: `apex-one local stop qwen3-vl-4b-q4kxl`.

---

## Recovery

| problem | what you see | what to do |
|---|---|---|
| **Model server crash** | a stage logs `MODEL_SERVER_CRASH` / `call_failed`, or the job pauses | The supervisor restarts the server automatically (up to 3 times, with backoff) and retries the call once. If the job paused: `apex-one local status`, then `apex-one local serve qwen3-vl-4b-q4kxl` if it is not running, then `apex-one resume <job_id>`. A crash is recorded as an infrastructure error, never as a quality score. |
| **Render failure** | the job stops at RENDER or DETERMINISTIC_QA with a render error | `apex-one resume <job_id>`. If it repeats, close other heavy programs, then resume again. A partial page is never released: QA blocks it. |
| **Insufficient memory** | `RESOURCE_BLOCKED` or `DEFER` with a reason (headroom below the required amount) | This is a safe refusal, not a crash. Stop other models (`apex-one local status`, `apex-one local stop <key>`), close other programs, and retry. Never lower the memory rules to make it start. |
| **Evidence validation failure** | `apex-one evidence check` lists problems, or the run reports `NO LOCK` / `needs_human` | Fix each listed file or URL. For a fact with a single source, save a second official source or add a written confirmation (REAL_OPPORTUNITY_PILOT.md step 5), then run `apex-one evidence run` again. |
| **Approval mismatch** | `Refused: artifact mismatch`, or `FINAL refused: final.pdf changed after approval` | The PDF is not the one you reviewed. Do not force it. Re-open the current `final.pdf`, review it again, recompute `sha256sum`, and approve again. If it changed after approval, find out why before approving the new bytes. `apex-one auth history --job <job_id>` shows what was approved. |
