# SECURITY & PRIVACY

* Secrets come only from the environment / `.env` (git-ignored). `.env.example` contains no values.
* `apex_one.core.security.redact` scrubs env secret values and key-shaped strings (nvapi-, gsk_, sk-, sk-or-,
  AIza, hf_, gh*_, Bearer) from every artifact and event written by `JobWorkspace`.
* Release runs `secret_scan` over all job artifacts; a hit blocks the release candidate.
* API responses never include keys; provider status shows only whether the env var is set.
* Artifact downloads are path-confined to the job directory (traversal returns 404).
* Privacy classes: `public`, `internal`, `private-student-data`. MissionAnalyzer flags phone numbers, e-mails,
  national IDs and personal grades as private; the firewall then allows only providers with
  `private_student_data_allowed` (local by default).
* Research fetcher identifies itself (`APEX_RESEARCH_USER_AGENT`) and respects robots.txt.
* No account creation, rotation or quota evasion is implemented anywhere.
