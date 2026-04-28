"""GearORM round-trip tests — Pydantic ↔ ORM conversion is lossless and the
slot/rarity casts reject unknown values.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.models.gear import GearORM, cast_rarity, cast_slot
from app.schemas.gear import BaseEffect, ExtendedEffect, ParsedGear


def _sample_parsed() -> ParsedGear:
    return ParsedGear(
        slot="weapon",
        hero="Squirrel Girl",
        hero_id="squirrel_girl",
        rarity="legendary",
        level=60,
        rating=7086,
        base_effects=[BaseEffect(name="Precision Damage", value=8300.0)],
        extended_effects=[
            ExtendedEffect(
                stat_id="Total Output Boost", tier="S", value=4200.0,
                raw_text="Total Output Boost +4200%", confidence=0.92,
            ),
            ExtendedEffect(
                stat_id="Boss Damage", tier="A", value=1800.0,
                raw_text="Boss Damage +1800%", confidence=0.78,
            ),
        ],
        overall_confidence=0.85,
        source_screenshot="/tmp/x.png",
    )


def test_from_parsed_round_trip() -> None:
    parsed = _sample_parsed()
    orm = GearORM.from_parsed(parsed)
    # Simulate what SQLAlchemy does after a flush — assign an id + timestamp.
    orm.id = 42
    orm.parsed_at = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

    piece = orm.to_pydantic()

    assert piece.id == 42
    assert piece.slot == "weapon"
    assert piece.hero == "Squirrel Girl"
    assert piece.hero_id == "squirrel_girl"
    assert piece.rarity == "legendary"
    assert piece.level == 60
    assert piece.rating == 7086
    assert len(piece.base_effects) == 1
    assert piece.base_effects[0].name == "Precision Damage"
    assert piece.base_effects[0].value == 8300.0
    assert piece.overall_confidence == 0.85
    assert piece.source_screenshot == "/tmp/x.png"
    assert piece.is_equipped is False
    assert piece.notes == ""
    assert piece.parsed_at == datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

    assert len(piece.extended_effects) == 2
    assert piece.extended_effects[0].stat_id == "Total Output Boost"
    assert piece.extended_effects[0].tier == "S"
    assert piece.extended_effects[0].value == 4200.0
    assert piece.extended_effects[0].raw_text == "Total Output Boost +4200%"
    assert piece.extended_effects[0].confidence == 0.92
    assert piece.extended_effects[1].tier == "A"


def test_extended_effects_json_is_valid() -> None:
    parsed = _sample_parsed()
    orm = GearORM.from_parsed(parsed)
    decoded = json.loads(orm.extended_effects_json)
    assert isinstance(decoded, list)
    assert len(decoded) == 2
    assert decoded[0]["stat_id"] == "Total Output Boost"
    assert decoded[0]["tier"] == "S"


def test_base_effects_json_round_trips() -> None:
    """Multi-row base effects survive JSON encode/decode through the ORM."""
    parsed = ParsedGear(
        slot="armor",
        rarity="legendary",
        level=60,
        rating=7086,
        base_effects=[
            BaseEffect(name="Health", value=2419.0),
            BaseEffect(name="Armor Value", value=438.0),
        ],
    )
    orm = GearORM.from_parsed(parsed)
    orm.id = 1
    orm.parsed_at = datetime(2026, 4, 27, tzinfo=UTC)
    decoded = json.loads(orm.base_effects_json)
    assert len(decoded) == 2
    assert decoded[1] == {"name": "Armor Value", "value": 438.0}
    piece = orm.to_pydantic()
    assert [e.name for e in piece.base_effects] == ["Health", "Armor Value"]


def test_load_extended_handles_empty_string() -> None:
    assert GearORM._load_extended("") == []


def test_load_extended_handles_non_list_blob() -> None:
    # Malformed DB content → empty list instead of crashing the to_pydantic call.
    assert GearORM._load_extended('{"oops": true}') == []


def test_load_base_handles_empty_string() -> None:
    assert GearORM._load_base("") == []


def test_load_base_handles_non_list_blob() -> None:
    assert GearORM._load_base('{"oops": true}') == []


def test_from_parsed_no_extended_effects() -> None:
    parsed = ParsedGear(
        slot="armor",
        rarity="normal",
        level=1,
        base_effects=[BaseEffect(name="HP", value=100.0)],
    )
    orm = GearORM.from_parsed(parsed)
    assert orm.extended_effects_json == "[]"
    assert orm.rating == 0
    assert orm.hero is None


def test_to_pydantic_handles_null_ocr_confidence() -> None:
    parsed = _sample_parsed()
    orm = GearORM.from_parsed(parsed)
    orm.id = 1
    orm.ocr_confidence = None  # nullable column — defaults to 0.0 in pydantic
    orm.parsed_at = datetime(2026, 4, 27, tzinfo=UTC)
    piece = orm.to_pydantic()
    assert piece.overall_confidence == 0.0


@pytest.mark.parametrize(
    "value",
    ["weapon", "armor", "accessory", "exclusive"],
)
def test_cast_slot_accepts_known(value: str) -> None:
    assert cast_slot(value) == value


def test_cast_slot_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown slot"):
        cast_slot("chest")


@pytest.mark.parametrize(
    "value",
    ["normal", "advanced", "rare", "epic", "legendary"],
)
def test_cast_rarity_accepts_known(value: str) -> None:
    assert cast_rarity(value) == value


def test_cast_rarity_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown rarity"):
        cast_rarity("mythic")


def test_cast_rarity_rejects_old_vocabulary() -> None:
    """`common` and `uncommon` are no longer valid (renamed 2026-04-27)."""
    with pytest.raises(ValueError, match="unknown rarity"):
        cast_rarity("common")
    with pytest.raises(ValueError, match="unknown rarity"):
        cast_rarity("uncommon")
