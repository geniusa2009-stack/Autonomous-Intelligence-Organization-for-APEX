"""Playwright/Chromium renderer: real pages, real screenshots, real PDF, real DOM metrics."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apex_one.compute.hardware import find_chromium
from apex_one.document.compiler.styles import FONT_DIR

JS = (Path(__file__).parent / "dom_metrics.js").read_text(encoding="utf-8")
A4 = {"width": 794, "height": 1123}


def ensure_fonts(target_dir: Path) -> None:
    fonts = target_dir / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for f in FONT_DIR.glob("*.ttf"):
        dst = fonts / f.name
        if not dst.exists():
            shutil.copy2(f, dst)


@dataclass
class RenderResult:
    metrics: dict[str, Any]
    page_screenshots: list[Path] = field(default_factory=list)
    pdf_path: Path | None = None
    mobile_metrics: dict[str, Any] | None = None
    mobile_screenshot: Path | None = None
    engine: str = "chromium"


def pdf_with_weasyprint(html_path: Path, pdf_path: Path) -> Path:
    """Fallback PDF engine (optional extra `pdf-fallback`). Used only if Chromium printing fails."""
    from weasyprint import HTML

    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    return pdf_path


class Renderer:
    """Use as a context manager; one browser for many renders."""

    def __init__(self, device_scale: float = 1.0):
        self.device_scale = device_scale
        self._pw = self._browser = None

    def __enter__(self) -> "Renderer":
        from playwright.sync_api import sync_playwright

        exe = find_chromium()
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(executable_path=exe) if exe else self._pw.chromium.launch()
        except Exception:
            self._pw.stop()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def _page(self, width: int, height: int, scale: float):
        return self._browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)

    def measure(self, html_path: Path, min_margin_mm: float = 12.0, screenshot_dir: Path | None = None,
                screenshot_prefix: str = "page") -> RenderResult:
        page = self._page(A4["width"] + 40, A4["height"], self.device_scale)
        try:
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            metrics = page.evaluate(JS, {"minMarginMm": min_margin_mm})
            shots: list[Path] = []
            if screenshot_dir is not None:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                visible = [el for el in page.query_selector_all("section.page") if el.is_visible()]
                for i, el in enumerate(visible, start=1):
                    p = screenshot_dir / f"{screenshot_prefix}-{i:02d}.png"
                    el.screenshot(path=str(p))
                    shots.append(p)
            return RenderResult(metrics=metrics, page_screenshots=shots)
        finally:
            page.close()

    def render_full(self, html_path: Path, out_dir: Path, *, min_margin_mm: float = 12.0,
                    pdf_path: Path | None = None) -> RenderResult:
        res = self.measure(html_path, min_margin_mm, screenshot_dir=out_dir / "screenshots")
        if pdf_path is not None:
            page = self._page(A4["width"], A4["height"], 1.0)
            try:
                page.goto(html_path.resolve().as_uri(), wait_until="load")
                page.evaluate("document.fonts.ready.then(() => true)")
                page.emulate_media(media="print")
                page.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True,
                         margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
                res.engine = "chromium"
            except Exception:
                pdf_with_weasyprint(html_path, pdf_path)
                res.engine = "weasyprint-fallback"
            finally:
                page.close()
            res.pdf_path = pdf_path
        # mobile preview (responsive reflow)
        mpage = self._page(390, 844, 2.0)
        try:
            mpage.goto(html_path.resolve().as_uri(), wait_until="load")
            mpage.evaluate("document.fonts.ready.then(() => true)")
            res.mobile_metrics = mpage.evaluate(JS, {"minMarginMm": 0})
            mshot = out_dir / "screenshots" / "mobile-preview.png"
            mpage.screenshot(path=str(mshot), full_page=False)
            res.mobile_screenshot = mshot
        finally:
            mpage.close()
        (out_dir / "qa").mkdir(parents=True, exist_ok=True)
        (out_dir / "qa" / "dom_metrics.json").write_text(json.dumps(res.metrics, ensure_ascii=False), encoding="utf-8")
        return res
