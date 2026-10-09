"""ONE Research: a dynamic research swarm.

Roles are functions over a shared, persisted ResearchState — not permanent processes. The worker
count scales with quality mode and with evidence gaps (coverage of critical predicates).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import Field

from apex_one.core.schemas.common import ApexModel, stable_hash
from apex_one.core.schemas.evidence import (
    Claim,
    ClaimStatus,
    Contradiction,
    Evidence,
    FactLock,
    Source,
    SourceKind,
    Verification,
)
from apex_one.core.schemas.mission import Job, QualityMode
from apex_one.core.workspace import JobWorkspace
from apex_one.research.authority import classify, detect_cycle_year, domain_of, infer_official_domains
from apex_one.research.browser.fetchers import FetchError, FetchResult, FixtureFetcher, HttpFetcher, LocalFileFetcher
from apex_one.research.contradiction.hunter import ContradictionHunter
from apex_one.research.discovery.search import (
    FixtureSearch,
    LocalManifestSearch,
    SearXNGAdapter,
    build_query_plan,
)
from apex_one.research.documents.parsers import ParsedBlock, ParsedDocument, parse_any
from apex_one.research.evidence.extractor import Extraction, ModelEvidenceExtractor, RuleEvidenceExtractor
from apex_one.research.verification.verifier import FactLocker, Verifier

PERMANENT_ROLES = [
    "ResearchDirector", "OfficialSourceHunter", "DiscoveryWorker", "WebReader", "DocumentReader",
    "DeadlineSpecialist", "EligibilitySpecialist", "FundingSpecialist", "AdmissionsSpecialist",
    "VisaLogisticsSpecialist", "HistoricalEvidenceWorker", "FreshnessAuditor", "SourceAuthorityJudge",
    "ContradictionHunter", "ResearchRedTeam",
]
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ResearchState(ApexModel):
    backend: str = "live"                       # live | fixture:<name> | local:<dir>
    roles: list[str] = Field(default_factory=list)
    workers: int = 3
    official_domains: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    candidate_urls: list[str] = Field(default_factory=list)
    url_hints: dict[str, dict[str, Any]] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)
    locks: list[FactLock] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    red_team: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    extractors_used: list[str] = Field(default_factory=list)
    expansion_rounds: int = 0


def plan_workers(mode: QualityMode, gaps: int = 0) -> tuple[int, list[str]]:
    base = {QualityMode.DRAFT: 3, QualityMode.STANDARD: 6, QualityMode.HIGH: 10, QualityMode.ULTRA: 12}[mode]
    cap = {QualityMode.DRAFT: 3, QualityMode.STANDARD: 10, QualityMode.HIGH: 16, QualityMode.ULTRA: 20}[mode]
    workers = min(cap, base + 2 * gaps)
    roles = PERMANENT_ROLES if mode in (QualityMode.HIGH, QualityMode.ULTRA) else \
        PERMANENT_ROLES[:6] + ["FundingSpecialist", "ContradictionHunter", "SourceAuthorityJudge"]
    if mode == QualityMode.DRAFT:
        roles = ["ResearchDirector", "OfficialSourceHunter", "DocumentReader", "ContradictionHunter"]
    return workers, roles


class ResearchDirector:
    """Coordinates the swarm across the research states of the job state machine."""

    STATE_FILE = "research_state.json"

    def __init__(self, job: Job, ws: JobWorkspace, broker=None):
        self.job, self.ws, self.broker = job, ws, broker
        self.state = self._load()
        self._fetcher = None
        self._search = None

    # ---------------- persistence ----------------
    def _load(self) -> ResearchState:
        if self.ws.exists(self.STATE_FILE):
            return ResearchState.model_validate(self.ws.read_json(self.STATE_FILE))
        backend = "live"
        if self.job.offline_fixture:
            backend = f"fixture:{self.job.offline_fixture}"
        elif self.job.source_inputs:
            backend = f"local:{self.job.source_inputs[0]}"
        return ResearchState(backend=backend)

    def save(self) -> None:
        self.ws.write_json(self.STATE_FILE, self.state)

    # ---------------- backends ----------------
    def _backend(self):
        if self._search is not None:
            return self._search, self._fetcher
        kind, _, arg = self.state.backend.partition(":")
        if kind == "fixture":
            d = FIXTURES_DIR / arg
            self._search, self._fetcher = FixtureSearch(d), FixtureFetcher(d)
        elif kind == "local":
            s = LocalManifestSearch(Path(arg))
            self._search, self._fetcher = s, LocalFileFetcher(s.file_map())
            self.state.url_hints = s.hints()
        else:
            self._search, self._fetcher = SearXNGAdapter(), HttpFetcher()
        return self._search, self._fetcher

    # ---------------- SOURCE_DISCOVERY ----------------
    def discover(self) -> bool:
        mode = self.job.policy.quality.mode
        self.state.workers, self.state.roles = plan_workers(mode)
        search, _ = self._backend()
        ok, detail = search.available()
        self.ws.check("SOURCE_DISCOVERY", "research.route_available", ok, detail)
        if not ok:
            self.state.blockers.append(f"No research route: {detail}. Or supply saved official sources with "
                                       f"--sources DIR (see docs/QUICKSTART.md).")
            self.save()
            return False
        inst = self.job.mission.institution or self.job.mission.opportunity_name
        self.state.queries = build_query_plan(inst, self.job.mission.cycle, self.state.roles)
        urls: list[str] = []
        for q in self.state.queries:
            for r in search.search(q):
                if r.url not in urls:
                    urls.append(r.url)
        self.state.candidate_urls = urls
        if self.state.backend.startswith("fixture:"):
            manifest = getattr(search, "manifest", {})
            self.state.official_domains = list(manifest.get("official_domains", []))
        elif not self.state.official_domains:
            hinted = [u for u, h in self.state.url_hints.items() if h.get("kind") in ("official", "official_document")]
            self.state.official_domains = sorted({".".join(domain_of(u).split(".")[-2:]) for u in hinted}) or \
                infer_official_domains(urls, inst)
        self.ws.check("SOURCE_DISCOVERY", "research.official_domain_hypothesis", bool(self.state.official_domains),
                      ",".join(self.state.official_domains))
        self.ws.check("SOURCE_DISCOVERY", "research.queries_generated", bool(self.state.queries))
        self.ws.check("SOURCE_DISCOVERY", "research.results_deduplicated", True, f"{len(urls)} urls")
        if not urls:
            self.state.blockers.append("Discovery returned no sources.")
        self.save()
        return bool(urls)

    # ---------------- SOURCE_EXPANSION + DOCUMENT_PARSE ----------------
    def _fetch_one(self, url: str) -> tuple[str, FetchResult | None, str]:
        _, fetcher = self._backend()
        try:
            return url, fetcher.fetch(url), ""
        except FetchError as e:
            return url, None, str(e)

    def expand_and_parse(self) -> bool:
        _, fetcher = self._backend()
        known = {s.url for s in self.state.sources}
        todo = [u for u in self.state.candidate_urls if u not in known]
        self.state.expansion_rounds += 1
        with ThreadPoolExecutor(max_workers=max(1, min(self.state.workers, 8))) as pool:
            results = list(pool.map(self._fetch_one, todo))
        hashes = {s.content_hash for s in self.state.sources}
        new_links: list[str] = []
        for url, res, err in results:
            if res is None:
                self.ws.events.emit("fetch_failed", url=url, error=err)
                continue
            h = stable_hash(res.content)
            if h in hashes:
                continue
            hashes.add(h)
            doc = parse_any(res.content, res.content_type)
            hint = self.state.url_hints.get(url, {})
            kind, authority = classify(url, self.state.official_domains, res.content_type)
            if hint.get("kind"):
                kind = SourceKind(hint["kind"])
                authority = max(authority, 0.9 if kind in (SourceKind.OFFICIAL, SourceKind.OFFICIAL_DOCUMENT) else authority)
            cycle = hint.get("cycle_year") or detect_cycle_year(" ".join([doc.title] + [b.text for b in doc.blocks[:6]]))
            src = Source(url=url, title=doc.title[:300], domain=domain_of(url), kind=kind, content_type=res.content_type,
                         content_hash=h, cycle_year=cycle, authority=authority, synthetic=res.synthetic,
                         fetch_method=res.method)
            rel = f"sources/{src.source_id}.json"
            self.ws.write_json(rel, {"url": url, "title": doc.title, "parser": doc.parser,
                                     "blocks": [b.__dict__ for b in doc.blocks]})
            src.text_path = rel
            self.state.sources.append(src)
            if kind == SourceKind.OFFICIAL and "html" in res.content_type and self.state.backend == "live":
                new_links += self._document_links(url, res.content)
        if new_links and self.state.expansion_rounds < 3:
            self.state.candidate_urls += [u for u in new_links if u not in self.state.candidate_urls][:20]
        self.ws.check("SOURCE_EXPANSION", "research.official_source_present",
                      any(s.kind in (SourceKind.OFFICIAL, SourceKind.OFFICIAL_DOCUMENT) for s in self.state.sources))
        self.ws.check("SOURCE_EXPANSION", "research.authority_scored", True, f"{len(self.state.sources)} sources")
        self.ws.check("DOCUMENT_PARSE", "parse.content_hashed", True)
        self.save()
        return bool(self.state.sources)

    def _document_links(self, base: str, html: bytes) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        out = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base, a["href"])
            text = (a.get_text(" ") or "").lower()
            if domain_of(href).endswith(tuple(self.state.official_domains)) and (
                    href.lower().endswith(".pdf") or re.search(r"international|deadline|financial|tuition|apply", text)):
                out.append(href.split("#")[0])
        return out

    def parsed(self, src: Source) -> ParsedDocument:
        data = self.ws.read_json(src.text_path or "")
        return ParsedDocument(title=data["title"], blocks=[ParsedBlock(**b) for b in data["blocks"]],
                              parser=data["parser"])

    # ---------------- EVIDENCE_EXTRACTION ----------------
    def extract(self, purpose: str = "production") -> int:
        subject = self.job.mission.institution or self.job.mission.opportunity_name
        rule = RuleEvidenceExtractor(subject)
        model = ModelEvidenceExtractor(self.broker, subject, purpose) if self.broker else None
        self.state.claims, self.state.evidence = [], []
        used = {rule.name}
        for src in self.state.sources:
            doc = self.parsed(src)
            ex = rule.extract(src, doc)
            if model is not None:
                mex, mid = model.extract(src, doc, self.ws)
                if mid:
                    used.add(f"model:{mid}")
                ex.extend(self._dedupe_model(ex, mex))
            self.state.claims += ex.claims
            self.state.evidence += ex.evidence
        self.state.extractors_used = sorted(used)
        for pred in ("deadline", "fee", "funding", "test_minimum", "eligibility", "application_requirement"):
            self.ws.check("EVIDENCE_EXTRACTION", f"evidence.{pred}_extracted",
                          any(c.predicate == pred for c in self.state.claims))
        self.save()
        return len(self.state.claims)

    @staticmethod
    def _dedupe_model(rule_ex: Extraction, model_ex: Extraction) -> Extraction:
        seen = {(c.slot, c.value.key(), c.source_ids[0]) for c in rule_ex.claims}
        out = Extraction()
        for c in model_ex.claims:
            if (c.slot, c.value.key(), c.source_ids[0]) not in seen:
                out.claims.append(c)
                out.evidence += [e for e in model_ex.evidence if e.evidence_id in c.evidence_ids]
        return out

    # ---------------- CONTRADICTION_SEARCH / FACT_RESOLUTION / FACT_LOCK ----------------
    def contradictions(self) -> int:
        smap = {s.source_id: s for s in self.state.sources}
        self.state.contradictions = ContradictionHunter(self.job.mission.cycle_year).find(self.state.claims, smap)
        self.save()
        return len(self.state.contradictions)

    def resolve_and_lock(self) -> dict[str, Any]:
        smap = {s.source_id: s for s in self.state.sources}
        resolutions = Verifier(self.job.mission.cycle_year).resolve(self.state.claims, smap, self.state.contradictions)
        winners = {r.winner.claim_id: r.winner for r in resolutions if r.winner}
        # replace claims by resolved versions (winners carry merged evidence)
        self.state.claims = [winners.get(c.claim_id, c) for c in self.state.claims]
        self.state.verifications = [r.verification for r in resolutions if r.verification]
        human_locks = [lk for lk in self.state.locks if lk.verified_by.startswith("human:")]
        locks = FactLocker.lock(resolutions)
        locked_slots = {lk.slot for lk in locks}
        locks += [lk for lk in human_locks if lk.slot not in locked_slots]
        self.state.locks = locks
        human_slots = {lk.slot for lk in human_locks}
        for x in self.state.contradictions:
            if x.slot in human_slots:
                x.resolved = True
                x.resolution = x.resolution or "resolved by human confirmation"
        for c in self.state.claims:
            if c.slot in human_slots and c.claim_id not in {lk.claim_id for lk in human_locks} \
                    and c.status != ClaimStatus.REJECTED:
                c.status = ClaimStatus.REJECTED
        lock_by_claim = {lk.claim_id for lk in locks}
        for c in self.state.claims:
            if c.claim_id in lock_by_claim:
                c.status = ClaimStatus.LOCKED
        self.red_team()
        self.save()
        return self.summary()

    # ---------------- ResearchRedTeam ----------------
    def red_team(self) -> None:
        findings = []
        smap = {s.source_id: s for s in self.state.sources}
        emap = {e.evidence_id: e for e in self.state.evidence}
        cmap = {c.claim_id: c for c in self.state.claims}
        for lk in self.state.locks:
            claim = cmap.get(lk.claim_id)
            if not claim:
                findings.append(f"{lk.slot}: lock without claim")
                continue
            for eid in claim.evidence_ids:
                ev = emap.get(eid)
                src = smap.get(ev.source_id) if ev else None
                if not ev or not src:
                    continue
                text = re.sub(r"\s+", " ", self.parsed(src).text)
                if re.sub(r"\s+", " ", ev.quote) not in text:
                    findings.append(f"{lk.slot}: quote not found verbatim in {src.url}")
            if lk.hedge:
                findings.append(f"{lk.slot}: source hedges the value ('{lk.hedge}'); copy must say so")
            if not lk.verify_integrity():
                findings.append(f"{lk.slot}: lock hash mismatch")
        self.state.red_team = findings

    def coverage(self, critical_predicates: list[str]) -> dict[str, str]:
        cov = {}
        for p in critical_predicates:
            if any(lk.predicate == p for lk in self.state.locks):
                cov[p] = "LOCKED"
            elif any(c.predicate == p and c.status == ClaimStatus.NEEDS_HUMAN for c in self.state.claims):
                cov[p] = "NEEDS_HUMAN"
            elif any(c.predicate == p for c in self.state.claims):
                cov[p] = "UNVERIFIED"
            else:
                cov[p] = "NOT_FOUND"
        self.state.coverage = cov
        return cov

    def summary(self) -> dict[str, Any]:
        unresolved_critical = [x for x in self.state.contradictions if x.critical and not x.resolved]
        return {
            "sources": len(self.state.sources),
            "claims": len(self.state.claims),
            "locks": len(self.state.locks),
            "contradictions": len(self.state.contradictions),
            "unresolved_critical_contradictions": len(unresolved_critical),
            "needs_human": sorted({c.slot for c in self.state.claims if c.status == ClaimStatus.NEEDS_HUMAN}),
            "red_team_findings": len(self.state.red_team),
        }

    def export(self) -> None:
        """Write the observability artifacts."""
        self.ws.write_json("sources.json", self.state.sources)
        self.ws.write_json("evidence.json", self.state.evidence)
        self.ws.write_json("claims.json", self.state.claims)
        self.ws.write_json("contradictions.json", self.state.contradictions)
        self.ws.write_json("verifications.json", self.state.verifications)
        self.ws.write_json("fact_locks.json", self.state.locks)
        self.ws.write_text("research_summary.json", json.dumps(
            {**self.summary(), "coverage": self.state.coverage, "red_team": self.state.red_team,
             "roles": self.state.roles, "workers": self.state.workers, "backend": self.state.backend,
             "extractors": self.state.extractors_used, "official_domains": self.state.official_domains,
             "queries": self.state.queries, "host_netlocs": sorted({urlparse(s.url).netloc for s in self.state.sources})},
            ensure_ascii=False, indent=2))
