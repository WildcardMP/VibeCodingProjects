"""Damage calculator unit tests — formula correctness for SG + MK abilities."""

from __future__ import annotations

import pytest

from app.schemas.hero import Ability, Hero
from app.schemas.simulation import StatTotals, TargetContext
from app.services.damage_calc import dps, expected_hit, find_hero, simulate


# ---------------------------------------------------------------------------
# Helpers — mirror the seed-data abilities for SG and MK
# ---------------------------------------------------------------------------
def _burst_acorn() -> Ability:
    """Squirrel Girl primary ability (Burst Acorn) — projectile, can crit + precision."""
    return Ability(
        id="burst_acorn",
        name="Burst Acorn",
        tags=["projectile", "aoe"],
        base_damage=80,
        scaling=[],
        cooldown=6.0,
        can_precision=True,
        can_crit=True,
    )


def _ankh() -> Ability:
    """Moon Knight Ankh of Khonshu — boss melt, can crit + precision."""
    return Ability(
        id="ankh",
        name="Ankh of Khonshu",
        tags=["debuff", "boss-melt"],
        base_damage=100,
        scaling=[],
        cooldown=10.0,
        can_precision=True,
        can_crit=True,
    )


# ---------------------------------------------------------------------------
# Formula correctness
# ---------------------------------------------------------------------------
def test_zero_stats_no_modifiers_returns_base_damage() -> None:
    """Empty StatTotals + neutral target → expected hit equals base damage."""
    hit = expected_hit(_burst_acorn(), StatTotals(), TargetContext())
    assert hit == 80
    assert dps(_burst_acorn(), StatTotals(), TargetContext()) == pytest.approx(80 / 6.0)


def test_total_output_boost_multiplies_correctly() -> None:
    """+8300% Total Output Boost = 84x multiplier (base * (1 + 83))."""
    stats = StatTotals(total_output_boost=8300)  # +8300% = +83 multiplier
    hit = expected_hit(_burst_acorn(), stats, TargetContext())
    assert hit == pytest.approx(80 * 84)


def test_damage_bonus_stacks_additively_with_situational() -> None:
    """damage_bonus + boss_damage are summed before the (1+x) multiplier."""
    stats = StatTotals(total_damage_bonus=100, boss_damage=50)  # +100% + +50%
    target = TargetContext(is_boss=True)
    hit = expected_hit(_ankh(), stats, target)
    # base 100 * (1+0) Total Output * (1 + (100+50)/100) = 100 * 2.5
    assert hit == pytest.approx(100 * 2.5)


def test_close_range_bonus_only_applies_when_in_range() -> None:
    stats = StatTotals(close_range_damage=830)  # Alchemy Amulet S-tier
    far = expected_hit(_burst_acorn(), stats, TargetContext(is_close_range=False))
    near = expected_hit(_burst_acorn(), stats, TargetContext(is_close_range=True))
    assert far == 80  # no bonus applied
    assert near == pytest.approx(80 * (1 + 8.3))  # +830% = +8.3 multiplier


def test_precision_channel_probabilistic_mean() -> None:
    """precision_rate=20%, precision_damage=8300% → 0.8*x + 0.2*(x*(1+83))."""
    stats = StatTotals(precision_rate=20, precision_damage=8300)
    hit = expected_hit(_burst_acorn(), stats, TargetContext())
    base_after_output = 80
    expected = (1 - 0.2) * base_after_output + 0.2 * base_after_output * (1 + 83)
    assert hit == pytest.approx(expected)


def test_precision_rate_clamps_at_100_percent() -> None:
    stats = StatTotals(precision_rate=999, precision_damage=100)  # absurd rate
    hit = expected_hit(_burst_acorn(), stats, TargetContext())
    # p clamped to 1.0 → all hits are precision, so hit = 80 * (1 + 1) = 160
    assert hit == pytest.approx(160)


def test_crit_channel_independent_of_precision() -> None:
    """Both channels apply multiplicatively when both rates > 0."""
    stats = StatTotals(
        precision_rate=10, precision_damage=100,  # +100% on precision crit
        crit_rate=10, crit_damage=200,            # +200% on yellow crit
    )
    hit = expected_hit(_burst_acorn(), stats, TargetContext())
    after_precision = (1 - 0.1) * 80 + 0.1 * 80 * (1 + 1.0)  # 80 + 8 = 88
    after_crit = (1 - 0.1) * after_precision + 0.1 * after_precision * (1 + 2.0)
    assert hit == pytest.approx(after_crit)


def test_can_precision_false_bypasses_precision_channel() -> None:
    stats = StatTotals(precision_rate=50, precision_damage=1000)
    silent_acorn = Ability(
        id="silent",
        name="Silent",
        tags=[],
        base_damage=100,
        scaling=[],
        cooldown=1,
        can_precision=False,
        can_crit=False,
    )
    assert expected_hit(silent_acorn, stats, TargetContext()) == 100


def test_vulnerability_applies_after_other_multipliers() -> None:
    """target.vulnerability is a final multiplicative debuff multiplier."""
    stats = StatTotals(total_output_boost=100)  # +100% = 2x
    target = TargetContext(vulnerability=0.5)  # +50% damage taken
    hit = expected_hit(_ankh(), stats, target)
    # 100 * 2 * 1.5 = 300
    assert hit == pytest.approx(300)


# ---------------------------------------------------------------------------
# Ability tagging — ability_damage_bonus vs primary_damage_bonus
# ---------------------------------------------------------------------------
def test_ability_damage_bonus_applies_to_non_primary_abilities() -> None:
    stats = StatTotals(ability_damage_bonus=100)  # +100% on abilities
    hit_ankh = expected_hit(_ankh(), stats, TargetContext())  # tagged "boss-melt", not primary
    assert hit_ankh == pytest.approx(100 * 2)


def test_primary_damage_bonus_applies_to_primary_tagged_abilities() -> None:
    stats = StatTotals(primary_damage_bonus=100, ability_damage_bonus=999)
    primary = Ability(
        id="primary",
        name="Primary Attack",
        tags=["primary"],
        base_damage=50,
        scaling=[],
        cooldown=0.5,
        can_precision=True,
        can_crit=True,
    )
    # Primary tag → primary_damage_bonus (100) wins; ability_damage_bonus ignored
    hit = expected_hit(primary, stats, TargetContext())
    assert hit == pytest.approx(50 * 2)  # +100% bonus


# ---------------------------------------------------------------------------
# DPS
# ---------------------------------------------------------------------------
def test_dps_divides_by_cooldown() -> None:
    stats = StatTotals(total_output_boost=100)  # 2x
    burst = _burst_acorn()  # 80 base, 6s cooldown
    hit = expected_hit(burst, stats, TargetContext())
    assert dps(burst, stats, TargetContext()) == pytest.approx(hit / 6.0)


def test_dps_zero_cooldown_returns_expected_hit() -> None:
    """Primary attacks have cooldown=0; treat DPS as damage-per-shot."""
    primary = Ability(
        id="instant",
        name="Instant",
        tags=["primary"],
        base_damage=50,
        scaling=[],
        cooldown=0.0,
        can_precision=False,
        can_crit=False,
    )
    assert dps(primary, StatTotals(), TargetContext()) == 50


# ---------------------------------------------------------------------------
# simulate() — full hero scoring
# ---------------------------------------------------------------------------
def test_simulate_returns_one_result_per_ability() -> None:
    sg = Hero(
        id="squirrel_girl",
        display_name="Squirrel Girl",
        abilities=[_burst_acorn()],
    )
    result = simulate(sg, StatTotals(total_output_boost=100), TargetContext())
    assert result.hero_id == "squirrel_girl"
    assert len(result.per_ability) == 1
    assert result.per_ability[0].ability_id == "burst_acorn"
    assert result.per_ability[0].expected_hit == pytest.approx(160)
    assert result.per_ability[0].dps == pytest.approx(160 / 6.0)
    # StatTotals echoes back unchanged
    assert result.stat_totals.total_output_boost == 100


def test_simulate_handles_hero_with_no_abilities() -> None:
    placeholder = Hero(id="ghost", display_name="Ghost", abilities=[])
    result = simulate(placeholder, StatTotals(), TargetContext())
    assert result.per_ability == []


# ---------------------------------------------------------------------------
# find_hero helper
# ---------------------------------------------------------------------------
def test_find_hero_returns_match_or_none() -> None:
    sg = Hero(id="squirrel_girl", display_name="Squirrel Girl", abilities=[])
    mk = Hero(id="moon_knight", display_name="Moon Knight", abilities=[])
    assert find_hero([sg, mk], "moon_knight") == mk
    assert find_hero([sg, mk], "ghost") is None
    assert find_hero([], "anything") is None
