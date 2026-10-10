"""Phase 21 — APEX Design Genome extraction from APPROVED documents (ALA, TGS, FLEX, Berea, ...).

Input: PDF, HTML (APEX `section.page` documents or any HTML), or page screenshots (PNG/JPG).
Output (never a copy of any page — only measured PRINCIPLES):
  APEXPageSignature   per-page measurements (tone, ink, margins, columns, type hierarchy, palette, hero, footer)
  APEXLayoutEmbedding normalised numeric vector per page (for similarity / anti-copy)
  APEXDesignPrinciple aggregated statistics with evidence counts (e.g. "median outer margin 16 mm")
  APEXApprovedPattern / APEXRejectedPattern  occupancy-grid patterns stored in DesignMemory with a verdict

LayerD / ScreenCoder would add layer-level decomposition; they are not runnable here (see
config/design_activation.yaml), so extraction uses PyMuPDF text geometry + pixel analysis + Chromium DOM.
Proposed genome changes go through ONE Lab (never applied automatically).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from apex_one.core.schemas.common import ApexModel, new_id, stable_hash

MM_PER_PT = 25.4 / 72


class APEXPageSignature(ApexModel):
    source: str
    page: int
    tone: str                       # dark | light | silver
    luminance: float
    ink: float
    margins_mm: dict[str, float]
    columns: int
    font_sizes_pt: list[float] = []
    hierarchy_ratio: float | None = None     # largest / median text size
    hero_present: bool = False
    palette: list[str] = []
    footer_band: bool = False
    occupancy: list[int] = []


class APEXLayoutEmbedding(ApexModel):
    source: str
    page: int
    vector: list[float]


class APEXDesignPrinciple(ApexModel):
    principle_id: str
    name: str
    statement: str
    value: Any
    evidence_pages: int
    sources: list[str]


class APEXPattern(ApexModel):
    pattern_id: str
    verdict: str                    # approved | rejected
    grid: list[int]
    tone: str
    source: str
    reason: str = ""


def _palette(im: Image.Image, k: int = 6) -> list[str]:
    small = im.convert("RGB").resize((96, 136))
    q = small.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: 3 * k]
    counts = sorted(q.getcolors(), reverse=True)
    return [f"#{pal[3 * i]:02X}{pal[3 * i + 1]:02X}{pal[3 * i + 2]:02X}" for _, i in counts[:k]]


def _pixel_analysis(im: Image.Image, page_w_mm: float = 210.0) -> dict[str, Any]:
    g = np.asarray(im.convert("L").resize((420, 594)), dtype=np.float32)
    lum = float(g.mean() / 255)
    bg = float(np.median(np.concatenate([g[:4].ravel(), g[-4:].ravel(), g[:, :4].ravel(), g[:, -4:].ravel()])))
    ink_mask = np.abs(g - bg) > 40
    ink = float(ink_mask.mean())
    rows, cols = np.where(ink_mask)
    mm = page_w_mm / 420
    if len(rows):
        margins = {"top": rows.min() * mm, "bottom": (593 - rows.max()) * mm, "left": cols.min() * mm,
                   "right": (419 - cols.max()) * mm}
    else:
        margins = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
    # column estimate: vertical gutters inside the content box (columns of near-zero ink)
    columns = 1
    if len(cols):
        prof = ink_mask[rows.min():rows.max() + 1, cols.min():cols.max() + 1].mean(axis=0)
        gutter = prof < 0.004
        runs, cur = 0, 0
        for v in gutter:
            cur = cur + 1 if v else 0
            if cur == 8:
                runs += 1
        columns = min(4, 1 + runs)
    # footer band: ink concentrated in bottom 6%
    footer = bool(ink_mask[int(594 * 0.93):].mean() > 0.002 and ink_mask[int(594 * 0.86):int(594 * 0.93)].mean() < 0.01)
    bg_lum = bg / 255          # tone is the PAGE (background) colour, not the mean, which ink density skews
    tone = "dark" if bg_lum < 0.35 else "silver" if bg_lum < 0.9 else "light"
    grid = []
    for gy in range(16):
        for gx in range(12):
            cell = ink_mask[gy * 594 // 16:(gy + 1) * 594 // 16, gx * 420 // 12:(gx + 1) * 420 // 12]
            grid.append(int(cell.mean() > 0.02))
    return {"luminance": round(lum, 4), "ink": round(ink, 4), "margins_mm": {k: round(v, 1) for k, v in margins.items()},
            "columns": columns, "tone": tone, "footer_band": footer, "occupancy": grid}


def _pdf_pages(path: Path, dpi: int = 72) -> list[tuple[Image.Image, list[float]]]:
    import pymupdf

    out = []
    doc = pymupdf.open(str(path))
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        sizes = [round(s["size"], 1) for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])
                 for s in l.get("spans", []) if s.get("text", "").strip()]
        out.append((im, sizes))
    doc.close()
    return out


def _html_pages(path: Path) -> list[tuple[Image.Image, list[float]]]:
    from apex_one.vision.render import Renderer

    tmp = path.parent / f".extract-{path.stem}"
    with Renderer() as r:
        res = r.measure(path, screenshot_dir=tmp, screenshot_prefix="p")
    pages = res.metrics.get("pages", [])
    out = []
    for i, shot in enumerate(res.page_screenshots):
        sizes = [it["maxFontPx"] * 0.75 for it in pages[i]["items"]] if i < len(pages) else []
        out.append((Image.open(shot).copy(), sizes))
    return out


def extract(paths: list[Path]) -> tuple[list[APEXPageSignature], list[APEXLayoutEmbedding]]:
    sigs, embs = [], []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages = _pdf_pages(path)
        elif suffix in (".html", ".htm"):
            pages = _html_pages(path)
        elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
            pages = [(Image.open(path).copy(), [])]
        else:
            continue
        for i, (im, sizes) in enumerate(pages, 1):
            pa = _pixel_analysis(im)
            med = statistics.median(sizes) if sizes else None
            hier = round(max(sizes) / med, 2) if sizes and med else None
            sig = APEXPageSignature(source=path.name, page=i, tone=pa["tone"], luminance=pa["luminance"], ink=pa["ink"],
                                    margins_mm=pa["margins_mm"], columns=pa["columns"], font_sizes_pt=sorted(set(sizes))[-8:],
                                    hierarchy_ratio=hier, hero_present=bool(hier and hier >= 4.0), palette=_palette(im),
                                    footer_band=pa["footer_band"], occupancy=pa["occupancy"])
            sigs.append(sig)
            m = pa["margins_mm"]
            embs.append(APEXLayoutEmbedding(source=path.name, page=i, vector=[
                pa["luminance"], pa["ink"] * 10, m["top"] / 40, m["bottom"] / 40, m["left"] / 40, m["right"] / 40,
                pa["columns"] / 4, (hier or 1) / 8, float(bool(hier and hier >= 4)), float(pa["footer_band"]),
                *[float(x) for x in pa["occupancy"]]]))
    return sigs, embs


def derive_principles(sigs: list[APEXPageSignature]) -> list[APEXDesignPrinciple]:
    if not sigs:
        return []
    srcs = sorted({s.source for s in sigs})
    n = len(sigs)

    def P(name: str, statement: str, value: Any) -> APEXDesignPrinciple:
        return APEXDesignPrinciple(principle_id=new_id("PR"), name=name, statement=statement, value=value,
                                   evidence_pages=n, sources=srcs)

    tones = Counter(s.tone for s in sigs)
    outer = [statistics.median([s.margins_mm["left"], s.margins_mm["right"]]) for s in sigs]
    hier = [s.hierarchy_ratio for s in sigs if s.hierarchy_ratio]
    cols = Counter(s.columns for s in sigs)
    pal = Counter(c for s in sigs for c in s.palette[:3])
    seq = [s.tone for s in sigs]
    max_dark_run = max((len(run) for run in "".join("D" if t == "dark" else "." for t in seq).split(".")), default=0)
    out = [
        P("tone_distribution", "share of dark / silver / light pages in approved documents",
          {k: round(v / n, 3) for k, v in tones.items()}),
        P("max_consecutive_dark", "longest run of consecutive dark pages", max_dark_run),
        P("outer_margin_mm", "median outer (left/right) margin", round(statistics.median(outer), 1)),
        P("column_usage", "distribution of detected column counts", dict(cols)),
        P("hero_frequency", "share of pages with a hero element (largest type >= 4x median)",
          round(sum(s.hero_present for s in sigs) / n, 3)),
        P("footer_signature", "share of pages carrying a bottom footer band", round(sum(s.footer_band for s in sigs) / n, 3)),
        P("dominant_colours", "most frequent page colours (first three per page)", [c for c, _ in pal.most_common(8)]),
        P("ink_density", "median ink density (visual weight) per page", round(statistics.median(s.ink for s in sigs), 4)),
    ]
    if hier:
        out.append(P("type_hierarchy_ratio", "median ratio of largest to median text size",
                     round(statistics.median(hier), 2)))
    return out


def ingest(paths: list[Path], verdict: str, out_dir: Path, db_url: str | None = None, reason: str = "") -> dict[str, Any]:
    """Ingest approved (or rejected) documents; store signatures, principles and patterns. Returns a summary."""
    from apex_one.memory import DesignMemory
    from apex_one.persistence.db import init_db

    init_db(db_url)
    sigs, embs = extract(paths)
    principles = derive_principles(sigs) if verdict == "approved" else []
    patterns = [APEXPattern(pattern_id=stable_hash([s.source, s.page, s.occupancy])[:16], verdict=verdict,
                            grid=s.occupancy, tone=s.tone, source=f"{s.source}#p{s.page}", reason=reason) for s in sigs]
    mem = DesignMemory(db_url)
    for p in patterns:
        mem.add(f"pattern:{p.pattern_id}", p.source, {"occupancy": p.grid, "tone": p.tone, "reason": reason,
                                                      "kind": "ingested-pattern"}, verdict=verdict)
    out_dir.mkdir(parents=True, exist_ok=True)
    run = {"verdict": verdict, "documents": [p.name for p in paths], "pages": len(sigs),
           "signatures": [s.model_dump() for s in sigs], "embeddings": [e.model_dump() for e in embs],
           "principles": [p.model_dump() for p in principles], "patterns": [p.model_dump() for p in patterns],
           "note": "principles are statistics; no page content or layout is copied into generation"}
    path = out_dir / f"genome_extraction_{verdict}_{stable_hash(run['documents'])[:8]}.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"path": str(path), "pages": len(sigs), "principles": len(principles), "patterns": len(patterns)}
