"""Trait-tree schemas — the canonical shape of `data/game/traits.json`.

A node's effects are *per-point*; the simulator multiplies by allocated points.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import StatId

TraitTree = Literal["gold", "blue", "shared"]


class TraitEffect(BaseModel):
    stat: StatId
    per_point: float  # additive per allocated point unless `multiplicative=True`
    multiplicative: bool = False


class TraitNode(BaseModel):
    hero_id: str
    tree: TraitTree
    node_id: str
    display_name: str
    max_points: int = Field(ge=1, le=10)
    effects: list[TraitEffect] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)  # other node_ids
