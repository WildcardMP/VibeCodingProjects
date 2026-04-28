"""Gear ORM model — mirror of the SQL schema in PROJECT.md §7.

Pydantic ↔ ORM conversion lives here so the router doesn't have to know JSON
encoding details. `extended_effects` is stored as a TEXT JSON blob because
SQLite has no native JSON column type and the field is small (≤4 entries) — a
relational `extended_effects` table would be overkill for the access pattern
(always read with the parent row, never queried independently).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..schemas.common import GearSlot, Rarity
from ..schemas.gear import ExtendedEffect, GearPiece, ParsedGear
from .base import Base


def _now_utc() -> datetime:
    return datetime.now(UTC)


class GearORM(Base):
    __tablename__ = "gear"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    slot: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    hero_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rarity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    base_effect: Mapped[str] = mapped_column(String(64), nullable=False)
    base_value: Mapped[float] = mapped_column(Float, nullable=False)
    extended_effects_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_screenshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    field_confidences_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    is_equipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ---------- conversion helpers ----------
    @staticmethod
    def _dump_extended(effects: list[ExtendedEffect]) -> str:
        # `mode="json"` ensures Pydantic types (e.g. Literal) serialize to plain JSON.
        return json.dumps([e.model_dump(mode="json") for e in effects])

    @staticmethod
    def _load_extended(blob: str) -> list[ExtendedEffect]:
        if not blob:
            return []
        raw: Any = json.loads(blob)
        if not isinstance(raw, list):
            return []
        return [ExtendedEffect.model_validate(item) for item in raw]

    @staticmethod
    def _dump_field_confidences(d: dict[str, float]) -> str:
        return json.dumps(d)

    @staticmethod
    def _load_field_confidences(blob: str) -> dict[str, float]:
        if not blob:
            return {}
        raw: Any = json.loads(blob)
        if not isinstance(raw, dict):
            return {}
        return {str(k): float(v) for k, v in raw.items()}

    @classmethod
    def from_parsed(cls, parsed: ParsedGear) -> GearORM:
        """Build a fresh ORM row from an OCR-parsed (or hand-edited) gear payload."""
        return cls(
            name=parsed.name,
            slot=parsed.slot,
            hero_id=parsed.hero_id,
            rarity=parsed.rarity,
            level=parsed.level,
            base_effect=parsed.base_effect,
            base_value=parsed.base_value,
            extended_effects_json=cls._dump_extended(parsed.extended_effects),
            source_screenshot=parsed.source_screenshot,
            ocr_confidence=parsed.overall_confidence,
            field_confidences_json=cls._dump_field_confidences(parsed.field_confidences),
        )

    def to_pydantic(self) -> GearPiece:
        # Columns with Python-side defaults (`default=...`) are applied at flush
        # time, so a freshly-constructed unflushed row returns `None` here. We
        # coerce to the schema defaults to keep `to_pydantic()` safe to call on
        # both pre- and post-flush instances.
        return GearPiece(
            id=self.id,
            name=self.name,
            slot=cast_slot(self.slot),
            hero_id=self.hero_id,
            rarity=cast_rarity(self.rarity),
            level=self.level,
            base_effect=self.base_effect,
            base_value=self.base_value,
            extended_effects=self._load_extended(self.extended_effects_json or "[]"),
            overall_confidence=self.ocr_confidence or 0.0,
            field_confidences=self._load_field_confidences(self.field_confidences_json or "{}"),
            source_screenshot=self.source_screenshot or "",
            is_equipped=bool(self.is_equipped),
            notes=self.notes or "",
            parsed_at=self.parsed_at,
        )


# Narrow string columns back to their Pydantic Literal types. The DB doesn't enforce
# the literal set, so we re-validate on read; rejecting an out-of-set value here
# would be a worse UX than logging and falling through.
def cast_slot(value: str) -> GearSlot:
    if value not in {"weapon", "armor", "accessory", "exclusive"}:
        raise ValueError(f"unknown slot in DB: {value!r}")
    return value  # type: ignore[return-value]


def cast_rarity(value: str) -> Rarity:
    if value not in {"common", "uncommon", "rare", "epic", "legendary"}:
        raise ValueError(f"unknown rarity in DB: {value!r}")
    return value  # type: ignore[return-value]
