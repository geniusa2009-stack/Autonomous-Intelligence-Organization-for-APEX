"""Every model/system named in the APEX ONE ULTRA specification must be represented."""

import yaml

from apex_one.core.schemas.compute import IntegrationStatus
from apex_one.settings import REPO_ROOT

SPEC_GENERAL = [
    "nemotron-3-ultra-550b-a55b", "nemotron-3-super-120b-a12b", "nemotron-nano-omni", "gpt-oss-120b", "gpt-oss-20b",
    "qwen-27b-class", "qwen-reasoning-coding-current", "qwen-vl-current", "kimi-k2.5", "kimi-k3-family", "glm-5.x",
    "minimax-m2.x", "minimax-m3-family", "gemini-flash-free", "gemma-multimodal", "aya-expanse-32b",
    "future-open-weight-slot",
]
SPEC_DESIGN = [
    "OmniDocLayout-LLM", "PosterO", "Scan-and-Print", "Uni-Layout", "PosterCopilot-7B", "SEGA-7B", "SEGA-13B",
    "WebGenAgent-LM-7B", "WebGenAgent-LM-8B", "WebGenAgent-Step-GRPO", "ScreenCoder", "DCGen", "MarkupDM",
    "PosterReward", "LayerD", "OmniSVG-4B", "OmniSVG-8B", "StarVector-1B", "StarVector-8B", "PosterOmni",
    "PosterCraft", "PosterMaker", "PosterVerse", "PosterGen", "BannerAgency", "SlidePoise", "SlideGen",
    "Qwen-Image-2.1", "UI-TARS-2", "GraphicDesignBench",
]


def test_all_spec_models_in_model_registry(registry):
    for mid in SPEC_GENERAL + SPEC_DESIGN:
        assert mid in registry.models, mid


def test_all_design_models_in_capability_matrix_and_license_registry(registry):
    matrix_models = set()
    for spec in registry.design_matrix["roles"].values():
        matrix_models.update(spec["specialists"])
    for mid in SPEC_DESIGN:
        assert mid in matrix_models, f"{mid} missing from design_capability_matrix.yaml"
        assert registry.models[mid].license_ref in registry.licenses, mid


def test_unknown_licences_are_not_production(registry):
    for lic in registry.licenses.values():
        if lic.production_state.value == "PRODUCTION_ALLOWED":
            assert lic.verified_at is not None, lic.id
        if lic.verified_at is None:
            assert not lic.production_allowed


def test_no_external_model_is_production_allowed_without_verification(registry):
    for mid in SPEC_GENERAL + SPEC_DESIGN:
        if registry.production_allowed(mid):
            lic = registry.license_for(mid)
            # only via a recorded verification: artifact evidence (license_verifications.yaml) or a human
            assert lic.verified_at is not None and lic.verified_by, mid
            assert lic.license_name in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause") or "human" in str(
                lic.verified_by), (mid, lic.license_name)


def test_aya_is_research_only(registry):
    assert registry.models["aya-expanse-32b"].integration_status == IntegrationStatus.RESEARCH_ONLY
    assert registry.license_for("aya-expanse-32b").production_state.value == "NON_COMMERCIAL"


def test_no_adapter_claims_implemented_without_code(registry):
    """IMPLEMENTED is reserved for engines whose code runs in this repository's tests."""
    for m in registry.models.values():
        if m.integration_status == IntegrationStatus.IMPLEMENTED:
            assert m.family in ("apex-native", "mock"), m.id


def test_config_files_parse():
    for name in ("providers.yaml", "model_registry.yaml", "license_registry.yaml", "design_capability_matrix.yaml",
                 "quality_gates.yaml", "apex_brand.yaml", "voice.yaml", "readers.yaml"):
        data = yaml.safe_load((REPO_ROOT / "config" / name).read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
