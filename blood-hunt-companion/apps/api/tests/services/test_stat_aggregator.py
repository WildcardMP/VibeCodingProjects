"""Stat aggregator unit tests — gear + traits + arcana → StatTotals.

Synthetic data only; no game-data loader, no Tesseract, no DB.
"""

from __future__ import annotations

from app.schemas.arcana import ArcanaEffect, ArcanaScroll
from app.schemas.gear import BaseEffect, ExtendedEffect, ParsedGear
from app.schemas.trait import TraitEffect, TraitNode
from app.services.stat_aggregator import aggregate_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _legendary_armor(**overrides: object) -> ParsedGear:
    body: dict[str, object] = {
        "slot": "armor",
        "rarity": "legendary",
        "level": 60,
        "rating": 7000,
        "base_effects": [
            BaseEffect(name="Health", value=2419),
            BaseEffect(name="Armor Value", value=438),
        ],
        "extended_effects": [
            ExtendedEffect(stat_id="Total Output Boost", tier="S", value=8300),
        ],
    }
    body.update(overrides)
    return ParsedGear.model_validate(body)


# ---------------------------------------------------------------------------
# Gear contributions
# ---------------------------------------------------------------------------
def test_aggregate_empty_returns_zero_totals() -> None:
    totals = aggregate_stats()
    assert totals.total_output_boost == 0.0
    assert totals.health == 0.0
    assert totals.other == {}


def test_aggregate_sums_base_and_extended_effects_from_one_piece() -> None:
    totals = aggregate_stats(gear=[_legendary_armor()])
    # Health: 2419 from base, no extended → 2419 flat
    assert totals.health == 2419
    # Armor Value: 438 from base
    assert totals.armor_value == 438
    # Total Output Boost: 8300 from extended → stays as percent number
    assert totals.total_output_boost == 8300


def test_aggregate_sums_across_multiple_gear_pieces() -> None:
    armor = _legendary_armor()
    weapon = ParsedGear.model_validate({
        "slot": "weapon",
        "rarity": "legendary",
        "level": 60,
        "rating": 6800,
        "base_effects": [BaseEffect(name="Precision Damage", value=1500)],
        "extended_effects": [
            ExtendedEffect(stat_id="Precision Damage", tier="S", value=8300),
            ExtendedEffect(stat_id="Precision Rate", tier="S", value=20),
        ],
    })
    totals = aggregate_stats(gear=[armor, weapon])
    assert totals.precision_damage == 1500 + 8300
    assert totals.precision_rate == 20
    assert totals.total_output_boost == 8300  # only on the armor


def test_aggregate_unknown_stat_lands_in_other_dict() -> None:
    """OCR may surface stats outside the canonical alias table — preserve them."""
    weird = ParsedGear.model_validate({
        "slot": "exclusive",
        "rarity": "legendary",
        "level": 60,
        "rating": 6500,
        "base_effects": [BaseEffect(name="Mammal Bond Duration", value=12.5)],
        "extended_effects": [],
    })
    totals = aggregate_stats(gear=[weird])
    assert totals.other == {"Mammal Bond Duration": 12.5}


def test_aggregate_alias_resolution_is_case_insensitive() -> None:
    """`HP`, `health`, `Health` all map to the same field."""
    g1 = _legendary_armor(base_effects=[BaseEffect(name="HP", value=100)])
    g2 = _legendary_armor(base_effects=[BaseEffect(name="health", value=200)])
    g3 = _legendary_armor(base_effects=[BaseEffect(name="Health", value=300)])
    totals = aggregate_stats(gear=[g1, g2, g3])
    assert totals.health == 600


# ---------------------------------------------------------------------------
# Traits
# ---------------------------------------------------------------------------
def test_aggregate_traits_apply_per_point() -> None:
    """Trait `per_point=0.45` × 5 allocated points → +2.25 contribution."""
    catalog = [
        TraitNode(
            hero_id="squirrel_girl",
            tree="blue",
            node_id="rodent_plague",
            display_name="Rodent Plague",
            max_points=5,
            effects=[TraitEffect(stat="Vulnerability Inflicted", per_point=0.45)],
        )
    ]
    totals = aggregate_stats(
        trait_alloc={"rodent_plague": 5},
        traits_catalog=catalog,
    )
    assert totals.vulnerability_inflicted == 0.45 * 5


def test_aggregate_traits_skip_unknown_node_ids() -> None:
    catalog = [
        TraitNode(
            hero_id="moon_knight",
            tree="gold",
            node_id="real_node",
            display_name="Real",
            max_points=3,
            effects=[TraitEffect(stat="Total Output Boost", per_point=10)],
        )
    ]
    totals = aggregate_stats(
        trait_alloc={"real_node": 2, "ghost_node": 99},
        traits_catalog=catalog,
    )
    assert totals.total_output_boost == 20  # ghost_node ignored


def test_aggregate_traits_zero_or_negative_points_contribute_nothing() -> None:
    catalog = [
        TraitNode(
            hero_id="moon_knight",
            tree="gold",
            node_id="zero_pts",
            display_name="Zero",
            max_points=3,
            effects=[TraitEffect(stat="Total Output Boost", per_point=10)],
        )
    ]
    totals = aggregate_stats(trait_alloc={"zero_pts": 0}, traits_catalog=catalog)
    assert totals.total_output_boost == 0


# ---------------------------------------------------------------------------
# Arcana
# ---------------------------------------------------------------------------
def test_aggregate_arcana_contributes_each_effect() -> None:
    catalog = [
        ArcanaScroll(
            id="scroll_of_conquest",
            name="Scroll of Conquest",
            tier="legendary",
            effects=[ArcanaEffect(stat="Total Damage Bonus", value=30)],
        ),
    ]
    totals = aggregate_stats(
        arcana_ids=["scroll_of_conquest"], arcana_catalog=catalog
    )
    assert totals.total_damage_bonus == 30


def test_aggregate_arcana_skip_unknown_ids() -> None:
    catalog = [
        ArcanaScroll(
            id="real_scroll",
            name="Real",
            tier="epic",
            effects=[ArcanaEffect(stat="Total Output Boost", value=20)],
        )
    ]
    totals = aggregate_stats(
        arcana_ids=["real_scroll", "ghost_scroll"], arcana_catalog=catalog
    )
    assert totals.total_output_boost == 20


# ---------------------------------------------------------------------------
# Combined: gear + traits + arcana
# ---------------------------------------------------------------------------
def test_aggregate_combines_all_three_sources() -> None:
    gear = [_legendary_armor()]  # +8300 Total Output Boost
    traits = [
        TraitNode(
            hero_id="moon_knight",
            tree="gold",
            node_id="boost_node",
            display_name="Boost",
            max_points=3,
            effects=[TraitEffect(stat="Total Output Boost", per_point=50)],
        )
    ]
    arcana = [
        ArcanaScroll(
            id="conquest",
            name="Conquest",
            tier="legendary",
            effects=[ArcanaEffect(stat="Total Output Boost", value=30)],
        )
    ]
    totals = aggregate_stats(
        gear=gear,
        trait_alloc={"boost_node": 3},
        arcana_ids=["conquest"],
        traits_catalog=traits,
        arcana_catalog=arcana,
    )
    # 8300 (gear) + 50*3 (traits) + 30 (arcana) = 8480
    assert totals.total_output_boost == 8480
