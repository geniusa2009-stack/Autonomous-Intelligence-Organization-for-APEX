# QUICKSTART (Mac-friendly)

## 1. Install
```bash
git clone <repo> && cd Autonomous-Intelligence-Organization-for-APEX
./scripts/bootstrap.sh            # creates .venv, installs apex-one, installs/locates Chromium, migrates DB
source .venv/bin/activate
apex-one doctor                   # machine, $0 policy, Chromium, DB, providers, local-model plan
```
Requirements: Python 3.12+, ~1 GB disk. macOS (Apple Silicon or Intel) and Linux are supported.
Nothing large is downloaded automatically; `doctor` only *recommends* local models.

## 2. Run the offline golden benchmark (no network, no keys)
```bash
apex-one benchmark --suite golden --quality ultra
```
It researches a **synthetic** corpus (fictional "Example Labor College", reserved `.invalid` domains), resolves
planted contradictions (stale cycle, wrong blog values, forum rumour), locks facts, writes the guide, evolves
layouts, renders, QA's, and stops at `RELEASE_CANDIDATE`. Artifacts: `artifacts/jobs/<JOB_ID>/`.

## 3. Your first real ultra-quality job
Pick ONE research route:

**A. Saved official sources (works offline):** save the official pages/PDFs into a folder and describe them:
```yaml
# ~/berea-sources/sources.yaml
sources:
  - {url: "https://www.berea.edu/admissions/international", file: intl.html, kind: official, cycle_year: 2027}
  - {url: "https://www.berea.edu/.../guide.pdf", file: guide.pdf, kind: official_document, cycle_year: 2027}
```
```bash
apex-one create-guide --opportunity "Berea College Fall 2027" --quality ultra --budget 0 --sources ~/berea-sources
```

**B. Live search:** run SearXNG (`docker compose --profile research up -d searxng`), set `SEARXNG_URL=http://localhost:8888`
in `.env`, then:
```bash
apex-one create-guide --opportunity "Berea College Fall 2027" --quality ultra --budget 0
```

## 4. Human steps
```bash
apex-one inspect J-xxxx                 # gates, warnings, artifacts
apex-one facts list J-xxxx              # locked facts / claims needing a human
apex-one facts confirm J-xxxx deadline.application --claim C-... --by "Your Name"   # resolve a conflict
apex-one resume J-xxxx
apex-one approve J-xxxx --by "Your Name"            # RELEASE_CANDIDATE -> FINAL (only a human can)
apex-one reject J-xxxx --by "Your Name" --notes "too generic" --target CREATIVE_DIRECTIONS
apex-one prefer J-xxxx --page N-... --ranking LC-b,LC-a,LC-c --reasons "less card-like,stronger hierarchy" --by "Your Name"
apex-one export J-xxxx
```

## 5. Optional $0 compute
* Local: `ollama pull gpt-oss:20b` (16 GB+ RAM) or `mlx_lm.server --model <repo> --port 8081` (Apple Silicon).
* Free tiers: put keys in `.env`, then attest the account has **no billing**:
  `apex-one providers attest groq --by "Your Name"`; verify model licences:
  `apex-one license verify lic-gpt-oss --license Apache-2.0 --state PRODUCTION_ALLOWED --source <url> --by "Your Name"`.
* API: `apex-one api` → http://127.0.0.1:8787/docs and http://127.0.0.1:8787/studio
