"""Build & Run schemas — what the run logger and analytics endpoints exchange."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunOutcome = Literal["clear", "wipe"]


class Build(BaseModel):
    id: int | None = None
    hero_id: str
    name: str
    trait_alloc: dict[str, int] = Field(default_factory=dict)  # node_id -> points
    arcana: list[str] = Field(default_factory=list)  # arcana scroll ids
    gear_loadout: dict[str, int] = Field(default_factory=dict)  # slot -> gear_piece.id
    created_at: datetime | None = None


class Run(BaseModel):
    id: int | None = None
    difficulty: int = Field(ge=1, le=160)
    build_id: int | None
    squad: list[str]  # hero ids of teammates including self
    outcome: RunOutcome
    phase_reached: int | None = Field(default=None, ge=1, le=12)
    duration_seconds: int | None = Field(default=None, ge=0)
    shards_earned: int | None = Field(default=None, ge=0)
    notes: str = ""
    played_at: datetime | None = None
