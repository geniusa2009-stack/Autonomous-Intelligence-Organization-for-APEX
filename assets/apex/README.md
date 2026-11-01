# APEX production assets

Place the ORIGINAL APEX brand assets here. Until every required asset validates, the **Brand Production Gate**
fails for real (non-synthetic) jobs, so no guide with placeholder branding can become a release candidate.

| File | Required | Contract |
|---|---|---|
| `logo.svg` | yes | vector SVG with viewBox; no embedded raster; colours within the APEX palette; not the placeholder |
| `logo-on-dark.svg` | yes | same, light variant for navy pages |
| `robot.svg` | yes | vector SVG robot signature; viewBox; palette colours (or `currentColor`) |
| `watermark.svg` | optional | vector; used at ≤ 6% opacity |
| `brand.yaml` | yes | `approved_by`, `approved_at`, `palette` {name: '#RRGGBB'}, `fonts` {role: family}, `font_files` {family: file}, `font_licences` {family: licence}, `usage` {min_logo_width_px, clear_space_ratio, allowed_backgrounds}, `checksums` {logo, logo_on_dark, robot, font:&lt;family&gt;: sha256} |

Install with `apex-one brand import <folder>` (validates everything first; installs nothing on any problem).
Check with `apex-one brand validate` → **VALID** / **INCOMPLETE** (something missing) / **INVALID** (something
present is wrong: placeholder, raster, off-palette colour, bad manifest, checksum or fingerprint mismatch).
Release stays blocked until VALID. Placeholders are never embedded in a FINAL artifact.
