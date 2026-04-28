"""Alembic environment.

Resolves the DB URL at runtime from `app.config.settings()` so a single
`alembic upgrade head` works against whatever path `BHC_DB_PATH` points at.

Imports `app.models` to ensure every ORM model has registered its table on
`Base.metadata` before autogenerate runs.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make `app.*` importable. `apps/api/alembic/env.py` → `apps/api/` is parent[1].
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.config import settings  # noqa: E402
from app.models import Base  # noqa: E402  (registers tables on Base.metadata)

config = context.config

# The placeholder URL in `alembic.ini` is meaningful: when alembic is invoked
# directly (e.g. `make migrate`), env.py rewrites it from `app.config.settings()`
# so the migration always lands on the configured `BHC_DB_PATH`. Tests set
# `BHC_DB_PATH` first (clearing the settings cache) so this code path picks up
# the tmp DB transparently.
#
# Callers that want to point alembic at a *different* URL than settings would
# yield can use `Config.set_main_option("sqlalchemy.url", ...)` with any URL
# that isn't the placeholder — we leave non-placeholder values untouched.
_PLACEHOLDER_URL = "sqlite:///../../data/personal.db"
_current_url = config.get_main_option("sqlalchemy.url", "")
if _current_url in ("", _PLACEHOLDER_URL):
    cfg = settings()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{cfg.db_path.as_posix()}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL scripts without an actual DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
