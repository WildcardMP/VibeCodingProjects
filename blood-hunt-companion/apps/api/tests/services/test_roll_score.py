"""F2 Gear Roll Evaluator unit tests.

Synthetic ``GameData`` from ``conftest.py`` — no I/O, no DB, no Tesseract.
"""

from __future__ import annotations

import pytest

from app.data_loader import GameData
from app.schemas.gear import BaseEffect, ExtendedEffect, ParsedGear
from app.schemas.roll_score import BuildContext
from app.services.roll_score import (
    UnknownAbilityError,
    UnknownHeroError,
    classify_threshold,
    compute_roll_score,
    derive_stat_weights,
    suggest_forge_action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_legendary(
    *,
    extended: list[ExtendedEffect] | None = None,
    base: list[BaseEffect] | None = None,
) -> ParsedGear:
    return ParsedGear.model_validate({
        "slot": "armor",
        "rarity": "legendary",
        "level": 60,
        "rating": 7000,
        "base_effects": base or [BaseEffect(name="Health", value=2419)],
        "extended_effects": extended or [],
    })


def _ee(stat: str, tier: str, value: float) -> ExtendedEffect:
    return ExtendedEffect(stat_id=stat, tier=tier, value=value)


# ---------------------------------------------------------------------------
# derive_stat_weights — resolution order
# ---------------------------------------------------------------------------
def test_derive_weights_hero_only_aggregates_across_abilities(
    synthetic_game_data: GameData,
) -> None:
    """SG has burst_acorn (TOB+Precision Damage) + squirrel_friends (TOB).
    Hero-only sums: TOB=2.0, Precision Damage=1.0 → normalize to 2/3, 1/3.
    """
    weights = derive_stat_weights(
        hero_id="squirrel_girl", ability_id=None, game_data=synthetic_game_data
    )
    assert weights == pytest.approx({
        "Total Output Boost": 2 / 3,
        "Precision Damage": 1 / 3,
    })
    assert sum(weights.values()) == pytest.approx(1.0)


def test_derive_weights_hero_plus_ability_uses_only_that_ability(
    synthetic_game_data: GameData,
) -> None:
    """ability_id=burst_acorn → just TOB(1) + Precision Damage(1), normalized to 0.5/0.5."""
    weights = derive_stat_weights(
        hero_id="squirrel_girl",
        ability_id="burst_acorn",
        game_data=synthetic_game_data,
    )
    assert weights == pytest.approx({
        "Total Output Boost": 0.5,
        "Precision Damage": 0.5,
    })


def test_derive_weights_no_hero_no_explicit_returns_total_output_boost(
    synthetic_game_data: GameData,
) -> None:
    weights = derive_stat_weights(
        hero_id=None, ability_id=None, game_data=synthetic_game_data
    )
    assert weights == {"Total Output Boost": 1.0}


def test_derive_weights_unknown_hero_raises(
    synthetic_game_data: GameData,
) -> None:
    with pytest.raises(UnknownHeroError, match="ghost_rider"):
        derive_stat_weights(
            hero_id="ghost_rider", ability_id=None, game_data=synthetic_game_data
        )


def test_derive_weights_unknown_ability_for_valid_hero_raises(
    synthetic_game_data: GameData,
) -> None:
    with pytest.raises(UnknownAbilityError, match="moonbeam"):
        derive_stat_weights(
            hero_id="moon_knight",
            ability_id="moonbeam",
            game_data=synthetic_game_data,
        )


def test_derive_weights_normalized_sum_is_one(
    synthetic_game_data: GameData,
) -> None:
    """Every derived weight set sums to 1.0 (within float tolerance)."""
    for hero_id in ("squirrel_girl", "moon_knight"):
        w = derive_stat_weights(
            hero_id=hero_id, ability_id=None, game_data=synthetic_game_data
        )
        assert sum(w.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Explicit stat_weights override
# ---------------------------------------------------------------------------
def test_explicit_stat_weights_override_hero_derivation(
    synthetic_game_data: GameData,
) -> None:
    """Non-empty stat_weights wins over hero/ability derivation."""
    gear = _make_legendary(
        extended=[_ee("Total Output Boost", "S", 8500)],
    )
    build = BuildContext(
        hero_id="squirrel_girl",
        ability_id="burst_acorn",
        stat_weights={"Boss Damage": 2.5},  # absurd weight, not normalized
    )
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    assert result.stat_weights_used == {"Boss Damage": 2.5}


def test_empty_stat_weights_dict_falls_through_to_hero_derivation(
    synthetic_game_data: GameData,
) -> None:
    """An EMPTY dict isn't an explicit override — falls back to hero/default."""
    gear = _make_legendary(
        extended=[_ee("Total Output Boost", "S", 8500)],
    )
    build = BuildContext(hero_id="moon_knight", stat_weights={})
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    # Moon Knight ankh: TOB(1) + Boss Damage(1), normalized 0.5/0.5
    assert result.stat_weights_used == pytest.approx({
        "Total Output Boost": 0.5,
        "Boss Damage": 0.5,
    })


# ---------------------------------------------------------------------------
# Scoring math
# ---------------------------------------------------------------------------
def test_legendary_perfect_roll_normalized_weights_scores_100(
    synthetic_game_data: GameData,
) -> None:
    """5 effects, each S-tier-max on the build's only weighted stat → 100/100."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
    ])
    # Generic build: weight is {TOB: 1.0}, normalized.
    build = BuildContext()
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    # Each slot contributes 8500 * 1.0 / 8500 = 1.0; sum = 5; / 5 slots * 100 = 100
    assert result.score == pytest.approx(100.0)
    assert result.threshold == "leaderboard_grade"


def test_absurd_weights_clamp_at_100(
    synthetic_game_data: GameData,
) -> None:
    """Caller weights every stat at 1.0 (not normalized) → score clamps to 100."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500),
        _ee("Precision Damage", "S", 8500),
        _ee("Boss Damage", "S", 4500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Precision Damage", "S", 8500),
    ])
    build = BuildContext(stat_weights={
        "Total Output Boost": 1.0,
        "Precision Damage": 1.0,
        "Boss Damage": 1.0,
    })
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    # Raw sum would be 5.0; / 5 slots * 100 = 100. Already at the ceiling.
    # Doubling weights would push past 100 — confirm clamp:
    build_x2 = BuildContext(stat_weights={
        "Total Output Boost": 2.0,
        "Precision Damage": 2.0,
        "Boss Damage": 2.0,
    })
    result_x2 = compute_roll_score(gear, build_x2, game_data=synthetic_game_data)
    assert result.score == pytest.approx(100.0)
    assert result_x2.score == 100.0  # clamped


def test_zero_weights_score_zero(
    synthetic_game_data: GameData,
) -> None:
    """All stat weights 0 → no contribution → score 0 → trash/smelt."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500) for _ in range(5)
    ])
    build = BuildContext(stat_weights={"Total Output Boost": 0.0})
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    assert result.score == 0.0
    assert result.threshold == "trash"
    assert result.forge_action == "smelt"


def test_legendary_one_relevant_four_irrelevant_scores_20(
    synthetic_game_data: GameData,
) -> None:
    """1 effect S-max on weight=1.0 stat, 4 on weight=0 stats → 1/5 * 100 = 20."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500),  # weight 1.0
        _ee("Boss Damage", "A", 1000),         # weight 0
        _ee("Boss Damage", "A", 1000),         # weight 0
        _ee("Boss Damage", "A", 1000),         # weight 0
        _ee("Boss Damage", "A", 1000),         # weight 0
    ])
    build = BuildContext(stat_weights={"Total Output Boost": 1.0})
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    assert result.score == pytest.approx(20.0)
    assert result.threshold == "filler"


def test_epic_three_a_tier_mid_value_no_artefacts(
    synthetic_game_data: GameData,
) -> None:
    """Epic = 3 effect slots. A-tier mid value × normalized weight = predictable score."""
    gear = ParsedGear.model_validate({
        "slot": "weapon",
        "rarity": "epic",
        "level": 60,
        "rating": 5500,
        "base_effects": [BaseEffect(name="Precision Damage", value=2000)],
        "extended_effects": [
            _ee("Total Output Boost", "A", 3000),
            _ee("Precision Damage", "A", 3000),
            _ee("Total Output Boost", "A", 3000),
        ],
    })
    # SG burst_acorn weights: TOB=0.5, Precision Damage=0.5
    build = BuildContext(hero_id="squirrel_girl", ability_id="burst_acorn")
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    # Each slot: 3000 * 0.5 / 8500 ≈ 0.1764. Sum ≈ 0.529. / 3 slots * 100 ≈ 17.6
    assert 15.0 < result.score < 25.0
    assert result.score <= 100.0
    assert len(result.breakdown) == 3


def test_normal_rarity_zero_effects_scores_zero(
    synthetic_game_data: GameData,
) -> None:
    """Normal-rarity has 0 extended-effect slots; score is always 0."""
    gear = ParsedGear.model_validate({
        "slot": "armor",
        "rarity": "normal",
        "level": 1,
        "rating": 100,
        "base_effects": [BaseEffect(name="Health", value=100)],
        "extended_effects": [],
    })
    result = compute_roll_score(
        gear, BuildContext(), game_data=synthetic_game_data
    )
    assert result.score == 0.0
    assert result.threshold == "trash"
    assert result.forge_action == "smelt"
    assert "no extended-effect rolls" in result.explanation.lower()


def test_uncatalogued_stat_records_and_contributes_zero(
    synthetic_game_data: GameData,
) -> None:
    """A stat name not in gear_stats catalog: contributes 0, surfaces in list."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500),       # catalogued
        _ee("Mystery New Stat", "S", 1000),         # NOT in catalog
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
    ])
    build = BuildContext(stat_weights={
        "Total Output Boost": 1.0,
        "Mystery New Stat": 1.0,  # weighted but uncatalogued — no s_tier_max
    })
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    assert "Mystery New Stat" in result.uncatalogued_stats
    # Mystery contributes 0 (no s_tier_max). 4 catalogued slots at 1.0 each.
    # Sum = 4 / 5 slots * 100 = 80.
    assert result.score == pytest.approx(80.0)
    # The breakdown row exists but with in_catalog=False.
    mystery_row = next(b for b in result.breakdown if b.stat_id == "Mystery New Stat")
    assert mystery_row.in_catalog is False
    assert mystery_row.s_tier_max is None
    assert mystery_row.normalized_contribution == 0.0


# ---------------------------------------------------------------------------
# Threshold + forge action
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("score, expected", [
    (0.0, "trash"),
    (19.9, "trash"),
    (20.0, "filler"),
    (39.9, "filler"),
    (40.0, "keep"),
    (59.9, "keep"),
    (60.0, "bis_candidate"),
    (79.9, "bis_candidate"),
    (80.0, "leaderboard_grade"),
    (100.0, "leaderboard_grade"),
])
def test_classify_threshold_band_boundaries(
    score: float, expected: str,
) -> None:
    assert classify_threshold(score) == expected


def test_keep_threshold_with_low_tier_recommends_reroll(
    synthetic_game_data: GameData,
) -> None:
    """A "keep" piece with at least one C/D-tier roll → reroll_low_tiers."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "D", 100),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
    ])
    # Sum: ~(100/8500 + 4*1.0) / 5 * 100 ≈ 80.2 → just over leaderboard.
    # Use weight-normalization to land in keep band.
    build = BuildContext(stat_weights={"Total Output Boost": 0.6})
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    assert result.threshold == "keep"
    assert result.forge_action == "reroll_low_tiers"


def test_keep_threshold_all_b_or_better_downgrades_to_keep(
    synthetic_game_data: GameData,
) -> None:
    """A "keep" piece with ALL rolls B-or-better → forge action softens to keep."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "B", 1000) for _ in range(5)
    ])
    build = BuildContext(stat_weights={"Total Output Boost": 1.0})
    result = compute_roll_score(gear, build, game_data=synthetic_game_data)
    # 5 * (1000/8500) / 5 * 100 ≈ 11.8 → trash actually
    # Use a weight that lands us in keep band:
    gear2 = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500),  # 1.0 contribution
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "S", 8500),
        _ee("Total Output Boost", "B", 1000),  # ~0.118 contribution; B-tier = NOT low
        _ee("Total Output Boost", "B", 1000),
    ])
    # Sum = 3.235 / 5 * 100 = 64.7 → bis_candidate. Damn, not quite keep.
    # Try with weight 0.7:
    build2 = BuildContext(stat_weights={"Total Output Boost": 0.7})
    result2 = compute_roll_score(gear2, build2, game_data=synthetic_game_data)
    # Adjusted contributions: (3 * 0.7) + (2 * 0.7 * 1000/8500) = 2.1647... / 5 * 100 ≈ 43.3
    assert result2.threshold == "keep"
    # No C or D tiers present → downgrade to plain "keep"
    assert result2.forge_action == "keep"
    # Sanity: the original (weight 1.0) had no low tiers either
    assert result.forge_action != "reroll_low_tiers" or all(
        e.tier not in {"C", "D"} for e in gear.extended_effects
    )


def test_suggest_forge_action_table(
    synthetic_game_data: GameData,
) -> None:
    """Smoke-test every (threshold → action) cell."""
    bare = _make_legendary(extended=[_ee("Total Output Boost", "S", 8500)])
    assert suggest_forge_action("trash", bare) == "smelt"
    assert suggest_forge_action("filler", bare) == "use_temporarily"
    assert suggest_forge_action("bis_candidate", bare) == "keep"
    assert suggest_forge_action("leaderboard_grade", bare) == "lock"
    # "keep" with no low tiers → keep; with a D tier → reroll_low_tiers
    assert suggest_forge_action("keep", bare) == "keep"
    bare_with_d = _make_legendary(extended=[_ee("Total Output Boost", "D", 100)])
    assert suggest_forge_action("keep", bare_with_d) == "reroll_low_tiers"


# ---------------------------------------------------------------------------
# Result-shape sanity
# ---------------------------------------------------------------------------
def test_breakdown_length_matches_extended_effects(
    synthetic_game_data: GameData,
) -> None:
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500),
        _ee("Boss Damage", "A", 1000),
        _ee("Precision Damage", "B", 500),
    ])
    result = compute_roll_score(
        gear, BuildContext(), game_data=synthetic_game_data
    )
    assert len(result.breakdown) == 3
    assert [b.stat_id for b in result.breakdown] == [
        "Total Output Boost", "Boss Damage", "Precision Damage",
    ]


def test_percentile_equals_score_v1_placeholder(
    synthetic_game_data: GameData,
) -> None:
    """V1 placeholder: percentile == score. Document so the next pass replaces it."""
    gear = _make_legendary(extended=[
        _ee("Total Output Boost", "S", 8500) for _ in range(5)
    ])
    result = compute_roll_score(
        gear, BuildContext(), game_data=synthetic_game_data
    )
    assert result.percentile == result.score
