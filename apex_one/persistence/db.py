"""Engine/session management and migrations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from apex_one.settings import REPO_ROOT, get_settings


@lru_cache(maxsize=8)
def _engine_for(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, future=True, connect_args={"check_same_thread": False})
    return create_engine(url, future=True, pool_pre_ping=True)


def get_engine(url: str | None = None) -> Engine:
    return _engine_for(url or get_settings().database_url)


def run_migrations(url: str | None = None) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url or get_settings().database_url)
    command.upgrade(cfg, "head")


def init_db(url: str | None = None) -> Engine:
    """Bring the database to the latest migration."""
    run_migrations(url)
    return get_engine(url)


def db_ready(url: str | None = None) -> bool:
    try:
        insp = inspect(get_engine(url))
        return "jobs" in insp.get_table_names() and "alembic_version" in insp.get_table_names()
    except Exception:
        return False


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    factory = sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
