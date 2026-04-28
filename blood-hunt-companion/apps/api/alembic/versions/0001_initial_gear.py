"""initial gear table

Revision ID: 0001_initial_gear
Revises:
Create Date: 2026-04-27
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_gear"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gear",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slot", sa.String(length=32), nullable=False),
        sa.Column("hero_id", sa.String(length=64), nullable=True),
        sa.Column("rarity", sa.String(length=16), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("base_effect", sa.String(length=64), nullable=False),
        sa.Column("base_value", sa.Float(), nullable=False),
        sa.Column("extended_effects_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_screenshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column(
            "parsed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("is_equipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_gear_slot", "gear", ["slot"])
    op.create_index("ix_gear_hero_id", "gear", ["hero_id"])
    op.create_index("ix_gear_rarity", "gear", ["rarity"])


def downgrade() -> None:
    op.drop_index("ix_gear_rarity", table_name="gear")
    op.drop_index("ix_gear_hero_id", table_name="gear")
    op.drop_index("ix_gear_slot", table_name="gear")
    op.drop_table("gear")
