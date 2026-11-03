# Real opportunity pilot (template)

One real opportunity, end to end, from authoritative evidence to an approved FINAL guide. No live network access is
needed during the run: everything comes from the files you save.

This template is not tied to a specific opportunity. Replace `<pack>` with a folder name, for example
`packs/<programme>-<cycle>`.

Prerequisites:
- `apex-one brand validate` prints VALID (BRAND_PACKAGE_INTAKE.md).
- An approver exists (APPROVER_SETUP.md).

## 1. Save authoritative sources

Open the opportunity's **official** pages in a browser and save each one: *Save page as → Web page, HTML only*, or
download the official PDF. Take at least:
- the **deadline** page;
- the **eligibility** page;
- the **funding / stipend / costs** page;
- the **application** page or handbook, if separate.

For every critical fact, try to have **two** official sources. A fact stated by only one source will need your
written confirmation in step 5. Do not save blogs, forums or aggregator sites as evidence.

## 2. Initialise the evidence pack

```
apex-one evidence init <pack>
```

This creates three templates. Fill them in:
- `pack.yaml`: the opportunity name and cycle, `prepared_by`, `prepared_at`.
- `sources.yaml`: one entry per saved file, with the **https URL it was saved from**:
  ```yaml
  sources:
    - url: https://<official domain>/<page>
      file: deadlines.html
      cycle_year: 2027
  ```
- `confirmations.yaml`: leave empty for now (step 5).

Copy the saved files into `<pack>`.

## 3. Validate the evidence pack

```
apex-one evidence check <pack>
```

Fix every listed problem: missing file, wrong type (only .html/.htm/.pdf), an empty file, a missing URL, or a
duplicate. A pack that uses test domains (`.invalid`, `.test`, `example.com`, ...) is reported as a TEST PACK. It
never counts as a real opportunity.

## 4–8. Extract facts, Fact Lock, build the guide, deterministic QA

```
apex-one evidence run <pack> --quality ultra
```

One command runs:
- source extraction;
- Fact Lock, with deadline, eligibility and funding validation;
- citation and evidence mapping;
- guide generation;
- deterministic QA.

It prints the job id, the state, the blockers and a per-stage summary. Use `--quality standard` for a faster draft
while preparing the pack.

## 5. Resolve required human confirmations

If the run reports `needs_human` slots, list the facts and the competing claims:

```
apex-one facts list <job_id>
```

For each slot, add a confirmation to `<pack>/confirmations.yaml`. The value must be written exactly as printed in the
official source:

```yaml
confirmations:
  - slot: deadline.application
    value: "16 February 2027"
    by: "<your full name>"
    at: "<YYYY-MM-DD>"
    note: "checked on <official page> on <date>"
```

Then run `apex-one evidence run <pack>` again. A confirmation locks a fact **only if** an extracted source states
that value. APEX never invents a value from a confirmation. Alternatively, confirm one claim directly and resume:

```
apex-one facts confirm <job_id> <slot> --claim <claim_id> --by "<your full name>"
apex-one resume <job_id>
```

## 8. Inspect QA

```
apex-one inspect <job_id>
```

Every quality gate must PASS. Read `final.pdf` in the job folder (the path is printed above) yourself.

## 9. Brand validation

```
apex-one brand validate          # must print VALID; a real job cannot reach release candidate otherwise
```

## 10. Release candidate

The job reaches `RELEASE_CANDIDATE` when every gate passes. Its pause message prints the `final.pdf` SHA-256 and the
exact approve command.

## 11. Authenticated human approval

```
sha256sum <job folder>/final.pdf
APEX_APPROVER_TOKEN=<token> apex-one approve <job_id> --artifact-sha256 <sha256> --notes "<comment>"
```

To send it back instead: `APEX_APPROVER_TOKEN=<token> apex-one reject <job_id> --notes "<what to fix>"`.

## 12. FINAL

```
apex-one release verify <job_id>       # FINAL bytes = approved bytes; ledger intact
apex-one release export <job_id>       # artifacts/exports/<job>-FINAL.zip + .sha256 + .approval.json (refused unless FINAL)
apex-one release check                 # REAL_OPPORTUNITY_VALIDATED is now satisfied
```
