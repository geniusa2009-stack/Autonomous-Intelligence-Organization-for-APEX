# APEX production assets

Place the ORIGINAL APEX brand assets here. Until every required asset validates, the **Brand Production Gate**
fails for real (non-synthetic) jobs, so no guide with placeholder branding can become a release candidate.

| File | Required | Contract |
|---|---|---|
| `logo.svg` | yes | vector SVG with viewBox; no embedded raster; colours within the APEX palette; not the placeholder |
| `logo-on-dark.svg` | yes | same, light variant for navy pages |
| `robot.svg` | yes | vector SVG robot signature; viewBox; palette colours (or `currentColor`) |
| `watermark.svg` | optional | vector; used at ≤ 6% opacity |
| `brand.yaml` | yes | `approved_by`, `approved_at`, palette hex values confirmed by APEX, font licences |

Validate with `apex-one assets validate`.
