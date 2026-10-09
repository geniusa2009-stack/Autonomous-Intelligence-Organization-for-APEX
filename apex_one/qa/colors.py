"""Colour utilities (WCAG contrast, palette distance)."""

from __future__ import annotations

import re


def parse_rgb(css: str) -> tuple[float, float, float, float] | None:
    m = re.match(r"rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)", css or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4) or 1)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str) -> float | None:
    f, b = parse_rgb(fg), parse_rgb(bg)
    if not f or not b:
        return None
    l1, l2 = luminance(f[:3]), luminance(b[:3])
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def nearest_palette_distance(css: str, palette_hex: list[str]) -> float:
    c = parse_rgb(css)
    if not c or c[3] == 0:
        return 0.0
    return min(sum((a - b) ** 2 for a, b in zip(c[:3], hex_rgb(h))) ** 0.5 for h in palette_hex)
