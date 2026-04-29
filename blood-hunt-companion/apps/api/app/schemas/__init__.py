"""Pydantic schemas — the wire format between OCR, FastAPI, and the Next.js frontend.

These mirror the canonical JSON shapes documented in PROJECT.md §10. Everything that
crosses an API boundary is defined here so the schemas can be code-generated into
TypeScript via `datamodel-code-generator` (see Makefile `gen-types` target).
"""

from .arcana import ArcanaScroll
from .common import GearSlot, Rarity, StatId, TierLetter
from .gear import BaseEffect, ExtendedEffect, GearPatch, GearPiece, ParsedGear
from .hero import Ability, AbilityScaling, Hero
from .run import Build, Run
from .simulation import (
    AbilityResult,
    SimulationRequest,
    SimulationResult,
    StatTotals,
    TargetContext,
)
from .trait import TraitEffect, TraitNode

__all__ = [
    "Ability",
    "AbilityResult",
    "AbilityScaling",
    "ArcanaScroll",
    "BaseEffect",
    "Build",
    "ExtendedEffect",
    "GearPatch",
    "GearPiece",
    "GearSlot",
    "Hero",
    "ParsedGear",
    "Rarity",
    "Run",
    "SimulationRequest",
    "SimulationResult",
    "StatId",
    "StatTotals",
    "TargetContext",
    "TierLetter",
    "TraitEffect",
    "TraitNode",
]
