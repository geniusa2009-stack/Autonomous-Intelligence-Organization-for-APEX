import random

import httpx
import pytest

from apex_one.core.schemas.compute import Availability
from apex_one.core.schemas.document import NodeType
from apex_one.core.schemas.quality import QAIssue
from apex_one.design.genome import load_genome, sample_genes
from apex_one.design.intent import derive_intent
from apex_one.design.models import DesignNotSupported, DesignRouter, build_design_adapters
from apex_one.design.mutation import OPERATORS, crossover, mutate
from apex_one.design.repair import classify, repair_genes
from apex_one.document.compiler import compile_document, compile_page, structural_signature
from tests.helpers import editorial


@pytest.fixture(scope="module")
def ed():
    return editorial()


def test_genome_invariants_and_sampling(ed):
    g = load_genome()
    assert g.invariants["palette"]["navy_900"] and g.invariants["forbidden"]["gradients"]
    cover = ed["ast"].pages()[0]
    intent = derive_intent(cover)
    rng = random.Random(1)
    for _ in range(20):
        genes = sample_genes(g, intent, rng)
        assert genes.archetype == "cover-monument"   # strict for covers
        assert 14.5 <= genes.base_font_px <= 18.5


def test_mutation_never_touches_invariants(ed):
    g = load_genome()
    rng = random.Random(2)
    genes = sample_genes(g, derive_intent(ed["ast"].pages()[2]), rng)
    for op in OPERATORS + ["tone"]:
        m = mutate(genes, op, g, rng)
        assert set(m.model_dump()) == set(genes.model_dump())
    c = crossover(genes, mutate(genes, "grid", g, rng), rng)
    assert c.archetype in g.gene_space["archetype"]


def test_compiler_binds_facts_and_isolates_bidi(ed):
    g = load_genome()
    locks = {lk.slot: lk for lk in ed["locks"]}
    pages = ed["ast"].pages()
    rng = random.Random(3)
    compiled = [compile_page(n, sample_genes(g, derive_intent(n), rng), g, locks, page_no=i, total_pages=len(pages),
                             synthetic=True) for i, n in enumerate(pages, 1)]
    html = compile_document(compiled, g, title="t", synthetic=True)
    assert '<html lang="ar" dir="rtl">' in html
    assert 'data-slot="deadline.application"' in html and locks["deadline.application"].lock_hash in html
    assert '<bdi class="term" dir="ltr" lang="en">' in html
    for bad in ("linear-gradient", "box-shadow:0", "border-radius:12"):
        assert bad not in html
    assert "SYNTHETIC" in html


def test_structural_signature_changes_with_structure(ed):
    g = load_genome()
    n = ed["ast"].pages()[2]
    a = sample_genes(g, derive_intent(n), random.Random(4))
    b = a.model_copy(update={"archetype": "ledger" if a.archetype != "ledger" else "split-asymmetric"})
    assert structural_signature(n, a) != structural_signature(n, b)


def test_repair_targets_failure_kind():
    g = load_genome()
    from apex_one.core.schemas.design import Genes

    genes = Genes(base_font_px=18, density=0.4, whitespace=0.7)
    fixed, applied = repair_genes(genes, [QAIssue(check="qa.overflow", severity="critical", message="x")], g)
    assert fixed.base_font_px < 18 and fixed.density > 0.4 and applied
    assert classify([QAIssue(check="qa.rtl_direction", severity="critical", message="x")]) == ["RTL"]


def test_design_router_falls_back_to_native_without_eligible_specialist(registry):
    router = DesignRouter(registry, build_design_adapters(registry, env={}))
    route = router.route_for("FundingChapter")
    assert route.route_name == "dense_information"
    choice = next(s for s in route.steps if s.step == "graphic_layout")
    assert choice.engine == "apex-native-layout" and choice.native
    assert any(c["model"] == "PosterCopilot-7B" and c["availability"] == "CONFIGURATION_REQUIRED" for c in choice.considered)
    # cover route includes svg_generation, dense route does not send pages through every model
    assert "svg_generation" in [s.step for s in router.route_for("Cover").steps]
    assert "svg_generation" not in [s.step for s in route.steps]


def test_specialist_used_only_when_available_and_licence_verified(registry):
    from datetime import UTC, datetime

    from apex_one.core.schemas.compute import LicenseRecord, ProductionState

    env = {"APEX_DESIGN_ENDPOINT_POSTERCOPILOT": "http://gpu-box:8000"}
    adapters = build_design_adapters(registry, env=env)
    router = DesignRouter(registry, adapters)
    assert router.choose("graphic_layout").engine == "apex-native-layout"     # licence UNKNOWN -> not production
    registry.licenses["lic-postercopilot"] = LicenseRecord(id="lic-postercopilot", license_name="Apache-2.0",
                                                           production_state=ProductionState.PRODUCTION_ALLOWED,
                                                           verified_at=datetime.now(UTC), verified_by="test")
    assert router.choose("graphic_layout").engine == "PosterCopilot-7B"
    research_router = DesignRouter(registry, adapters, purpose="research")
    assert research_router.choose("graphic_layout").engine == "PosterCopilot-7B"


def test_openai_design_endpoint_adapter_mocked(registry):
    from datetime import UTC, datetime

    from apex_one.core.schemas.compute import LicenseRecord, ProductionState

    registry.licenses["lic-postercopilot"] = LicenseRecord(id="lic-postercopilot", license_name="test",
                                                           production_state=ProductionState.PRODUCTION_ALLOWED,
                                                           verified_at=datetime.now(UTC), verified_by="test")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content":
        'here: {"regions":[{"block_id":"B-1","col":1,"span":8,"row":1,"rows":3}]}'}}]}))
    ad = build_design_adapters(registry, transport=transport, env={"APEX_DESIGN_ENDPOINT_POSTERCOPILOT": "http://x"})
    res = ad["PosterCopilot-7B"].invoke("graphic_layout", {"spec": {"blocks": []}})
    assert res.output["regions"][0]["span"] == 8
    with pytest.raises(DesignNotSupported):
        ad["PosterCraft"].invoke("poster_asset", {})
    assert ad["LayerD"].availability()[0] == Availability.UNAVAILABLE


def test_intent_rationale_and_archetypes(ed):
    for n in ed["ast"].pages():
        i = derive_intent(n)
        assert i.archetype_preferences and i.rationale
        if n.semantic_type == NodeType.BREATH:
            assert i.archetype_preferences == ["quiet-breath"]
