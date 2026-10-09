import os
import shutil
from pathlib import Path

import pytest

from apex_one.settings import REPO_ROOT, reset_settings_cache


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own DB + artifacts dir; real config/voice from the repo."""
    monkeypatch.setenv("APEX_HOME", str(REPO_ROOT))
    monkeypatch.setenv("APEX_DATABASE_URL", f"sqlite:///{tmp_path / 'apex.db'}")
    monkeypatch.setenv("APEX_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    for k in ("NVIDIA_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN",
              "HF_TOKEN", "SEARXNG_URL", "VLLM_BASE_URL", "SGLANG_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    reset_settings_cache()
    yield tmp_path
    reset_settings_cache()


@pytest.fixture
def registry():
    from apex_one.compute.registry import load_registry

    return load_registry(with_db_overlay=False)


def chromium_available() -> bool:
    from apex_one.compute.hardware import find_chromium

    return find_chromium() is not None


requires_browser = pytest.mark.skipif(not chromium_available(), reason="Chromium not available")
