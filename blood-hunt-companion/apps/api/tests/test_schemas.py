"""Schema sanity — pydantic accepts the canonical shapes and rejects bad ones."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import BaseEffect, ExtendedEffect, Hero, ParsedGear


def test_parsed_gear_minimum() -> None:
    g = ParsedGear(
        slot="armor",
        rarity="legendary",
        level=60,
        base_effects=[BaseEffect(name="Total Output Boost", value=4200.0)],
    )
    assert g.extended_effects == []
    assert g.overall_confidence == 0.0
    assert g.rating == 0
    assert g.hero is None


def test_parsed_gear_with_extended() -> None:
    g = ParsedGear(
        slot="weapon",
        hero="Squirrel Girl",
        hero_id="squirrel_girl",
        rarity="legendary",
        level=60,
        rating=7086,
        base_effects=[BaseEffect(name="Precision Damage", value=8300.0)],
        extended_effects=[
            ExtendedEffect(stat_id="Precision Rate", tier="S", value=20.0, confidence=0.92),
            ExtendedEffect(stat_id="Total Output Boost", tier="A", value=3600.0, confidence=0.88),
        ],
        overall_confidence=0.9,
    )
    assert len(g.extended_effects) == 2
    assert g.extended_effects[0].tier == "S"
    assert g.rating == 7086
    assert g.hero == "Squirrel Girl"


def test_parsed_gear_rejects_bad_rarity() -> None:
    with pytest.raises(ValidationError):
        ParsedGear(
            slot="armor",
            rarity="ultra-mega",  # type: ignore[arg-type]
            level=60,
            base_effects=[BaseEffect(name="Total Output Boost", value=4200.0)],
        )


def test_parsed_gear_rejects_bad_slot() -> None:
    with pytest.raises(ValidationError):
        ParsedGear(
            slot="chest",  # type: ignore[arg-type]
            rarity="legendary",
            level=60,
            base_effects=[BaseEffect(name="Total Output Boost", value=4200.0)],
        )


@pytest.mark.parametrize("rarity", ["normal", "advanced", "rare", "epic", "legendary"])
def test_parsed_gear_accepts_all_canonical_rarities(rarity: str) -> None:
    """Every value in the renamed Rarity Literal must validate."""
    g = ParsedGear(
        slot="armor",
        rarity=rarity,  # type: ignore[arg-type]
        level=1,
        base_effects=[BaseEffect(name="HP", value=100.0)],
    )
    assert g.rarity == rarity


def test_extended_effect_caps_at_5() -> None:
    """Legendary gear has up to 5 extended effects (was 4 pre-2026-04-27)."""
    # Five rows is the legendary cap — must validate.
    g = ParsedGear(
        slot="armor",
        rarity="legendary",
        level=60,
        base_effects=[BaseEffect(name="Health", value=2419.0)],
        extended_effects=[
            ExtendedEffect(stat_id="X", tier="S", value=1.0) for _ in range(5)
        ],
    )
    assert len(g.extended_effects) == 5

    # Six rows is over the cap — must reject.
    with pytest.raises(ValidationError):
        ParsedGear(
            slot="armor",
            rarity="legendary",
            level=60,
            base_effects=[BaseEffect(name="Health", value=2419.0)],
            extended_effects=[
                ExtendedEffect(stat_id="X", tier="S", value=1.0) for _ in range(6)
            ],
        )


def test_parsed_gear_supports_multiple_base_effects() -> None:
    """Armor shows BOTH Health and Armor Value under BASE EFFECT."""
    g = ParsedGear(
        slot="armor",
        rarity="legendary",
        level=60,
        base_effects=[
            BaseEffect(name="Health", value=2419.0),
            BaseEffect(name="Armor Value", value=438.0),
        ],
    )
    assert len(g.base_effects) == 2
    assert g.base_effects[1].name == "Armor Value"


def test_hero_round_trip() -> None:
    h = Hero(id="squirrel_girl", display_name="Squirrel Girl", abilities=[])
    assert Hero.model_validate(h.model_dump()) == h
