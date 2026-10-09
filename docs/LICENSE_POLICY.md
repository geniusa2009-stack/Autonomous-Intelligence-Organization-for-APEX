# LICENCE POLICY

States: `PRODUCTION_ALLOWED`, `RESEARCH_ONLY`, `NON_COMMERCIAL`, `UNKNOWN`, `BLOCKED`.

1. **Unknown ⇒ not production.** Every external model starts `UNKNOWN` unless a more restrictive state is known.
2. **Restrictions may come from reported knowledge; permissions require verification.** `reported_license` is
   informational; `PRODUCTION_ALLOWED` counts only with `verified_at` set (recorded via
   `apex-one license verify ...`, stored in `license_verifications`, overlaying the YAML).
3. Records hold: licence name, commercial use, research use, redistribution, derivative use, dataset constraints,
   provider constraints, verified_at/by, source reference.
4. **Research-only models stay usable in ONE Lab** (purpose `research`), but any output carries research-only
   provenance and the release **LicenseGuard** blocks a release whose output was touched by any engine that is not
   production-allowed (`license_report.json`, critical gate `license_contamination = 0`).
5. The deterministic mock is never production-eligible regardless of its licence record.
6. Fonts: IBM Plex Sans Arabic, Readex Pro, IBM Plex Mono — SIL OFL 1.1 (bundled, see `apex_one/assets/fonts/FONTS_LICENSE.md`).
7. Synthetic benchmark corpora are original and fictional (`.invalid` domains).

Build-time note: no licence could be verified online from the build container (Hugging Face, arXiv and GitHub
were blocked by the egress proxy). This is why every external model is currently production-blocked.
