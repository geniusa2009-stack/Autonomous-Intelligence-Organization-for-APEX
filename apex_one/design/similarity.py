"""Phase 22 — anti-copy / anti-repetition engine.

SAME DNA, DIFFERENT ORGANISM:
* BRAND_SIMILARITY  (want HIGH): palette compliance, brand fonts, APEX signature elements (logo/footer/robot).
* LAYOUT_SIMILARITY (want CONTROLLED): geometry of where content sits — a coarse occupancy grid of the rendered
  text blocks (IoU), the structural signature, and (when screenshots exist) a perceptual hash.

The two are computed from different features so that a page can be maximally "APEX" while still being a new
composition. Thresholds: layout similarity >= MUTATE_AT asks for mutation, >= REJECT_AT rejects the candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apex_one.qa.colors import nearest_palette_distance

GRID_W, GRID_H = 12, 16
MUTATE_AT = 0.85
REJECT_AT = 0.93


def occupancy_grid(page: dict[str, Any]) -> list[int]:
    """12x16 grid; a cell is 1 if any rendered text block covers >= 25% of it."""
    W, H = page["w"], page["h"]
    cw, ch = W / GRID_W, H / GRID_H
    cells = [0] * (GRID_W * GRID_H)
    for it in page.get("items", []):
        if it["w"] <= 0 or it["h"] <= 0:
            continue
        x0, y0, x1, y1 = it["x"], it["y"], it["x"] + it["w"], it["y"] + it["h"]
        for gy in range(int(max(0, y0 // ch)), int(min(GRID_H - 1, y1 // ch)) + 1):
            for gx in range(int(max(0, x0 // cw)), int(min(GRID_W - 1, x1 // cw)) + 1):
                ix = min(x1, (gx + 1) * cw) - max(x0, gx * cw)
                iy = min(y1, (gy + 1) * ch) - max(y0, gy * ch)
                if ix > 0 and iy > 0 and ix * iy >= 0.25 * cw * ch:
                    cells[gy * GRID_W + gx] = 1
    return cells


def grid_iou(a: list[int], b: list[int]) -> float:
    inter = sum(1 for x, y in zip(a, b) if x and y)
    union = sum(1 for x, y in zip(a, b) if x or y)
    return inter / union if union else 1.0


def layout_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    """a/b: {'grid': [...], 'signature': str, 'dhash': int|None}"""
    s = grid_iou(a["grid"], b["grid"])
    if a.get("signature") and a.get("signature") == b.get("signature"):
        s = max(s, 0.9)
    if a.get("dhash") is not None and b.get("dhash") is not None:
        from apex_one.vision.page import hamming_similarity

        s = 0.7 * s + 0.3 * hamming_similarity(a["dhash"], b["dhash"])
    return round(s, 4)


def brand_similarity(page: dict[str, Any], invariants: dict[str, Any], fonts_loaded: list[str]) -> float:
    palette = list(invariants["palette"].values())
    colors = page.get("colors", [])
    on_palette = sum(1 for c in colors if nearest_palette_distance(c, palette) <= 8) / max(1, len(colors))
    brand_fonts = set(invariants["fonts"].values())
    used = {i["fontFamily"].split(",")[0].strip().strip("'\"") for i in page.get("items", [])}
    font_score = len(used & brand_fonts) / max(1, len(used))
    signature = 1.0 if (page.get("hasFooter") or page.get("nodeType") == "Cover") else 0.0
    forbidden = 1.0 - min(1.0, len(page.get("cardLike", [])) / 4)
    return round(0.4 * on_palette + 0.25 * font_score + 0.2 * signature + 0.15 * forbidden, 4)


@dataclass
class SimilarityVerdict:
    brand_similarity: float
    layout_similarity_max: float
    nearest: str | None
    verdict: str                      # OK | MUTATE | REJECT
    comparisons: dict[str, float] = field(default_factory=dict)


class AntiCopyEngine:
    def __init__(self, invariants: dict[str, Any], references: dict[str, dict[str, Any]] | None = None):
        """references: id -> {'grid','signature','dhash'} from approved layouts / previous guides (DesignMemory)."""
        self.invariants = invariants
        self.references = references or {}

    def check(self, page: dict[str, Any], signature: str, fonts_loaded: list[str],
              same_document: dict[str, dict[str, Any]] | None = None, dhash: int | None = None) -> SimilarityVerdict:
        me = {"grid": occupancy_grid(page), "signature": signature, "dhash": dhash}
        comps: dict[str, float] = {}
        for rid, ref in {**(same_document or {}), **self.references}.items():
            comps[rid] = layout_similarity(me, ref)
        nearest = max(comps, key=comps.get) if comps else None
        mx = comps[nearest] if nearest else 0.0
        verdict = "REJECT" if mx >= REJECT_AT else "MUTATE" if mx >= MUTATE_AT else "OK"
        return SimilarityVerdict(brand_similarity(page, self.invariants, fonts_loaded), mx, nearest, verdict, comps)
