"""Derived page images: thumbnail, grayscale, blur, zoom crops (for vision critics and humans)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


def derive_images(png: Path, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(png).convert("RGB")
    stem = png.stem
    paths = {}
    thumb = im.copy()
    thumb.thumbnail((240, 340))
    paths["thumbnail"] = out_dir / f"{stem}-thumb.png"
    thumb.save(paths["thumbnail"])
    paths["grayscale"] = out_dir / f"{stem}-gray.png"
    ImageOps.grayscale(im).save(paths["grayscale"])
    paths["blur"] = out_dir / f"{stem}-blur.png"
    im.filter(ImageFilter.GaussianBlur(radius=max(4, im.width // 90))).save(paths["blur"])
    w, h = im.size
    for name, box in (("zoom-top", (0, 0, w, h // 3)), ("zoom-mid", (0, h // 3, w, 2 * h // 3)),
                      ("zoom-bottom", (0, 2 * h // 3, w, h))):
        paths[name] = out_dir / f"{stem}-{name}.png"
        im.crop(box).save(paths[name])
    return paths


def dhash(png: Path, size: int = 12) -> int:
    im = Image.open(png).convert("L").resize((size + 1, size))
    px = list(im.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | int(px[r * (size + 1) + c] > px[r * (size + 1) + c + 1])
    return bits


def hamming_similarity(a: int, b: int, bits: int = 144) -> float:
    return 1.0 - bin(a ^ b).count("1") / bits


def ink_stats(png: Path) -> tuple[float, float]:
    """(mean luminance 0..1, ink density = fraction of pixels differing strongly from the page background)."""
    im = Image.open(png).convert("L")
    small = im.resize((120, 170))
    px = list(small.getdata())
    mean = sum(px) / len(px) / 255
    bg = max(set(px), key=px.count)
    ink = sum(1 for p in px if abs(p - bg) > 40) / len(px)
    return mean, ink
