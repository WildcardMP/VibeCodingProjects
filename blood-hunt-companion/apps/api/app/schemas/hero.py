"""Hero & ability schemas — the canonical shape of `data/game/heroes.json`."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import StatId


class AbilityScaling(BaseModel):
    """A single (stat, coefficient) pair in an ability's damage formula.

    Multiple rows compose a multi-stat scaling expression — see services/damage_calc.py
    for how these compose with `total_output_boost`, `total_damage_bonus`, etc.
    """

    stat: StatId
    coefficient: float


class Ability(BaseModel):
    id: str
    name: str
    tags: list[str] = Field(default_factory=list)  # e.g. ["projectile", "aoe", "boss-melt"]
    base_damage: float
    scaling: list[AbilityScaling] = Field(default_factory=list)
    cooldown: float = 0.0
    can_precision: bool = True  # whether precision-rate/damage applies
    can_crit: bool = True


class Hero(BaseModel):
    id: str
    display_name: str
    abilities: list[Ability] = Field(default_factory=list)
