"""Fetchers: direct HTTP (robots-aware), Playwright (JS pages), local files, synthetic fixtures."""

from __future__ import annotations

import os
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

MAX_BYTES = 12 * 1024 * 1024


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    url: str
    content: bytes
    content_type: str
    status: int
    method: str
    synthetic: bool = False


def user_agent() -> str:
    return os.environ.get("APEX_RESEARCH_USER_AGENT", "APEX-ONE-Research/0.1")


class HttpFetcher:
    name = "http"

    def __init__(self, transport: httpx.BaseTransport | None = None, respect_robots: bool = True, timeout: float = 20):
        self.transport, self.respect_robots, self.timeout = transport, respect_robots, timeout
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                with httpx.Client(transport=self.transport, timeout=8, headers={"User-Agent": user_agent()}) as c:
                    r = c.get(root + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                self._robots[root] = rp
            except httpx.HTTPError:
                self._robots[root] = None
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(user_agent(), url)

    def fetch(self, url: str) -> FetchResult:
        if not self.allowed(url):
            raise FetchError(f"robots.txt disallows {url}")
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout, follow_redirects=True,
                              headers={"User-Agent": user_agent()}) as c:
                r = c.get(url)
        except httpx.HTTPError as e:
            raise FetchError(f"{type(e).__name__}: {e}") from e
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code} for {url}")
        if len(r.content) > MAX_BYTES:
            raise FetchError("document too large")
        return FetchResult(str(r.url), r.content, r.headers.get("content-type", "text/html"), r.status_code, self.name)


class PlaywrightFetcher:
    """For JavaScript-rendered pages. Uses the same Chromium as the renderer."""

    name = "playwright"

    def fetch(self, url: str) -> FetchResult:  # pragma: no cover - requires network
        from playwright.sync_api import sync_playwright

        from apex_one.compute.hardware import find_chromium

        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=find_chromium())
            page = browser.new_page(user_agent=user_agent())
            resp = page.goto(url, wait_until="networkidle", timeout=45000)
            html = page.content()
            browser.close()
        return FetchResult(url, html.encode("utf-8"), "text/html", resp.status if resp else 0, self.name)


class LocalFileFetcher:
    """User-supplied files (saved official pages/PDFs). URL mapping comes from sources.yaml."""

    name = "local-file"

    def __init__(self, mapping: dict[str, Path]):
        self.mapping = mapping

    def fetch(self, url: str) -> FetchResult:
        path = self.mapping.get(url)
        if path is None or not path.exists():
            raise FetchError(f"no local file for {url}")
        ctype = "application/pdf" if path.suffix.lower() == ".pdf" else "text/html"
        return FetchResult(url, path.read_bytes(), ctype, 200, self.name)


def text_to_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    rect = pymupdf.Rect(50, 50, 545, 790)
    page.insert_textbox(rect, text, fontsize=10.5, fontname="helv")
    doc.set_metadata({"title": text.splitlines()[0][:120]})
    data = doc.tobytes()
    doc.close()
    return data


class FixtureFetcher:
    """Serves the synthetic offline corpus. Every result is flagged synthetic=True."""

    name = "synthetic-fixture"

    def __init__(self, corpus_dir: Path):
        self.dir = corpus_dir
        self.manifest = yaml.safe_load((corpus_dir / "corpus.yaml").read_text(encoding="utf-8"))
        self.docs = {d["url"]: d for d in self.manifest["documents"]}

    def fetch(self, url: str) -> FetchResult:
        d = self.docs.get(url)
        if not d:
            raise FetchError(f"not in synthetic corpus: {url}")
        raw = (self.dir / d["file"]).read_text(encoding="utf-8")
        if d.get("render_pdf_from_text"):
            return FetchResult(url, text_to_pdf(raw), "application/pdf", 200, self.name, synthetic=True)
        return FetchResult(url, raw.encode("utf-8"), d["content_type"], 200, self.name, synthetic=True)
