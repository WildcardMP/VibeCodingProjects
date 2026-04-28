"""Alembic migration tests — `upgrade head` produces a schema that matches the
ORM model, and `downgrade base` removes it cleanly.

These tests exercise the same Alembic config the user runs via `make migrate`.
We redirect the DB target by setting `BHC_DB_PATH` before clearing the settings
cache, which `env.py` then reads on next invocation.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.config import settings as settings_factory

API_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_ROOT / "alembic.ini"


@pytest.fixture
def alembic_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Config, Path]]:
    """Yield (alembic_config, db_path) targeting an isolated tmp DB."""
    db_path = tmp_path / "alembic_test.db"
    monkeypatch.setenv("BHC_DB_PATH", str(db_path))
    monkeypatch.setenv("BHC_REPO_ROOT", str(tmp_path))  # avoid touching real repo paths
    settings_factory.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    # Leave sqlalchemy.url at the placeholder so env.py auto-resolves from settings.

    yield cfg, db_path

    settings_factory.cache_clear()


def test_upgrade_creates_gear_table_and_indexes(
    alembic_db: tuple[Config, Path],
) -> None:
    cfg, db_path = alembic_db
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "gear" in tables
    assert "alembic_version" in tables

    columns = {c["name"] for c in insp.get_columns("gear")}
    expected = {
        "id", "slot", "hero_id", "rarity", "level", "base_effect", "base_value",
        "extended_effects_json", "source_screenshot", "ocr_confidence", "parsed_at",
        "is_equipped", "notes",
    }
    assert expected <= columns

    index_names = {i["name"] for i in insp.get_indexes("gear")}
    assert {"ix_gear_slot", "ix_gear_hero_id", "ix_gear_rarity"} <= index_names


def test_downgrade_to_base_removes_gear_table(
    alembic_db: tuple[Config, Path],
) -> None:
    cfg, db_path = alembic_db
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    insp = inspect(engine)
    assert "gear" not in set(insp.get_table_names())


def test_orm_metadata_matches_migration(
    alembic_db: tuple[Config, Path],
) -> None:
    """Catch drift between hand-written migration and SQLAlchemy ORM definitions.

    Apply the migration, introspect the resulting schema, then confirm every
    column on `GearORM.__table__` is present with the expected nullability.
    """
    from app.models.gear import GearORM

    cfg, db_path = alembic_db
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    insp = inspect(engine)
    db_cols = {c["name"]: c for c in insp.get_columns("gear")}
    for col in GearORM.__table__.columns:
        assert col.name in db_cols, f"ORM column {col.name} missing from migration"
        assert db_cols[col.name]["nullable"] == col.nullable, (
            f"nullability mismatch for {col.name}: "
            f"orm={col.nullable} db={db_cols[col.name]['nullable']}"
        )
