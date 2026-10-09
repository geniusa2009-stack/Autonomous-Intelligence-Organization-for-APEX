"""apex-native-svg: deterministic, original vector assets (no model, no licence risk).

Visual metaphors are quiet structural line systems — never blobs, gradients or random icons.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "assets"


@lru_cache(maxsize=8)
def inline_asset(rel: str) -> str:
    svg = (ASSETS / rel).read_text(encoding="utf-8")
    return svg[svg.index("<svg"):]


def metaphor_svg(kind: str, width: int, height: int, color: str, seed: int, opacity: float = 0.14) -> str:
    rng = random.Random(seed)
    parts: list[str] = []
    if kind == "grid-lines":
        step = rng.choice([48, 56, 64, 72])
        for x in range(step, width, step):
            parts.append(f'<path d="M{x} 0 V{height}"/>')
        for y in range(step, height, step):
            parts.append(f'<path d="M0 {y} H{width}"/>')
        hx = rng.randrange(step, width - step, step)
        parts.append(f'<path d="M{hx} 0 V{height}" stroke-width="2.2"/>')
    elif kind == "orbit":
        cx, cy = rng.uniform(0.2, 0.8) * width, rng.uniform(0.15, 0.5) * height
        for i in range(1, 6):
            r = i * min(width, height) * 0.11
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none"/>')
        a = rng.uniform(0, math.tau)
        r = 3 * min(width, height) * 0.11
        parts.append(f'<circle cx="{cx + r * math.cos(a):.1f}" cy="{cy + r * math.sin(a):.1f}" r="5" fill="{color}"/>')
    elif kind == "blueprint":
        x0, y0 = rng.uniform(0.05, 0.3) * width, rng.uniform(0.05, 0.25) * height
        w, h = width * 0.55, height * 0.35
        parts += [f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="none"/>',
                  f'<path d="M{x0:.1f} {y0 + h + 14:.1f} H{x0 + w:.1f}"/>',
                  f'<path d="M{x0:.1f} {y0 + h + 8:.1f} V{y0 + h + 20:.1f} M{x0 + w:.1f} {y0 + h + 8:.1f} V{y0 + h + 20:.1f}"/>',
                  f'<path d="M{x0 + w + 14:.1f} {y0:.1f} V{y0 + h:.1f}"/>']
    else:
        return ""
    return (f'<svg class="metaphor" data-decor="1" aria-hidden="true" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none" style="opacity:{opacity}"><g stroke="{color}" stroke-width="1" fill="none">'
            + "".join(parts) + "</g></svg>")


def bar_fraction_svg(value_pct: float, fg: str, bg: str, width: int = 520, height: int = 18) -> str:
    v = max(0.0, min(100.0, value_pct))
    w = width * v / 100
    # RTL page: the bar fills from the right edge
    return (f'<svg class="viz-bar" viewBox="0 0 {width} {height}" role="img" aria-label="{v:.0f}%">'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{bg}"/>'
            f'<rect x="{width - w:.1f}" y="0" width="{w:.1f}" height="{height}" fill="{fg}"/></svg>')
