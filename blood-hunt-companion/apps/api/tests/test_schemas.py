"""Schema sanity — pydantic accepts the canonical shapes and rejects bad ones."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import ExtendedEffect, Hero, ParsedGear


def test_parsed_gear_minimum() -> None:
    g = ParsedGear(
        slot="armor",
        rarity="legendary",
        level=60,
        base_effect="Total Output Boost",
        base_value=4200.0,
    )
    assert g.extended_effects == []
    assert g.overall_confidence == 0.0


def test_parsed_gear_with_extended() -> None:
    g = ParsedGear(
        slot="weapon",
        hero_id="squirrel_girl",
        rarity="legendary",
        level=60,
        base_effect="Precision Damage",
        base_value=8300.0,
        extended_effects=[
            ExtendedEffect(stat_id="Precision Rate", tier="S", value=20.0, confidence=0.92),
            ExtendedEffect(stat_id="Total Output Boost", tier="A", value=3600.0, confidence=0.88),
        ],
        overall_confidence=0.9,
    )
    assert len(g.extended_effects) == 2
    assert g.extended_effects[0].tier == "S"


def test_parsed_gear_rejects_bad_rarity() -> None:
    with pytest.raises(ValidationError):
        ParsedGear(
            slot="armor",
            rarity="ultra-mega",  # type: ignore[arg-type]
            level=60,
            base_effect="Total Output Boost",
            base_value=4200.0,
        )


def test_parsed_gear_rejects_bad_slot() -> None:
    with pytest.raises(ValidationError):
        ParsedGear(
            slot="chest",  # type: ignore[arg-type]
            rarity="legendary",
            level=60,
            base_effect="Total Output Boost",
            base_value=4200.0,
        )


def test_extended_effect_caps_at_4() -> None:
    with pytest.raises(ValidationError):
        ParsedGear(
            slot="armor",
            rarity="legendary",
            level=60,
            base_effect="Total Output Boost",
            base_value=4200.0,
            extended_effects=[
                ExtendedEffect(stat_id="X", tier="S", value=1.0) for _ in range(5)
            ],
        )


def test_hero_round_trip() -> None:
    h = Hero(id="squirrel_girl", display_name="Squirrel Girl", abilities=[])
    assert Hero.model_validate(h.model_dump()) == h
