"""add gear.name + gear.field_confidences_json

Revision ID: 0002_gear_name_and_field_confidences
Revises: 0001_initial_gear
Create Date: 2026-04-27
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_gear_name_and_field_confidences"
down_revision: str | None = "0001_initial_gear"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite needs batch mode for ALTER TABLE ADD COLUMN with constraints/defaults.
    with op.batch_alter_table("gear") as batch:
        batch.add_column(sa.Column("name", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column(
                "field_confidences_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("gear") as batch:
        batch.drop_column("field_confidences_json")
        batch.drop_column("name")
