"""Phase 14+ modules: local acquisition, live statuses, council scoring, vision council parsing/calibration,
anti-copy similarity, genome extraction, asset contract and the synthetic/real gate split."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw

from apex_one.core.schemas.common import Metric

# ---------------------------------------------------------------- local acquisition


def _spec(tmp_path, monkeypatch):
    from apex_one.compute.local import acquisition as acq

    monkeypatch.setattr(acq, "models_dir", lambda: tmp_path / "models")
    return acq, acq.LocalModelSpec(key="tiny", registry_model="tiny", repository="ai/tiny", tag="latest", port=9999)


def test_layer_names_cover_annotated_and_legacy_docker_layers():
    from apex_one.compute.local.acquisition import _fname

    assert _fname({"digest": "sha256:ab", "mediaType": "x", "annotations": {"org.cncf.model.filepath": "a/m.gguf"}}) == "m.gguf"
    assert _fname({"digest": "sha256:ab", "mediaType": "application/vnd.docker.ai.gguf.v3"}) == "model.gguf"
    assert _fname({"digest": "sha256:ab", "mediaType": "application/vnd.docker.ai.mmproj"}) == "mmproj-model.gguf"
    assert _fname({"digest": "sha256:ab", "mediaType": "application/vnd.docker.ai.license"}) == "LICENSE"
    assert _fname({"digest": "sha256:ab", "mediaType": "unknown"}) == "sha256_ab"


def _transport(blobs: dict[str, bytes], manifest: dict, corrupt: bool = False, quota: list | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "auth.docker.io":
            return httpx.Response(200, json={"token": "t"})
        if "/manifests/" in req.url.path:
            if quota:
                quota.pop()
                return httpx.Response(429)
            return httpx.Response(200, json=manifest)
        digest = req.url.path.rsplit("/", 1)[1]
        if digest in blobs:
            data = blobs[digest]
            return httpx.Response(200, content=(b"X" + data[1:]) if corrupt else data)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _manifest(model: bytes, lic: bytes):
    d1, d2 = "sha256:" + hashlib.sha256(model).hexdigest(), "sha256:" + hashlib.sha256(lic).hexdigest()
    return {d1: model, d2: lic}, {"layers": [
        {"digest": d1, "size": len(model), "mediaType": "application/vnd.docker.ai.gguf.v3"},
        {"digest": d2, "size": len(lic), "mediaType": "application/vnd.docker.ai.license"}]}


def test_acquire_verifies_digests_and_records_licence(tmp_path, monkeypatch):
    acq, spec = _spec(tmp_path, monkeypatch)
    blobs, man = _manifest(b"GGUF" + b"0" * 2000, b"Apache License 2.0")
    real = httpx.Client
    monkeypatch.setattr(acq.httpx, "Client", lambda *a, **k: real(transport=_transport(blobs, man)))
    rec = acq.acquire(spec, progress=lambda m: None, reserve_gb=0)
    assert [f["file"] for f in rec["files"]] == ["model.gguf", "LICENSE"]
    assert rec["licence_files"] == ["LICENSE"]
    assert (spec.dir / "model.gguf").read_bytes().startswith(b"GGUF")
    assert json.loads((spec.dir / "apex_manifest.json").read_text())["key"] == "tiny"


def test_acquire_deletes_blob_on_digest_mismatch(tmp_path, monkeypatch):
    acq, spec = _spec(tmp_path, monkeypatch)
    blobs, man = _manifest(b"GGUF" + b"0" * 2000, b"lic")
    real = httpx.Client
    monkeypatch.setattr(acq.httpx, "Client", lambda *a, **k: real(transport=_transport(blobs, man, corrupt=True)))
    with pytest.raises(RuntimeError, match="digest verification FAILED"):
        acq.acquire(spec, progress=lambda m: None, reserve_gb=0)
    assert not (spec.dir / "model.gguf").exists()


def test_manifest_quota_waits_instead_of_bypassing(tmp_path, monkeypatch):
    acq, spec = _spec(tmp_path, monkeypatch)
    blobs, man = _manifest(b"GGUF0", b"lic")
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    client = httpx.Client(transport=_transport(blobs, man, quota=[1, 1]))
    msgs: list[str] = []
    assert acq.fetch_manifest(spec, client, progress=msgs.append) == man
    assert sleeps == [300, 300] and all("429" in m for m in msgs)
    # cached: a second call does not touch the registry (quota-friendly)
    assert acq.fetch_manifest(spec, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))) == man


def test_manifest_quota_gives_up_after_max_wait(tmp_path, monkeypatch):
    acq, spec = _spec(tmp_path, monkeypatch)
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = httpx.Client(transport=_transport({}, {}, quota=[1] * 50))
    with pytest.raises(httpx.HTTPStatusError):
        acq.fetch_manifest(spec, client, max_wait_s=600, progress=lambda m: None)


# ---------------------------------------------------------------- live statuses / council scorers


def test_check_structured_is_exact():
    from apex_one.compute.live import check_structured

    assert check_structured('sure: {"deadline": "2027-01-15", "fee_usd": 65}')[0]
    assert not check_structured('{"deadline": "2027-01-16", "fee_usd": 65}')[0]
    assert not check_structured("no json")[0]


def test_network_check_classifies_proxy_denial(monkeypatch):
    from apex_one.compute import live

    def deny(*a, **k):
        raise httpx.ProxyError("403 Forbidden")
    monkeypatch.setattr(live.httpx, "get", deny)
    ok, why = live.network_check("https://api.groq.com/openai/v1")
    assert not ok and "egress proxy denied" in why
    assert live.network_check("http://127.0.0.1:8091/v1") == (True, "local")


def test_live_report_never_claims_live_without_execution(registry):
    from apex_one.compute.live import LiveStatus, provider_level_report

    rows = provider_level_report(registry, env={})
    assert rows
    assert all(r["status"] != LiveStatus.LIVE_TESTED for r in rows)


def test_council_scorers_reward_truth_only():
    from apex_one.compute.benchmark import council as c

    assert c.s_reasoning(json.dumps({"date": c.LATEST_SAT}))[0] == 100
    assert c.s_reasoning('{"date": "2026-11-01"}')[0] == 0
    assert c.s_extract(json.dumps(c.EXTRACT_TRUTH))[0] == 100
    assert c.s_extract('{"deadline": "2027-02-01"}')[0] == 25
    assert c.s_long('{"date": "2027-01-20"}')[0] == 100
    assert c.s_egyptian("عشان كده لازم تقدم قبل يوم 15 يعني مش بعده")[0] > c.s_egyptian("يرجى التقديم قبل 15")[0]
    good_html = '<section dir="rtl"><h2>العنوان</h2><p>نص <bdi>IELTS</bdi></p></section>'
    assert c.s_html(good_html)[0] == 100
    assert c.s_html('<section><script></script></section>')[0] < 50


# ---------------------------------------------------------------- vision council


ROLE_JSON = {r: {"score": 80, "observations": ["ok"], "problems": [{"issue": "x", "severity": "MAJOR", "region": "nowhere"}],
                 "suggested_repair": "r", "confidence": 3} for r in
             ("VisualHierarchyJudge", "TypographyJudge", "EditorialDesignJudge", "APEXBrandJudge", "AIClicheJudge",
              "ReaderAttentionJudge")}


def test_parse_review_normalises_and_drops_invalid():
    from apex_one.vision.council import parse_review

    data = dict(ROLE_JSON)
    data["TypographyJudge"] = {"score": 140}
    data["AIClicheJudge"] = "bad"
    out = parse_review("```json\n" + json.dumps(data) + "\n```")
    assert "TypographyJudge" not in out and "AIClicheJudge" not in out
    r = out["VisualHierarchyJudge"]
    assert r["confidence"] == 1.0 and r["problems"][0] == {"issue": "x", "severity": "major", "region": "full"}
    assert parse_review("not json") == {}


def test_page_review_median_and_disagreement():
    from apex_one.vision.council import PageReview

    pr = PageReview("p1", reviews={"a": {"TypographyJudge": {"score": 90}}, "b": {"TypographyJudge": {"score": 50}},
                                   "c": {"TypographyJudge": {"score": 70}}})
    m = pr.role_metric("TypographyJudge")
    assert m.value == 70 and m.status.value == "MEASURED"
    assert pr.role_metric("AIClicheJudge").value is None
    assert pr.disagreements()[0]["role"] == "TypographyJudge"


def test_calibration_flags_a_judge_that_cannot_discriminate(tmp_path):
    from apex_one.vision.council import PageReview, calibrate

    class FakeCouncil:
        models = ["sharp", "blind"]

        def review(self, page_id, png, intent):
            good = page_id == "calibration-good"
            return PageReview(page_id, reviews={
                "sharp": {r: {"score": 85 if good else 40} for r in ROLE_JSON},
                "blind": {r: {"score": 70} for r in ROLE_JSON}})

    res = calibrate(FakeCouncil(), tmp_path / "g.png", {"low_contrast": tmp_path / "b.png",
                                                       "no_hierarchy": tmp_path / "c.png"}, "intent")
    assert res["models"]["sharp"]["reliable"] and res["models"]["sharp"]["discrimination_rate"] == 1.0
    assert not res["models"]["blind"]["reliable"]


# ---------------------------------------------------------------- anti-copy


def _page(items):
    return {"w": 794, "h": 1123, "items": [{"x": x, "y": y, "w": w, "h": h, "fontFamily": "Inter"} for x, y, w, h in items]}


def test_layout_similarity_separates_copies_from_new_compositions():
    from apex_one.design.similarity import REJECT_AT, AntiCopyEngine, grid_iou, occupancy_grid

    a = _page([(60, 60, 670, 200), (60, 300, 670, 600)])
    b = _page([(60, 60, 670, 200), (60, 300, 670, 600)])
    c = _page([(400, 700, 330, 360)])
    assert grid_iou(occupancy_grid(a), occupancy_grid(b)) == 1.0
    assert grid_iou(occupancy_grid(a), occupancy_grid(c)) < 0.4
    ref = {"prev-guide#3": {"grid": occupancy_grid(a), "signature": "s1", "dhash": None}}
    inv = {"palette": {"n": "#0A1A33"}, "fonts": {"latin": "Inter"}}
    v = AntiCopyEngine(inv, ref).check(b, "s2", ["Inter"])
    assert v.verdict == "REJECT" and v.layout_similarity_max >= REJECT_AT and v.nearest == "prev-guide#3"
    assert AntiCopyEngine(inv, ref).check(c, "s3", ["Inter"]).verdict == "OK"


def test_brand_similarity_is_independent_of_layout():
    from apex_one.design.similarity import brand_similarity

    inv = {"palette": {"n": "#0A1A33", "w": "#FFFFFF"}, "fonts": {"latin": "Inter"}}
    on = {"colors": ["rgb(10, 26, 51)", "rgb(255, 255, 255)"], "items": [{"fontFamily": "Inter"}], "hasFooter": True}
    off = {"colors": ["rgb(255, 0, 128)"], "items": [{"fontFamily": "Comic Sans"}], "cardLike": [1, 2, 3, 4]}
    assert brand_similarity(on, inv, []) == 1.0
    assert brand_similarity(off, inv, []) < 0.2


# ---------------------------------------------------------------- genome extraction


def _page_png(path: Path, dark: bool, hero: bool) -> Path:
    im = Image.new("RGB", (595, 842), "#0A1A33" if dark else "#FFFFFF")
    d = ImageDraw.Draw(im)
    ink = "#FFFFFF" if dark else "#0B1424"
    if hero:
        d.rectangle([50, 80, 545, 260], fill=ink)
    for y in range(300, 760, 24):
        d.rectangle([50, y, 545, y + 8], fill=ink)
    d.rectangle([50, 815, 300, 822], fill=ink)
    im.save(path)
    return path


def test_genome_extraction_measures_principles_not_copies(tmp_path):
    from apex_one.design.genome_extraction import derive_principles, extract, ingest

    pages = [_page_png(tmp_path / f"p{i}.png", dark=i == 0, hero=i == 0) for i in range(3)]
    sigs, embs = extract(pages)
    assert [s.tone for s in sigs] == ["dark", "light", "light"]
    assert all(len(e.vector) == 10 + 12 * 16 for e in embs)
    assert 10 < sigs[1].margins_mm["left"] < 25
    pr = {p.name: p.value for p in derive_principles(sigs)}
    assert pr["max_consecutive_dark"] == 1 and set(pr["tone_distribution"]) == {"dark", "light"}
    res = ingest(pages, "approved", tmp_path / "out")
    data = json.loads(Path(res["path"]).read_text())
    assert res["patterns"] == 3 and data["principles"]
    assert "copied" in data["note"]


# ---------------------------------------------------------------- assets + gates

PALETTE = ["#0A1A33", "#FFFFFF", "#A9B3C1"]


def test_svg_validation(tmp_path):
    from apex_one.release.assets import validate_svg

    good = tmp_path / "g.svg"
    good.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect fill="#0A1A33"/></svg>')
    assert validate_svg(good, PALETTE, set()) == []
    bad = tmp_path / "b.svg"
    bad.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/png;base64,AA"/>'
                   '<script/><rect fill="#FF00AA"/></svg>')
    probs = " ".join(validate_svg(bad, PALETTE, set()))
    assert "viewBox" in probs and "raster" in probs and "script" in probs and "palette" in probs
    assert "PLACEHOLDER" in validate_svg(good, PALETTE, {hashlib.sha256(good.read_bytes()).hexdigest()})[0]


def test_repo_assets_are_not_production_ready():
    from apex_one.release.assets import brand_production_metric, validate_assets

    rep = validate_assets()
    assert rep["production_ready"] is False and rep["failures"]
    assert brand_production_metric(rep).value == len(rep["failures"])


def test_brand_gate_blocks_real_jobs_but_not_synthetic_benchmarks():
    from apex_one.qa.court import evaluate_gates

    cfg = {"critical": {"brand_production_assets": {"max": 0, "metric": "brand.production_asset_failures",
                                                    "applies_to": "real_jobs"}}}
    metrics = {"brand.production_asset_failures": Metric.measured("brand.production_asset_failures", 4, "t", unit="count")}
    real = evaluate_gates("J-real", metrics, cfg, [], [], synthetic=False)
    assert not real.release_candidate and any("brand_production_assets" in b for b in real.release_blockers)
    syn = evaluate_gates("J-syn", metrics, cfg, [], [], synthetic=True)
    assert syn.release_candidate and syn.gates[0].status == "NOT_APPLICABLE_SYNTHETIC" and syn.warnings


def test_council_uses_only_calibrated_reliable_judges(tmp_path, monkeypatch):
    from apex_one.vision.council import page_budget, reliable_judges, select_pages

    assert reliable_judges(tmp_path / "none.json")[0] == []
    p = tmp_path / "cal.json"
    p.write_text(json.dumps({"models": {"a": {"reliable": True}, "b": {"reliable": False}, "c": {"reliable": True}}}))
    assert reliable_judges(p)[0] == ["a", "c"]
    assert page_budget("draft") == 0 and page_budget("ultra") > page_budget("standard")
    monkeypatch.setenv("APEX_VISION_COUNCIL_PAGES", "1")
    assert page_budget("draft") == 1
    pages = [{"pageId": "p1", "nodeType": "FundingChapter"}, {"pageId": "p2", "nodeType": "Checklist"},
             {"pageId": "p3", "nodeType": "Cover"}, {"pageId": "p4", "nodeType": "OpportunitySnapshot"}]
    assert select_pages(pages, 3) == ["p3", "p4", "p1"]


def test_council_document_metrics_and_weak_pages():
    from apex_one.vision.council import PageReview, document_metrics, weak_pages

    ok = {r: {"score": 90, "problems": []} for r in ROLE_JSON}
    bad = {r: {"score": 90, "problems": []} for r in ROLE_JSON}
    bad["TypographyJudge"] = {"score": 50, "problems": [{"issue": "tofu glyphs", "severity": "critical", "region": "top"}]}
    reviews = [PageReview("p1", reviews={"m": ok}), PageReview("p2", reviews={"m": bad}), PageReview("p3", reviews={"m": ok})]
    dm = document_metrics(reviews)
    assert dm["TypographyJudge"].name == "design.typography" and dm["TypographyJudge"].value == 90
    assert dm["VisualHierarchyJudge"].name == "council.visual_hierarchy"
    weak = weak_pages(reviews)
    assert list(weak) == ["p2"] and any("critical" in w for w in weak["p2"])


class _FakeBroker:
    """Answers pairwise prompts: 'fair' prefers the page whose image is `good`; 'biased' always says A."""

    def __init__(self, good_b64: str):
        self.good = good_b64

    def complete(self, req, messages, **kw):
        from types import SimpleNamespace

        imgs = messages[0].images_b64_png
        if req.model_id == "fair":
            w = "A" if imgs[0] == self.good else "B"
        else:
            w = "A"
        return SimpleNamespace(executed=True, text=json.dumps({"winner": w, "reason": "r"}),
                               decision=SimpleNamespace(outcome=SimpleNamespace(value="EXECUTED")))


def test_pairwise_counts_only_order_consistent_votes(tmp_path):
    from apex_one.vision.council import encode_png
    from apex_one.vision.pairwise import PairwiseJudge

    good = _page_png(tmp_path / "good.png", dark=False, hero=True)
    bad = _page_png(tmp_path / "bad.png", dark=True, hero=False)
    broker = _FakeBroker(encode_png(good, 640))
    res = PairwiseJudge(broker, ["fair"]).compare(bad, good, "intent")
    assert res.winner == "second" and res.votes == {"fair": "second"}
    biased = PairwiseJudge(broker, ["biased"]).compare(bad, good, "intent")
    assert biased.winner is None and "position bias" in biased.disagreements[0]
    # one consistent vote out of two judges is not a strict majority
    assert PairwiseJudge(broker, ["fair", "biased"]).compare(bad, good, "intent").winner is None


def test_ultra_candidate_budget(monkeypatch):
    from apex_one.core.governor.governor import MODE_PARAMS, ultra_candidates
    from apex_one.core.schemas.mission import QualityMode

    assert MODE_PARAMS[QualityMode.ULTRA]["initial_important"] == 64
    assert ultra_candidates(64) == 64
    monkeypatch.setenv("APEX_ULTRA_CANDIDATES", "512")
    assert ultra_candidates(64) == 256
    monkeypatch.setenv("APEX_ULTRA_CANDIDATES", "128")
    assert ultra_candidates(64) == 128


def test_abc_record_validation():
    from apex_one.memory.preference import APEXPreferenceRecord, validate_record

    ok = APEXPreferenceRecord(job_id="J", page_id="P", labels={"A": "1", "B": "2", "C": "3"}, ranking=["B", "A", "C"],
                              winner="B", reason="clearer deadline", tags=["hierarchy", "numbers"], annotator="dir")
    assert validate_record(ok) == []
    bad = ok.model_copy(update={"ranking": ["B", "A"], "winner": "A", "tags": ["vibes"], "reason": " "})
    assert len(validate_record(bad)) == 4


def _row(system, ptype, val, critical=False, contract=()):
    return {"system": system, "page_type": ptype, "produced": True, "critical": critical, "contract": list(contract),
            "metrics": {m: val for m in ("design.hierarchy", "design.typography", "design.brand_fit")}}


def test_moe_routes_by_measured_evidence_and_semantic_family(registry):
    from apex_one.design.models.moe import DesignMoE

    rows = [_row("native-tournament", "Timeline", 92), _row("native-baseline", "Timeline", 80),
            _row("llm:gemma-multimodal", "Timeline", 99), _row("llm:qwen-vl-current", "Timeline", 100, critical=True),
            _row("native-baseline", "Cover", 95), _row("native-tournament", "Cover", 90)]
    moe = DesignMoE(registry, rows, k=2)
    ev = moe.route("Timeline", purpose="evaluation")
    assert ev.gate == "exact-type" and ev.experts == ["llm:gemma-multimodal", "native-tournament"]
    prod = moe.route("Timeline", purpose="production")      # UNKNOWN licences never route for production
    assert prod.experts == ["native-tournament", "native-baseline"] and "llm:gemma-multimodal" in prod.excluded
    fam = moe.route("Checklist", purpose="production")      # no Checklist evidence -> same reading family (scan)
    assert fam.gate == "family" and fam.experts[0] == "native-tournament"
    assert moe.route("Breath").experts[0] == "native-baseline"   # glance family evidence (Cover)
    assert DesignMoE(registry, [], k=2).route("Closing").gate == "default"


def test_arabic_typography_rules():
    from apex_one.qa.typography import check_arabic_typography

    def item(**kw):
        base = {"id": "b", "role": "paragraph", "text": "النص العربي هنا", "fontPx": 16, "lineHeightPx": 28, "lines": 3,
                "letterSpacing": "normal", "fontStyle": "normal"}
        return {**base, **kw}

    clean, m = check_arabic_typography({"pageId": "p", "items": [item()]})
    assert clean == [] and m["typography.arabic"].value == 100
    issues, m = check_arabic_typography({"pageId": "p", "items": [
        item(letterSpacing="1.92px"), item(fontStyle="italic"), item(lineHeightPx=22),
        item(text="هل تقدر?  ده مهم, جداً"), item(text="مـــهم")]})
    checks = {i.check for i in issues}
    assert checks == {"qa.arabic_letter_spacing", "qa.arabic_italic", "qa.arabic_leading", "qa.arabic_punctuation",
                      "qa.arabic_tatweel"}
    assert any(i.severity == "critical" for i in issues) and m["typography.arabic"].value < 60
    ok, _ = check_arabic_typography({"pageId": "p", "items": [item(text="قدّم الـ tuition والـ deadline")]})
    assert ok == []    # «الـ» before a Latin term is the accepted convention, not stretching
    _, m = check_arabic_typography({"pageId": "p", "items": [item(text="English only")]})
    assert m["typography.arabic"].value is None


def test_reports_print_pending_instead_of_numbers():
    from apex_one.lab.reports import design_bench_md, live_provider_md

    assert "NOT_MEASURED" in live_provider_md(None)
    assert "NOT_MEASURED" in design_bench_md(None, [], None)
    rows = [{"provider": "groq", "status": "NETWORK_BLOCKED", "network": "egress proxy denied CONNECT"},
            {"provider": "llamacpp_local", "model": "m", "status": "LIVE_TESTED", "structured_correct": True,
             "structured_ms": 4594.8, "structured_output": "{}", "cost_basis": "local"}]
    md = live_provider_md(rows)
    assert "**NETWORK_BLOCKED**" in md and "4.6 s" in md and "LIVE_TESTED 1" in md


def test_model_activation_report_marks_unrun_models_pending(registry, tmp_path):
    from apex_one.compute.local.acquisition import LocalModelSpec
    from apex_one.lab.reports import model_activation_md

    class Spec(LocalModelSpec):
        @property
        def dir(self):
            return tmp_path / self.key

    spec = Spec(key="k", registry_model="gemma-multimodal", repository="ai/x", tag="t", port=1)
    md = model_activation_md({"k": spec}, None, None, None, registry)
    assert "NOT ACQUIRED" in md and "PENDING" in md and "LIVE_TESTED" not in md.split("## General")[0].split("|---|")[-1]


def test_moe_holds_default_on_saturated_evidence(registry):
    from apex_one.design.models.moe import DesignMoE

    rows = [_row("native-baseline", "Cover", 100), _row("native-tournament", "Cover", 99.2)]
    ch = DesignMoE(registry, rows).route("Cover")
    assert ch.experts[0] == "native-tournament" and "default-held" in ch.gate
