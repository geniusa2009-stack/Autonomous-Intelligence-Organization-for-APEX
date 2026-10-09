"""Whole-document art direction: contact sheet + rhythm analysis."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.quality import QAIssue
from apex_one.vision.page import dhash, hamming_similarity, ink_stats


def contact_sheet(pngs: list[Path], out: Path, cols: int = 5, scale: float = 0.3) -> Path:
    ims = [Image.open(p).convert("RGB") for p in pngs]
    w, h = ims[0].size
    tw, th = int(w * scale), int(h * scale)
    rows = (len(ims) + cols - 1) // cols
    pad = 14
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad + 14) + pad), (213, 219, 227))
    d = ImageDraw.Draw(sheet)
    for k, im in enumerate(ims):
        x, y = pad + (k % cols) * (tw + pad), pad + (k // cols) * (th + pad + 14)
        sheet.paste(im.resize((tw, th)), (x, y))
        d.text((x, y + th + 2), f"{k + 1:02d}", fill=(10, 26, 51))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def rhythm_analysis(pngs: list[Path], archetypes: list[str], rhythm_roles: list[str], signatures: list[str]
                    ) -> tuple[list[QAIssue], dict[str, Metric], dict]:
    stats = [ink_stats(p) for p in pngs]
    hashes = [dhash(p) for p in pngs]
    lum = [s[0] for s in stats]
    ink = [s[1] for s in stats]
    issues: list[QAIssue] = []
    penalty = 0.0
    dark = [v < 0.35 for v in lum]
    for k in range(2, len(dark)):
        if dark[k] == dark[k - 1] == dark[k - 2] and dark[k]:
            issues.append(QAIssue(check="doc.dark_light_distribution", severity="major",
                                  message=f"three dark pages in a row ending at page {k + 1}"))
            penalty += 8
    for k in range(1, len(archetypes)):
        if archetypes[k] == archetypes[k - 1]:
            issues.append(QAIssue(check="doc.page_repetition", severity="major",
                                  message=f"pages {k} and {k + 1} share archetype {archetypes[k]}"))
            penalty += 6
        sim = hamming_similarity(hashes[k], hashes[k - 1])
        if sim > 0.92:
            issues.append(QAIssue(check="doc.page_repetition", severity="major",
                                  message=f"pages {k} and {k + 1} look near-identical (dHash {sim:.2f})"))
            penalty += 8
    dup_sigs = len(signatures) - len(set(signatures))
    if dup_sigs:
        issues.append(QAIssue(check="doc.page_repetition", severity="minor", message=f"{dup_sigs} repeated page structures"))
        penalty += 3 * dup_sigs
    heroes = sum(1 for a in archetypes if a in ("hero-number", "cover-monument", "manifesto"))
    if heroes > max(3, len(archetypes) // 3):
        issues.append(QAIssue(check="doc.hero_frequency", severity="major", message=f"{heroes} loud pages; hero fatigue"))
        penalty += 10
    # density contrast between consecutive pages (rhythm needs variation)
    flat = sum(1 for k in range(1, len(ink)) if abs(ink[k] - ink[k - 1]) < 0.01 and archetypes[k] != "cover-monument")
    penalty += 2 * flat
    distinct = len(set(archetypes)) / max(1, len(archetypes))
    novelty = 100 * min(1.0, distinct * 1.6) - 3 * dup_sigs
    data = {"luminance": lum, "ink": ink, "archetypes": archetypes, "rhythm_roles": rhythm_roles}
    return issues, {
        "document.rhythm": Metric.measured("document.rhythm", max(0.0, 100 - penalty),
                                           "contact-sheet analysis: dark/light runs, adjacent repetition (archetype + "
                                           "dHash), hero frequency, density variation"),
        "design.novelty": Metric.measured("design.novelty", max(0.0, min(100.0, novelty)),
                                          "within-document structural diversity (archetype + signature uniqueness)"),
    }, data
