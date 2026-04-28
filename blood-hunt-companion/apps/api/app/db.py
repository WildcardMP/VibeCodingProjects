"""Database engine, session factory, and FastAPI dependency.

The app is local-only (single user, single SQLite file) so we use a synchronous
SQLAlchemy 2.0 engine — no async machinery, no connection pool tuning. The DB
lives at `data/personal.db` by default; override via `BHC_DB_PATH` env var.

Tests build a separate engine against `sqlite:///:memory:` (or a tmp path) and
override the FastAPI dependency, so production code never sees fixture state.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

log = logging.getLogger(__name__)


def _sqlite_url(db_path: Path) -> str:
    """Build a SQLAlchemy URL for a SQLite file path. Always forward-slashed."""
    return f"sqlite:///{db_path.as_posix()}"


def make_engine(url: str | None = None) -> Engine:
    """Build a synchronous Engine. Tests pass an explicit URL; prod uses settings."""
    if url is None:
        cfg = settings()
        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        url = _sqlite_url(cfg.db_path)
    log.info("Building DB engine for %s", url)
    # `check_same_thread=False` is needed because FastAPI may dispatch handlers
    # across worker threads while sharing the same Connection. We rely on the
    # session-per-request pattern below to keep concurrent access safe.
    return create_engine(url, future=True, connect_args={"check_same_thread": False})


@lru_cache(maxsize=1)
def _engine_singleton() -> Engine:
    return make_engine()


@lru_cache(maxsize=1)
def _sessionmaker_singleton() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine_singleton(), expire_on_commit=False, future=True)


def reset_singletons() -> None:
    """Drop cached engine + sessionmaker — used by tests that swap the DB URL."""
    _engine_singleton.cache_clear()
    _sessionmaker_singleton.cache_clear()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context-manager wrapper for direct script use (Alembic env, REPL, tests)."""
    sm = _sessionmaker_singleton()
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Yields a session, commits on success, rolls back on error."""
    sm = _sessionmaker_singleton()
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
