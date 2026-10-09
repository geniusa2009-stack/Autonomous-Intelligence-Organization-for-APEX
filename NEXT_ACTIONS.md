# Next actions (ordered)

1. **Restore GitHub access and push** `claude/charming-archimedes-2guzc9` (connect GitHub / install the Claude GitHub App).
2. **Supply the original APEX logo** → `apex_one/assets/brand/`, set `is_placeholder: false` in `config/apex_brand.yaml`.
3. **First real job**: save Berea's official international-admissions + financial-aid pages/PDFs for the Fall 2027
   cycle with a `sources.yaml`, then
   `apex-one create-guide --opportunity "Berea College Fall 2027" --quality ultra --budget 0 --sources <dir>`
   (or run SearXNG: `docker compose --profile research up -d searxng` and set `SEARXNG_URL`).
4. **Enable $0 models** (optional, improves extraction/vision/language judging):
   * local: `ollama pull qwen2.5vl:7b` (vision judge) and `gpt-oss:20b` if RAM ≥ 16 GB;
   * free tiers: add keys, `apex-one providers attest <id> --by <name>`, `apex-one providers --probe`;
   * licences: `apex-one license verify <lic-id> ...` after reading each licence.
5. **Reader comprehension target (93.3 < 95)**: skim personas miss one item; consider moving the decision-critical
   warning onto the snapshot page for skimmers (editorial decision for a human).
6. **Rhythm target (92 < 93)**: tune the document-level tournament penalty weights through ONE Lab
   (`apex-one lab propose --weakness rhythm --overlay '{"tournament.weights": {...}}'`).
7. **Specialist design models**: serve PosterCopilot-7B / WebGenAgent / PosterReward on a GPU you control behind
   `APEX_DESIGN_ENDPOINT_*`, verify licences, run `apex-one benchmark --suite design` and a Lab experiment.
8. **PostgreSQL + pgvector**: `docker compose --profile db up -d postgres`; set `APEX_DATABASE_URL`; `apex-one db-upgrade`.
9. **Preference learning**: record human rankings from the studio (`/studio`) and train a CANDIDATE scorer
   (`apex-one lab train-preference --approved-by <name>`) once ≥ 30 pairs exist.
