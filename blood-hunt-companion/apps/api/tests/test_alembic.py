"""Alembic migration tests — `upgrade head` produces a schema that matches the
ORM model, and `downgrade base` removes it cleanly.

These tests exercise the same Alembic config the user runs via `make migrate`.
We redirect the DB target by setting `BHC_DB_PATH` before clearing the settings
cache, which `env.py` then reads on next invocation.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

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
        "id", "name", "slot", "hero", "hero_id", "rarity", "level", "rating",
        "base_effects_json", "extended_effects_json", "source_screenshot",
        "ocr_confidence", "field_confidences_json", "parsed_at",
        "is_equipped", "notes",
    }
    assert expected <= columns
    # Old scalar base columns must be gone after the 0003 migration.
    assert "base_effect" not in columns
    assert "base_value" not in columns

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


def test_0003_renames_rarity_and_collapses_base_effect(
    alembic_db: tuple[Config, Path],
) -> None:
    """Spin up a DB at 0002, hand-insert old-vocab rows, then upgrade to 0003.

    Verifies the migration renames `common`→`normal` / `uncommon`→`advanced`
    and folds the scalar `base_effect`/`base_value` pair into the new
    `base_effects_json` list, even when production data exists.
    """
    cfg, db_path = alembic_db
    command.upgrade(cfg, "0002_gear_name_and_field_confidences")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gear (slot, rarity, level, base_effect, base_value, "
                "extended_effects_json) VALUES (:s, :r, :l, :be, :bv, '[]')"
            ),
            [
                {"s": "armor", "r": "common", "l": 1, "be": "HP", "bv": 100.0},
                {"s": "weapon", "r": "uncommon", "l": 30, "be": "Precision Damage", "bv": 200.0},
                {"s": "armor", "r": "legendary", "l": 60, "be": "Health", "bv": 2419.0},
            ],
        )

    command.upgrade(cfg, "0003_vocabulary_corrections")

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT slot, rarity, base_effects_json, rating, hero FROM gear ORDER BY id")
        ).fetchall()

    assert [r.rarity for r in rows] == ["normal", "advanced", "legendary"]
    # Every old (base_effect, base_value) pair should round-trip into a
    # single-element list.
    payloads = [json.loads(r.base_effects_json) for r in rows]
    assert payloads == [
        [{"name": "HP", "value": 100.0}],
        [{"name": "Precision Damage", "value": 200.0}],
        [{"name": "Health", "value": 2419.0}],
    ]
    # New columns default cleanly.
    assert [r.rating for r in rows] == [0, 0, 0]
    assert [r.hero for r in rows] == [None, None, None]


def test_0003_downgrade_restores_scalar_columns(
    alembic_db: tuple[Config, Path],
) -> None:
    """Round-trip: upgrade head, insert a row, downgrade to 0002, verify."""
    cfg, db_path = alembic_db
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    payload = json.dumps([{"name": "Precision Damage", "value": 8300.0}])
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gear (slot, rarity, level, rating, hero, "
                "base_effects_json, extended_effects_json) "
                "VALUES (:s, :r, :l, :rt, :h, :be, '[]')"
            ),
            {
                "s": "weapon",
                "r": "legendary",
                "l": 60,
                "rt": 7086,
                "h": "Moon Knight",
                "be": payload,
            },
        )

    command.downgrade(cfg, "0002_gear_name_and_field_confidences")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT rarity, base_effect, base_value FROM gear")
        ).fetchone()
    assert row is not None
    # Downgrade reverts the rarity rename.
    assert row.rarity == "legendary"  # unchanged because not in rename set
    assert row.base_effect == "Precision Damage"
    assert row.base_value == 8300.0
