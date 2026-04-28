"""Arcana scroll schemas — `data/game/arcana.json`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import StatId

ArcanaTier = Literal["normal", "advanced", "rare", "epic", "legendary"]


class ArcanaEffect(BaseModel):
    stat: StatId
    value: float
    multiplicative: bool = True


class ArcanaScroll(BaseModel):
    id: str
    name: str
    tier: ArcanaTier
    effects: list[ArcanaEffect] = Field(default_factory=list)
    description: str = ""
