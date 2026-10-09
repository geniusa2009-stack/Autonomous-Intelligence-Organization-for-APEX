"""Discovery adapters: SearXNG (self-hosted metasearch), browser-use (optional), local manifests, fixtures."""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""
    engine: str = ""


def build_query_plan(institution: str, cycle: str | None, roles: list[str]) -> list[str]:
    base = institution.strip()
    cyc = f" {cycle}" if cycle else ""
    plan = [f"{base} international admissions{cyc}", f"{base} application deadline{cyc}",
            f"{base} financial aid international students", f"{base} tuition fees cost of attendance",
            f"{base} TOEFL IELTS minimum", f"{base} SAT requirement test optional",
            f"{base} application requirements recommendation essay"]
    if "VisaLogisticsSpecialist" in roles:
        plan.append(f"{base} international students I-20 F-1 visa")
    if "HistoricalEvidenceWorker" in roles:
        plan.append(f"{base} international admissions previous year deadline")
    if "ResearchRedTeam" in roles:
        plan.append(f"{base} scholarship deadline changed")
    return plan


class SearXNGAdapter:
    name = "searxng"

    def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None):
        self.base_url = (base_url or os.environ.get("SEARXNG_URL") or "").rstrip("/")
        self.transport = transport

    def available(self) -> tuple[bool, str]:
        return (True, "") if self.base_url else (False, "set SEARXNG_URL to a SearXNG instance with JSON output enabled")

    def search(self, query: str, n: int = 10) -> list[SearchResult]:
        if not self.base_url:
            return []
        with httpx.Client(transport=self.transport, timeout=20) as c:
            r = c.get(f"{self.base_url}/search", params={"q": query, "format": "json", "safesearch": 1})
        r.raise_for_status()
        return [SearchResult(x.get("url", ""), x.get("title", ""), x.get("content", ""), x.get("engine", ""))
                for x in r.json().get("results", [])[:n] if x.get("url")]


class BrowserUseAdapter:
    """Agentic browsing via the optional `browser-use` package (needs an LLM route; $0 firewall applies)."""

    name = "browser-use"

    def available(self) -> tuple[bool, str]:
        if importlib.util.find_spec("browser_use") is None:
            return False, "OPTIONAL_DEPENDENCY_MISSING: pip install 'apex-one[browser-agent]'"
        return False, "CONFIGURED_BUT_UNTESTED: requires a $0 vision/tool-use model route"

    def search(self, query: str, n: int = 10) -> list[SearchResult]:
        return []


class FixtureSearch:
    name = "synthetic-fixture"

    def __init__(self, corpus_dir: Path):
        self.manifest = yaml.safe_load((corpus_dir / "corpus.yaml").read_text(encoding="utf-8"))

    def available(self) -> tuple[bool, str]:
        return True, "synthetic offline corpus"

    def search(self, query: str, n: int = 10) -> list[SearchResult]:
        docs = self.manifest["documents"]
        idx = self.manifest.get("search_index", {})
        q = query.lower()
        hits: list[int] = []
        for key, ids in idx.items():
            if set(re.findall(r"\w+", key.lower())) & set(re.findall(r"\w+", q)) >= {"example", "labor"}:
                overlap = len(set(key.lower().split()) & set(q.split()))
                if overlap >= 4:
                    hits += [i for i in ids if i not in hits]
        if not hits and "example labor" in q:
            hits = list(range(len(docs)))
        return [SearchResult(docs[i]["url"], docs[i]["file"], "", self.name) for i in hits[:n]]


class LocalManifestSearch:
    """A directory of saved sources + sources.yaml: [{url, file, kind?, cycle_year?}]."""

    name = "local-manifest"

    def __init__(self, directory: Path):
        self.dir = directory
        manifest = directory / "sources.yaml"
        self.entries = (yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}).get("sources", []) \
            if manifest.exists() else [{"url": f"file://{p.resolve()}", "file": p.name}
                                       for p in sorted(directory.iterdir()) if p.suffix.lower() in (".html", ".htm", ".pdf")]

    def available(self) -> tuple[bool, str]:
        return bool(self.entries), f"{len(self.entries)} local sources"

    def search(self, query: str, n: int = 50) -> list[SearchResult]:
        return [SearchResult(e["url"], e.get("title", e["file"]), "", self.name) for e in self.entries][:n]

    def file_map(self) -> dict[str, Path]:
        return {e["url"]: self.dir / e["file"] for e in self.entries}

    def hints(self) -> dict[str, dict]:
        return {e["url"]: e for e in self.entries}
