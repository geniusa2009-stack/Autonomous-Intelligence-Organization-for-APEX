"""Runtime settings. Secrets are read from the environment and never persisted."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    home: Path
    config_dir: Path
    voice_dir: Path
    artifacts_dir: Path
    database_url: str
    chromium_path: str | None
    live_tests: bool
    env_policy_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def jobs_dir(self) -> Path:
        return self.artifacts_dir / "jobs"


POLICY_ENV_KEYS = (
    "APEX_MAX_API_COST_USD",
    "APEX_PAID_FALLBACK_ALLOWED",
    "APEX_AUTO_BILLING_ALLOWED",
    "APEX_AUTO_UPGRADE_ALLOWED",
    "APEX_QUOTA_BYPASS_ALLOWED",
)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    home = Path(os.environ.get("APEX_HOME", REPO_ROOT)).resolve()
    _load_dotenv(home / ".env")
    artifacts = Path(os.environ.get("APEX_ARTIFACTS_DIR", home / "artifacts"))
    if not artifacts.is_absolute():
        artifacts = home / artifacts
    db_url = os.environ.get("APEX_DATABASE_URL", f"sqlite:///{home / 'var' / 'apex_one.db'}")
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        rel = db_url.removeprefix("sqlite:///")
        if not Path(rel).is_absolute():
            db_url = f"sqlite:///{home / rel}"
    return Settings(
        home=home,
        config_dir=Path(os.environ.get("APEX_CONFIG_DIR", home / "config")),
        voice_dir=Path(os.environ.get("APEX_VOICE_DIR", home / "voice")),
        artifacts_dir=artifacts,
        database_url=db_url,
        chromium_path=os.environ.get("APEX_CHROMIUM_PATH") or None,
        live_tests=os.environ.get("APEX_LIVE_TESTS", "0") == "1",
        env_policy_overrides={k: os.environ[k] for k in POLICY_ENV_KEYS if k in os.environ},
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
