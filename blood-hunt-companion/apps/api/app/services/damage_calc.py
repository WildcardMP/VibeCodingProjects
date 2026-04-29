"""Per-ability damage + DPS calculation.

Implements the damage formula from PROJECT.md §11 and RESEARCH.md §6.1–6.2.
Pure functions — no I/O. The router pulls hero abilities from
`data_loader.load_game_data()` and hands them in alongside the aggregated
`StatTotals`.

**Formula** (per ability, per hit):

    base = ability.base_damage
    out  = base * (1 + total_output_boost / 100)
    out *= (1 + (total_damage_bonus + situational) / 100)
    if can_precision and precision_rate > 0:
        p = min(1, precision_rate / 100)
        out = (1 - p) * out + p * out * (1 + precision_damage / 100)
    if can_crit and crit_rate > 0:
        c = min(1, crit_rate / 100)
        out = (1 - c) * out + c * out * (1 + crit_damage / 100)
    out *= (1 + target.vulnerability)

**DPS:**

    dps = out / max(ability.cooldown, EPSILON)

For abilities with `cooldown == 0` (primary attacks, instant-cast effects)
DPS equals expected damage per hit — the caller can reinterpret as
"damage per shot" for those.

**Calibration TODOs** (carried from RESEARCH.md §6.5):

* Multiplicative vs. additive stacking inside the damage_bonus bucket is
  modeled additively here — the most common interpretation, but A/B
  against in-game training-room measurements is still pending.
* Precision and crit channels are treated as **independent multiplicative
  multipliers**. RESEARCH.md flags this as the working assumption.
* Vulnerability is applied as a single multiplicative term at the end;
  multi-source stacking (Squirrel Friends + Rodent Plague + Jumbo Acorn)
  is the responsibility of the caller (sum into `target.vulnerability`).
"""

from __future__ import annotations

from collections.abc import Iterable

from ..schemas.hero import Ability, Hero
from ..schemas.simulation import (
    AbilityResult,
    SimulationResult,
    StatTotals,
    TargetContext,
)

# Stat values arrive as percent numbers (per PHASE2_OCR_INPUTS.md). Convert to
# multiplier fractions where the formula needs them.
_PCT_DIVISOR = 100.0

# Floor to avoid divide-by-zero in DPS for zero-cooldown abilities. Using a
# tiny positive number rather than a special-case branch keeps the math
# uniform; the caller decides how to display "DPS" for instant abilities.
_COOLDOWN_FLOOR = 1e-6


def _to_mult(pct: float) -> float:
    """Percent number → multiplier fraction. 8300 → 83.0, 12.7 → 0.127."""
    return pct / _PCT_DIVISOR


def _situational_bonus(stats: StatTotals, target: TargetContext) -> float:
    """Sum every situational damage_bonus that applies to this target."""
    bonus = 0.0
    if target.is_boss:
        bonus += stats.boss_damage
    if target.is_close_range:
        bonus += stats.close_range_damage
    if target.is_healthy:
        bonus += stats.healthy_enemy_damage
    return bonus


def _ability_bonus(ability: Ability, stats: StatTotals) -> float:
    """Ability-tagged bonus (`ability_damage_bonus`) only applies to abilities,
    not to primary attacks. We use the `tags` list as the discriminator —
    anything tagged `"primary"` falls back to `primary_damage_bonus`.
    """
    if "primary" in ability.tags:
        return stats.primary_damage_bonus
    return stats.ability_damage_bonus


def expected_hit(
    ability: Ability, stats: StatTotals, target: TargetContext
) -> float:
    """Compute expected damage per hit for one ability (probabilistic mean)."""
    out = ability.base_damage

    # Multiplicative: total output boost (the universally best stat per
    # RESEARCH.md §3.4).
    out *= 1 + _to_mult(stats.total_output_boost)

    # Additive bucket: all the damage_bonus stats (target-conditional).
    bonus = stats.total_damage_bonus
    bonus += _ability_bonus(ability, stats)
    bonus += _situational_bonus(stats, target)
    out *= 1 + _to_mult(bonus)

    # Precision channel — orange numbers. Independent of crit per RESEARCH.md
    # §3.4 (community A/B suggests they're separate channels).
    if ability.can_precision and stats.precision_rate > 0:
        p = min(1.0, _to_mult(stats.precision_rate))
        out = (1 - p) * out + p * out * (1 + _to_mult(stats.precision_damage))

    # Crit channel — yellow numbers. Same independent treatment.
    if ability.can_crit and stats.crit_rate > 0:
        c = min(1.0, _to_mult(stats.crit_rate))
        out = (1 - c) * out + c * out * (1 + _to_mult(stats.crit_damage))

    # Vulnerability applies after every other multiplier (debuffs the target,
    # not the source). Caller is responsible for summing multi-source stacks
    # into `target.vulnerability` before calling.
    out *= 1 + target.vulnerability

    return out


def dps(ability: Ability, stats: StatTotals, target: TargetContext) -> float:
    """Expected DPS — `expected_hit / cooldown`. Zero-cooldown returns the
    expected hit (caller treats as damage-per-shot)."""
    hit = expected_hit(ability, stats, target)
    cd = ability.cooldown if ability.cooldown > _COOLDOWN_FLOOR else _COOLDOWN_FLOOR
    if ability.cooldown <= 0:
        return hit
    return hit / cd


def simulate(
    hero: Hero, stats: StatTotals, target: TargetContext
) -> SimulationResult:
    """Score every ability the hero owns against the build + target.

    Returns a `SimulationResult` with one `AbilityResult` per ability. The
    aggregated `StatTotals` is echoed back so the frontend can render the
    stat-pool breakdown without re-doing the aggregation client-side.
    """
    results = [
        AbilityResult(
            ability_id=ability.id,
            ability_name=ability.name,
            base_damage=ability.base_damage,
            expected_hit=expected_hit(ability, stats, target),
            dps=dps(ability, stats, target),
        )
        for ability in hero.abilities
    ]
    return SimulationResult(
        hero_id=hero.id, per_ability=results, stat_totals=stats
    )


def find_hero(heroes: Iterable[Hero], hero_id: str) -> Hero | None:
    """Tiny helper so routers don't repeat the lookup pattern."""
    return next((h for h in heroes if h.id == hero_id), None)
