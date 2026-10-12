"""Document parsing: HTML (BeautifulSoup/lxml), PDF (PyMuPDF), optional Docling.

Output keeps the heading path of every block so evidence carries a precise locator.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

HEADINGS = ("h1", "h2", "h3", "h4")
BLOCK_TAGS = ("p", "li", "td", "th", "dd", "dt", "blockquote", "figcaption", "caption")


@dataclass
class ParsedBlock:
    text: str
    locator: str           # heading path or "page N"
    tag: str = "p"
    year_context: int | None = None   # a year declared by the enclosing table header, e.g. "Dates (2027)"


@dataclass
class ParsedDocument:
    title: str
    blocks: list[ParsedBlock]
    meta: dict[str, str] = field(default_factory=dict)
    parser: str = ""

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _table_year(tr) -> int | None:
    """Year stated in the table's header row (e.g. "Dates (2027)"); only an explicit 20xx in the header counts."""
    table = tr.find_parent("table")
    first = table.find("tr") if table else None
    if first is None or first is tr:
        return None
    m = re.findall(r"\b(20\d\d)\b", first.get_text(" "))
    return int(m[0]) if len(set(m)) == 1 else None


def parse_html(html: str) -> ParsedDocument:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "nav", "footer", "svg", "form"]):
        t.decompose()
    title = _clean(soup.title.get_text()) if soup.title else ""
    meta = {}
    for m in soup.find_all("meta"):
        name = (m.get("name") or m.get("property") or "").lower()
        if name and m.get("content"):
            meta[name] = m["content"]
    path: list[str] = []
    blocks: list[ParsedBlock] = []
    body = soup.body or soup
    for el in body.find_all(list(HEADINGS) + list(BLOCK_TAGS) + ["tr"]):
        if el.name == "tr":
            # a table row is ONE statement ("Mentee Applications Open | Feb 3 - Feb 16"): keep label and value together
            cells = [_clean(c.get_text(" ")) for c in el.find_all(["td", "th"], recursive=False)]
            txt = " | ".join(c for c in cells if c)
            if txt:
                blocks.append(ParsedBlock(txt, " > ".join(path) or "body", "tr", _table_year(el)))
            continue
        if el.name in ("td", "th") and el.find_parent("tr"):
            continue                                    # already part of its row block
        txt = _clean(el.get_text(" "))
        if not txt:
            continue
        if el.name in HEADINGS:
            level = int(el.name[1])
            path = path[: level - 1] + [txt]
            blocks.append(ParsedBlock(txt, " > ".join(path), el.name))
            continue
        if el.find_parent(BLOCK_TAGS):  # avoid double counting nested blocks
            continue
        blocks.append(ParsedBlock(txt, " > ".join(path) or "body", el.name))
    return ParsedDocument(title=title, blocks=blocks, meta=meta, parser="bs4-lxml")


def parse_pdf(data: bytes) -> ParsedDocument:
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    blocks: list[ParsedBlock] = []
    title = doc.metadata.get("title", "") if doc.metadata else ""
    for i, page in enumerate(doc, start=1):
        for b in page.get_text("blocks"):
            txt = _clean(b[4])
            if txt:
                blocks.append(ParsedBlock(txt, f"page {i}", "pdf-block"))
    meta = {k: str(v) for k, v in (doc.metadata or {}).items() if v}
    doc.close()
    return ParsedDocument(title=title, blocks=blocks, meta=meta, parser="pymupdf")


def docling_available() -> bool:
    return importlib.util.find_spec("docling") is not None


def parse_with_docling(path: Path) -> ParsedDocument:  # pragma: no cover - optional dependency
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(path))
    md = result.document.export_to_markdown()
    blocks, heading = [], "body"
    for line in md.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading = line.lstrip("# ").strip()
            blocks.append(ParsedBlock(heading, heading, "h"))
        else:
            blocks.append(ParsedBlock(_clean(line.lstrip("-* ")), heading, "p"))
    return ParsedDocument(title=path.stem, blocks=blocks, parser="docling")


def parse_any(content: bytes, content_type: str) -> ParsedDocument:
    if "pdf" in content_type:
        if docling_available():  # pragma: no cover - optional dependency
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(content)
                tmp.flush()
                try:
                    return parse_with_docling(Path(tmp.name))
                except Exception:
                    pass
        return parse_pdf(content)
    return parse_html(content.decode("utf-8", errors="replace"))
