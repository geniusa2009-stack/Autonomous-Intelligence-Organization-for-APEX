import json
from pathlib import Path

import httpx
import pytest

from apex_one.compute.broker import ComputeBroker
from apex_one.compute.providers import MockAdapter
from apex_one.core.schemas.evidence import ClaimStatus, Source, SourceKind
from apex_one.core.schemas.mission import Job, Mission
from apex_one.core.workspace import JobWorkspace
from apex_one.editorial.fact_guard import LockRegistry, semantic_diff
from apex_one.knowledge import EntityType, KnowledgeGraph, build_graph_from_research
from apex_one.persistence import init_db
from apex_one.research.authority import classify, detect_cycle_year, infer_official_domains
from apex_one.research.browser import FetchError, HttpFetcher
from apex_one.research.discovery import SearXNGAdapter
from apex_one.research.documents import parse_html
from apex_one.research.evidence.extractor import ModelEvidenceExtractor, RuleEvidenceExtractor
from apex_one.research.evidence.normalize import find_dates, find_money, find_percents
from apex_one.research.swarm import ResearchDirector


def _job(**kw):
    return Job(mission=Mission(text="x", opportunity_name="Example Labor College Fall 2027",
                               institution="Example Labor College", cycle="Fall 2027", cycle_year=2027),
               offline_fixture="synthetic_berea_style", **kw)


@pytest.fixture
def researched(tmp_path):
    job = _job()
    ws = JobWorkspace(job.job_id, root=tmp_path)
    rd = ResearchDirector(job, ws)
    assert rd.discover() and rd.expand_and_parse()
    rd.extract()
    rd.contradictions()
    rd.resolve_and_lock()
    return rd


def test_normalizers_handle_english_and_arabic():
    assert [d.isoformat() for d, *_ in find_dates("Due Nov. 1, 2026 or ١٥ يناير ٢٠٢٧")] == ["2026-11-01", "2027-01-15"]
    assert find_money("fee US$65 or 1,500 EGP")[0][:2] == (65.0, "USD")
    assert find_money("fee US$65 or 1,500 EGP")[1][:2] == (1500.0, "EGP")
    assert find_percents("يغطي ١٠٠٪")[0][0] == 100.0


def test_rule_extractor_predicates():
    html = """<h2>Dates</h2><p>The application deadline is January 15, 2027.</p>
    <p>The application fee is $65.</p><p>We are test-optional.</p>
    <p>A minimum TOEFL iBT score of 90 is required.</p>"""
    src = Source(url="https://x.edu/a")
    ex = RuleEvidenceExtractor("X").extract(src, parse_html(html))
    slots = {c.slot: c.value.canonical for c in ex.claims}
    assert slots["deadline.application"] == "2027-01-15"
    assert slots["fee.application"] == "USD 65"
    assert slots["test_requirement.sat_act"] == "false"
    assert slots["test_minimum.toefl_ibt"] == "90"
    assert all(e.quote and e.locator for e in ex.evidence)


def test_full_research_on_synthetic_corpus(researched):
    st = researched.state
    locks = {lk.slot: lk for lk in st.locks}
    assert locks["deadline.application"].value.canonical == "2026-11-01"      # official, current cycle
    assert locks["fee.application"].value.canonical == "USD 0"                # blog's $35 rejected
    assert locks["test_minimum.toefl_ibt"].value.canonical == "80"            # 2026-cycle 79 rejected
    assert locks["test_minimum.ielts"].value.canonical == "6.5"               # blog 6.0 rejected
    assert locks["test_requirement.sat_act"].value.canonical == "false"       # forum rumour rejected
    assert locks["funding.student_contribution_per_year"].hedge == "estimated"
    assert all(s.synthetic for s in st.sources)
    summary = researched.summary()
    assert summary["unresolved_critical_contradictions"] == 0
    rejected = [c for c in st.claims if c.status == ClaimStatus.REJECTED]
    assert any("previous-cycle" == c.freshness for c in rejected)
    assert any("low-authority" in " ".join(c.notes) for c in rejected)
    assert all(lk.verify_integrity() for lk in st.locks)
    # red team: every locked quote exists verbatim in its source
    assert not [f for f in st.red_team if "quote not found" in f]


def test_single_source_critical_claim_needs_human(researched):
    st = researched.state
    needs = {c.slot for c in st.claims if c.status == ClaimStatus.NEEDS_HUMAN}
    assert "visa_logistics.visa_type" in needs
    assert "visa_logistics.visa_type" not in {lk.slot for lk in st.locks}


def test_official_sources_disagree_is_unresolved(tmp_path):
    from apex_one.research.contradiction import ContradictionHunter
    from apex_one.research.verification import Verifier

    s1 = Source(url="https://a.edu/1", kind=SourceKind.OFFICIAL, authority=0.95, cycle_year=2027, content_hash="1")
    s2 = Source(url="https://a.edu/2", kind=SourceKind.OFFICIAL, authority=0.95, cycle_year=2027, content_hash="2")
    ex1 = RuleEvidenceExtractor("A").extract(s1, parse_html("<p>The application deadline is January 1, 2027.</p>"))
    ex2 = RuleEvidenceExtractor("A").extract(s2, parse_html("<p>The application deadline is January 9, 2027.</p>"))
    claims = ex1.claims + ex2.claims
    smap = {s1.source_id: s1, s2.source_id: s2}
    xs = ContradictionHunter(2027).find(claims, smap)
    res = Verifier(2027).resolve(claims, smap, xs)
    assert res[0].verification.verdict == ClaimStatus.NEEDS_HUMAN
    assert xs and not xs[0].resolved


def test_model_extractor_drops_hallucinated_quotes(registry, tmp_path):
    def script(messages, json_mode):
        return json.dumps({"claims": [
            {"predicate": "deadline", "quote": "The application deadline is January 15, 2027."},
            {"predicate": "fee", "quote": "The application fee is $999 (invented)."},
        ]})

    broker = ComputeBroker(registry, allow_mock=True,
                           adapters={"mock": MockAdapter(registry.providers["mock"], script=script)})
    src = Source(url="https://x.edu")
    doc = parse_html("<p>The application deadline is January 15, 2027.</p>")
    ex, mid = ModelEvidenceExtractor(broker, "X", purpose="research").extract(src, doc)
    assert mid == "mock-llm"
    assert [c.value.canonical for c in ex.claims] == ["2027-01-15"]
    assert all(e.extractor == "model:mock-llm" for e in ex.evidence)


def test_semantic_diff_and_lock_immutability(researched):
    locks = researched.state.locks
    ok = "آخر ميعاد 1 نوفمبر 2026 والـ deposit هو $50 و TOEFL 80 والمصاريف 100%"
    assert semantic_diff(ok, locks, allowed_years={2027}) == []
    bad = "آخر ميعاد 1 ديسمبر 2026 والـ deposit هو $55 و IELTS 6"
    kinds = {v.kind for v in semantic_diff(bad, locks)}
    assert {"unbound_date", "altered_money", "unbound_number"} <= kinds
    assert semantic_diff("آخر ميعاد ١ نوفمبر ٢٠٢٦", locks) == []
    reg = LockRegistry(locks)
    copy = reg["deadline.application"]
    copy.display_en = "tampered"
    assert reg["deadline.application"].display_en != "tampered" and reg.intact()
    tampered = locks[0].model_copy(update={"display_en": "x"})
    assert not tampered.verify_integrity()


def test_knowledge_graph_traversal_and_persistence(researched):
    init_db()
    g = build_graph_from_research(researched.state, researched.job.mission)
    deadline = g.nodes["fact:deadline.application"]
    assert deadline.entity_type == EntityType.DEADLINE
    srcs = g.provenance(deadline.node_id)
    assert srcs and all(n.entity_type == EntityType.SOURCE for n in srcs)
    assert g.path("opportunity", srcs[0].node_id)
    assert g.of_type(EntityType.APPLICANT_STEP)
    g.save("J-kg")
    g2 = KnowledgeGraph.load("J-kg")
    assert len(g2.nodes) == len(g.nodes) and g2.provenance("fact:deadline.application")


def test_http_fetcher_respects_robots():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="<p>ok</p>", headers={"content-type": "text/html"})

    f = HttpFetcher(transport=httpx.MockTransport(handler))
    assert f.fetch("https://x.edu/public").content == b"<p>ok</p>"
    with pytest.raises(FetchError):
        f.fetch("https://x.edu/private/page")


def test_searxng_adapter():
    def handler(req):
        assert req.url.params["format"] == "json"
        return httpx.Response(200, json={"results": [{"url": "https://berea.example/x", "title": "t"}]})

    a = SearXNGAdapter("http://searx.local", transport=httpx.MockTransport(handler))
    assert a.available()[0] and a.search("q")[0].url == "https://berea.example/x"
    assert not SearXNGAdapter("").available()[0]


def test_authority_and_cycle_detection():
    assert classify("https://admissions.example-labor-college.invalid/x", ["example-labor-college.invalid"])[0] == SourceKind.OFFICIAL
    assert classify("https://forum.student-talk.invalid/t/1", [])[0] == SourceKind.FORUM
    assert detect_cycle_year("International Applicants: Fall 2027 Entry") == 2027
    assert infer_official_domains(["https://www.berea.edu/a", "https://bereablog.com/x", "https://berea.edu/b"],
                                  "Berea College") == ["berea.edu"]


def test_live_mode_without_search_is_blocked(tmp_path):
    job = Job(mission=Mission(text="x", opportunity_name="Berea College Fall 2027", institution="Berea College",
                              cycle="Fall 2027", cycle_year=2027))
    rd = ResearchDirector(job, JobWorkspace(job.job_id, root=tmp_path))
    assert rd.discover() is False
    assert any("SEARXNG_URL" in b for b in rd.state.blockers)


def test_local_sources_manifest(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "page.html").write_text("<h1>Fall 2027</h1><p>The application deadline is January 5, 2027.</p>")
    (d / "sources.yaml").write_text("sources:\n  - {url: 'https://www.uni.edu/intl', file: page.html, kind: official, cycle_year: 2027}\n")
    job = Job(mission=Mission(text="x", opportunity_name="Uni Fall 2027", institution="Uni", cycle="Fall 2027",
                              cycle_year=2027), source_inputs=[str(d)])
    rd = ResearchDirector(job, JobWorkspace(job.job_id, root=tmp_path / "ws"))
    assert rd.discover() and rd.expand_and_parse()
    assert rd.state.sources[0].kind == SourceKind.OFFICIAL
    assert rd.extract() >= 1
    _ = Path
