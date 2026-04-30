"""Shared fixtures for service-layer tests.

Builds a synthetic ``GameData`` with two heroes (SG + MK) and a three-stat
catalog. Lets `test_roll_score` and any future service tests share one
deterministic source rather than each rolling its own.

Stats are sized to the prompt: TOB and Precision Damage at S-tier max
8500, Boss Damage at S-tier max 4500. Tier ramp follows the seed-data
pattern (D < C < B < A < S, monotonic).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.data_loader import GameData
from app.schemas.hero import Ability, AbilityScaling, Hero


def _tier_ramp(s_max: float) -> list[dict[str, Any]]:
    """Generate a monotonic D→S tier table summing to roughly s_max at the top.

    The exact mid-tier values aren't asserted on; they exist so the
    catalog shape is well-formed for code paths that look up other tiers.
    """
    return [
        {"tier": "D", "min": s_max * 0.003, "max": s_max * 0.012},
        {"tier": "C", "min": s_max * 0.012, "max": s_max * 0.047},
        {"tier": "B", "min": s_max * 0.047, "max": s_max * 0.176},
        {"tier": "A", "min": s_max * 0.176, "max": s_max * 0.470},
        {"tier": "S", "min": s_max * 0.470, "max": s_max},
    ]


@pytest.fixture
def synthetic_game_data() -> GameData:
    """Two heroes, three stats. Deterministic; no I/O."""
    heroes = [
        Hero(
            id="squirrel_girl",
            display_name="Squirrel Girl",
            abilities=[
                Ability(
                    id="burst_acorn",
                    name="Burst Acorn",
                    tags=["projectile", "aoe"],
                    base_damage=80,
                    scaling=[
                        AbilityScaling(stat="Total Output Boost", coefficient=1.0),
                        AbilityScaling(stat="Precision Damage", coefficient=1.0),
                    ],
                    cooldown=6.0,
                    can_precision=True,
                    can_crit=True,
                ),
                Ability(
                    id="squirrel_friends",
                    name="Squirrel Friends",
                    tags=["summon"],
                    base_damage=50,
                    scaling=[
                        AbilityScaling(stat="Total Output Boost", coefficient=1.0),
                    ],
                    cooldown=12.0,
                    can_precision=False,
                    can_crit=False,
                ),
            ],
        ),
        Hero(
            id="moon_knight",
            display_name="Moon Knight",
            abilities=[
                Ability(
                    id="ankh",
                    name="Ankh of Khonshu",
                    tags=["debuff", "boss-melt"],
                    base_damage=100,
                    scaling=[
                        AbilityScaling(stat="Total Output Boost", coefficient=1.0),
                        AbilityScaling(stat="Boss Damage", coefficient=1.0),
                    ],
                    cooldown=10.0,
                    can_precision=True,
                    can_crit=True,
                ),
            ],
        ),
    ]

    gear_stats: list[dict[str, Any]] = [
        {
            "stat_id": "Total Output Boost",
            "display_name": "Total Output Boost",
            "applies_to_slots": ["weapon", "armor", "accessory", "exclusive"],
            "tiers": _tier_ramp(8500),
        },
        {
            "stat_id": "Precision Damage",
            "display_name": "Precision Damage",
            "applies_to_slots": ["weapon", "accessory"],
            "tiers": _tier_ramp(8500),
        },
        {
            "stat_id": "Boss Damage",
            "display_name": "Boss Damage",
            "applies_to_slots": ["weapon", "accessory"],
            "tiers": _tier_ramp(4500),
        },
    ]

    return GameData(
        heroes=heroes,
        traits=[],
        gear_stats=gear_stats,
        arcana=[],
        forge_rules={},
        version={"extracted_at": None, "raw_files_present": []},
        loaded_at=datetime(2026, 4, 29),
        sources={k: Path("/synthetic") for k in (
            "heroes", "traits", "gear_stats", "arcana", "forge_rules", "version",
        )},
    )
