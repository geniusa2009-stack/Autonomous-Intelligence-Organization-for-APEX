# APEX brand package — intake specification

This is everything needed to hand APEX its official brand. You do not need to read any code. Assemble one folder
exactly as below, then run two commands. Production stays blocked until `apex-one brand validate` prints **VALID**.

Never send placeholder, sample or "temporary" artwork. The importer rejects the known placeholders, and a guide with
placeholder branding can never be released.

## 1. Folder structure

```
brand/
├── manifest.yaml            ← the description of the package (section 4)
├── usage_rules.md           ← how the brand may and may not be used, in plain words (section 5)
├── logo/
│   ├── logo.svg             ← REQUIRED: main logo, for light backgrounds
│   ├── logo-on-dark.svg     ← REQUIRED: light variant, for the navy pages
│   └── watermark.svg        ← optional: used at ≤ 6 % opacity
├── mascot/
│   └── robot.svg            ← REQUIRED: the APEX robot signature
└── fonts/
    ├── <font file per family>.woff2   (or .woff / .ttf / .otf)
    └── licences/
        └── <licence text per family>.txt   (or .pdf / .md — the licence text or the purchase receipt)
```

Rules for the folder:
- There is no `colors/` folder. The official colours are written once, in `manifest.yaml`, so there is a single source of truth.
- Every file in the folder must be named in `manifest.yaml`. A stray file, such as an old draft, is rejected.
  The exceptions are `README.md` and hidden files such as `.DS_Store`.
- No shortcuts or symbolic links, and no files outside the folder.

## 2. Logos and mascot

| | requirement | checked automatically |
|---|---|---|
| format | **SVG only** (vector). PNG/JPG are not accepted: the guide is printed and zoomed, and raster logos blur | yes |
| size | must declare a `viewBox`. Width and height must be > 0, and the longer side at most 12× the shorter | yes |
| content | no embedded images (PNG/JPEG inside the SVG), no `<script>` | yes |
| colours | only the colours listed in `palette` (section 4). Black and white are allowed only if listed there | yes |
| placeholders | must not be one of the known APEX placeholders | yes |
| transparency | `logo.svg` and `logo-on-dark.svg` have a **transparent background** (no full-page rectangle behind the mark). `logo-on-dark.svg` uses light colours that read on navy | **no** — the approver checks this by eye |
| smallest use | the smallest width the logo may be printed at goes in `usage.min_logo_width_px` | yes (must be > 0) |
| robot | `mascot/robot.svg`, same rules; it is placed as a small signature in page footers | yes |

## 3. Fonts

For **each** font family used, the package must contain all three of the following:
1. **The font file** in `fonts/`: `.woff2`, `.woff`, `.ttf` or `.otf`. A file whose first bytes are not a real font is rejected as corrupted.
2. **The licence name** in `manifest.yaml`, for example `OFL-1.1`, `Apache-2.0` or `commercial`. `unknown`, `none`, `tbd` and `proprietary` are rejected.
3. **Licence evidence** in `fonts/licences/`: the licence text shipped with the font, or the purchase receipt or licence certificate for a commercial font. It must be at least 200 bytes.

A font without all three is treated as unlicensed and rejected. Fonts are embedded in the PDF, so the font file itself is required; a font name alone is not enough.

## 4. `manifest.yaml`

Copy this, then replace every `<...>`:

```yaml
schema_version: 1
approved_by: "<full name of the person who approves this brand>"
approved_at: "<YYYY-MM-DD>"

palette:                       # the official colours, exactly #RRGGBB
  navy_900: "#0A1A33"
  white: "#FFFFFF"
  # <name>: "#RRGGBB"   (one line per official colour)

fonts:                         # role -> family name
  display: "<family name>"
  body: "<family name>"

font_files:                    # family name -> file inside the package
  "<family name>": fonts/<file>.woff2

font_licences:                 # family name -> licence name + evidence file
  "<family name>": {licence: OFL-1.1, evidence: fonts/licences/<file>.txt}

files:                         # optional: only if your file names differ from section 1
  logo: logo/logo.svg
  logo_on_dark: logo/logo-on-dark.svg
  robot: mascot/robot.svg
  # watermark: logo/watermark.svg

usage:
  min_logo_width_px: 96        # never print the logo narrower than this
  clear_space_ratio: 0.5       # empty margin around the logo, as a fraction of the logo height (0–1)
  allowed_backgrounds: [white, navy_900]    # palette names the logo may sit on

checksums:                     # generated for you — see step 6
```

## 5. `usage_rules.md`

Write the brand rules in plain words, at least a few sentences. Cover at least:
- **Allowed:** which logo goes on which background; the minimum size; the clear space.
- **Forbidden:** recolouring, stretching or squashing, rotating, adding shadows/glows/outlines, cropping, placing on busy photos, re-typesetting the wordmark, and using the robot as a decorative pattern.
- **Who to ask** when unsure.

APEX already applies the machine-readable part (`usage` in the manifest). This file is the human-readable record of the same rules.

## 6. Checksums

The checksums prove that the files that arrive are exactly the ones you approved: nothing corrupted in transit, nothing swapped. After everything else is in place, run:

```
apex-one brand checksums brand/
```

Paste its output (a `checksums:` block) at the end of `manifest.yaml`, replacing the empty `checksums:` line.

## 7. Import and validate

```
apex-one brand import brand/ --dry-run     # checks everything, installs nothing; lists every problem
apex-one brand import brand/               # installs only if every check passes
apex-one brand validate                    # VALID | INCOMPLETE | INVALID, with the exact reasons
```

The import:
- copies the files into a staging area;
- re-checks every checksum after the copy;
- swaps the staged copy in only when everything matches;
- leaves the previous assets untouched if anything fails;
- records a brand fingerprint.

Editing an installed file afterwards makes `brand validate` report INVALID until the package is imported again.

What each result means:
- **VALID**: production may use the brand.
- **INCOMPLETE**: nothing present is wrong, but a required file is missing. The reasons name it.
- **INVALID**: something present is wrong: a placeholder, a raster image, an off-palette colour, an unlicensed font, a corrupted file, a checksum mismatch, or a file edited after import. The reasons name it.
