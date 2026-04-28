"""Gear schemas: a single piece of equipment, parsed from OCR or entered manually."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import GearSlot, Rarity, StatId, TierLetter


class BaseEffect(BaseModel):
    """One row of "base effect" on a gear piece. Every piece has 1+ base effects
    (e.g. armor shows BOTH Health and Armor Value under BASE EFFECT)."""

    name: StatId
    value: float


class ExtendedEffect(BaseModel):
    """One row of "extended effect" on a gear piece. Counts are per-rarity:
    normal 0, advanced 1, rare 2, epic 3, legendary up to 5. Each row has its own
    S–D tier and a numeric roll within the tier range from `gear_stats.json`."""

    stat_id: StatId
    tier: TierLetter
    value: float
    raw_text: str = ""  # what Tesseract literally saw, for audit/debugging
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ParsedGear(BaseModel):
    """OCR output before persistence. The frontend reviews this, the user can edit
    any field, then a `POST /api/gear/manual` (or auto-save) commits it as a `GearPiece`.

    `field_confidences` is a parallel dict mirroring the schema: each top-level
    field name maps to a 0..1 confidence score from the OCR pipeline. Per-row
    `ExtendedEffect.confidence` covers the extended-effects list. The frontend
    uses these to color fields green (≥0.85) / yellow (0.6–0.85) / red (<0.6)
    per CLAUDE.md §3.6.
    """

    name: str | None = None  # item display name from OCR (nullable until ground truth lands)
    slot: GearSlot
    hero: str | None = None  # in-game hero display name, e.g. "Moon Knight"
    hero_id: str | None = None  # canonical slug for DB joins, e.g. "moon_knight"
    rarity: Rarity
    level: int = Field(ge=1, le=60)  # cap matches hero level cap (RESEARCH §3.6)
    rating: int = Field(ge=0, default=0)  # tooltip overall rating, e.g. 7086
    base_effects: list[BaseEffect] = Field(default_factory=list)
    extended_effects: list[ExtendedEffect] = Field(default_factory=list, max_length=5)
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    field_confidences: dict[str, float] = Field(default_factory=dict)
    source_screenshot: str = ""


class GearPiece(ParsedGear):
    """Persisted gear with database identity."""

    id: int
    is_equipped: bool = False
    notes: str = ""
    parsed_at: datetime


class GearPatch(BaseModel):
    """Partial-update payload for PATCH /api/gear/{id}.

    Every field is optional; only keys actually present in the request body land
    on the row (via `model_dump(exclude_unset=True)`). Send `"hero_id": null`
    to explicitly clear hero binding, omit it to leave the existing binding alone.
    """

    name: str | None = None
    slot: str | None = None
    hero: str | None = None
    hero_id: str | None = None
    rarity: str | None = None
    level: int | None = Field(default=None, ge=1, le=60)
    rating: int | None = Field(default=None, ge=0)
    base_effects: list[BaseEffect] | None = None
    extended_effects: list[ExtendedEffect] | None = None
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_screenshot: str | None = None
    is_equipped: bool | None = None
    notes: str | None = None
