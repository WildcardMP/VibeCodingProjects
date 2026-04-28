"""rarity rename, base_effects list, rating + hero columns

Revision ID: 0003_vocabulary_corrections
Revises: 0002_gear_name_and_field_confidences
Create Date: 2026-04-27

Aligns the gear schema with the in-game tooltip after user-confirmed
screenshots:

* `rarity` values renamed: 'common' → 'normal', 'uncommon' → 'advanced'.
  No production data exists yet, but the UPDATE runs anyway so any DB
  populated from prior dev sessions migrates cleanly.
* `base_effect` (scalar str) + `base_value` (scalar float) collapsed into
  a single `base_effects_json` TEXT column holding `[{"name", "value"}, ...]`.
  Existing rows have their old pair preserved as a one-element list.
* New columns: `rating` (INTEGER, default 0) and `hero` (TEXT, nullable)
  for the tooltip overall rating and the in-game hero display name.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_vocabulary_corrections"
down_revision: str | None = "0002_gear_name_and_field_confidences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RARITY_RENAMES: dict[str, str] = {
    "common": "normal",
    "uncommon": "advanced",
}


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Rename rarity values --------------------------------------------------
    for old, new in _RARITY_RENAMES.items():
        bind.execute(
            sa.text("UPDATE gear SET rarity = :new WHERE rarity = :old"),
            {"new": new, "old": old},
        )

    # --- 2. Add new columns + base_effects_json ----------------------------------
    # SQLite needs batch mode for ALTER TABLE on existing rows. We add the new
    # columns first, backfill base_effects_json, then drop the old scalar
    # columns inside a second batch (separate batches keep the diff readable).
    with op.batch_alter_table("gear") as batch:
        batch.add_column(
            sa.Column(
                "base_effects_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch.add_column(
            sa.Column(
                "rating",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("hero", sa.String(length=64), nullable=True))

    # --- 3. Backfill base_effects_json from old (base_effect, base_value) pair ---
    rows = bind.execute(
        sa.text("SELECT id, base_effect, base_value FROM gear")
    ).fetchall()
    for row in rows:
        payload = json.dumps([{"name": row.base_effect, "value": row.base_value}])
        bind.execute(
            sa.text("UPDATE gear SET base_effects_json = :p WHERE id = :id"),
            {"p": payload, "id": row.id},
        )

    # --- 4. Drop the old scalar base columns --------------------------------------
    with op.batch_alter_table("gear") as batch:
        batch.drop_column("base_value")
        batch.drop_column("base_effect")


def downgrade() -> None:
    bind = op.get_bind()

    # Re-add the scalar columns first so we can backfill before they go NOT NULL.
    with op.batch_alter_table("gear") as batch:
        batch.add_column(
            sa.Column("base_effect", sa.String(length=64), nullable=True)
        )
        batch.add_column(sa.Column("base_value", sa.Float(), nullable=True))

    rows = bind.execute(sa.text("SELECT id, base_effects_json FROM gear")).fetchall()
    for row in rows:
        try:
            effects = json.loads(row.base_effects_json or "[]")
        except json.JSONDecodeError:
            effects = []
        first = effects[0] if effects else {"name": "", "value": 0.0}
        bind.execute(
            sa.text(
                "UPDATE gear SET base_effect = :n, base_value = :v WHERE id = :id"
            ),
            {"n": first.get("name", ""), "v": float(first.get("value", 0.0)), "id": row.id},
        )

    # Tighten NOT NULL on the restored columns and drop the new ones.
    with op.batch_alter_table("gear") as batch:
        batch.alter_column("base_effect", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("base_value", existing_type=sa.Float(), nullable=False)
        batch.drop_column("hero")
        batch.drop_column("rating")
        batch.drop_column("base_effects_json")

    for old, new in _RARITY_RENAMES.items():
        # Reverse the upgrade mapping: 'normal' -> 'common', 'advanced' -> 'uncommon'.
        bind.execute(
            sa.text("UPDATE gear SET rarity = :old WHERE rarity = :new"),
            {"old": old, "new": new},
        )
