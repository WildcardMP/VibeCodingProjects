"""Damage simulator schemas — what `POST /api/simulate` exchanges.

The simulator is Phase 3's F1 deliverable per PROJECT.md §3.1 and §11. It
takes a `(hero, build, target)` tuple and returns per-ability damage + DPS
plus the aggregated `StatTotals` so the frontend can show a stat-pool
breakdown without re-doing the math client-side.

**Value convention** (mirrors `PHASE2_OCR_INPUTS.md`):

* **Percentage stats** (Total Output Boost, Precision Damage, Crit Rate,
  ...) are stored as the percent number itself — `8300` for `+8300%`,
  `12.7` for `+12.7%`. The damage formula divides by 100 where it needs a
  multiplier. This matches the OCR ingest contract; aggregation does no
  unit conversion.
* **Flat stats** (Health, Armor Value) are stored as absolute units.
* `StatTotals.other` is a catch-all dict so OCR-discovered stats outside
  the canonical set still flow through the simulator without being
  silently dropped — they just don't contribute to the formula.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .gear import ParsedGear


class StatTotals(BaseModel):
    """Aggregated stat pool from gear + traits + arcana."""

    # --- Damage scaling (percentage stats) -----------------------------------
    total_output_boost: float = 0.0
    total_damage_bonus: float = 0.0
    ability_damage_bonus: float = 0.0
    primary_damage_bonus: float = 0.0
    boss_damage: float = 0.0
    close_range_damage: float = 0.0
    healthy_enemy_damage: float = 0.0

    # --- Precision channel (orange numbers) ----------------------------------
    precision_rate: float = 0.0
    precision_damage: float = 0.0

    # --- Crit channel (yellow numbers, independent of precision) -------------
    crit_rate: float = 0.0
    crit_damage: float = 0.0

    # --- Debuffs / penetration -----------------------------------------------
    vulnerability_inflicted: float = 0.0

    # --- Cooldowns -----------------------------------------------------------
    cooldown_reduction: float = 0.0
    rune_cooldown_reduction: float = 0.0

    # --- Survivability (flat units, not percentages) -------------------------
    health: float = 0.0
    armor_value: float = 0.0
    block_rate: float = 0.0
    block_damage_reduction: float = 0.0
    dodge_rate: float = 0.0

    # --- Catch-all for OCR-discovered stats outside the canonical set --------
    other: dict[str, float] = Field(default_factory=dict)


class TargetContext(BaseModel):
    """Situational toggles for a single simulated hit.

    Defaults model a generic mid-wave enemy (no boss bonuses, no
    close-range proximity, no debuffs applied). Override per scenario.
    """

    is_boss: bool = False
    is_close_range: bool = False
    is_healthy: bool = False  # most enemies are "healthy" until hit a few times
    vulnerability: float = 0.0  # extra debuff applied before this hit (e.g. SG Squirrel Friends)


class SimulationRequest(BaseModel):
    """Client → server payload for a single simulation."""

    hero_id: str  # canonical slug; e.g. "moon_knight"
    gear: list[ParsedGear] = Field(default_factory=list)
    trait_alloc: dict[str, int] = Field(default_factory=dict)  # node_id → points allocated
    arcana_ids: list[str] = Field(default_factory=list)  # equipped arcana scroll ids
    target: TargetContext = Field(default_factory=TargetContext)


class AbilityResult(BaseModel):
    """One ability's damage output for the requested build + target."""

    ability_id: str
    ability_name: str
    base_damage: float
    expected_hit: float  # damage per hit (probabilistic for precision/crit channels)
    dps: float  # expected_hit / cooldown; equals expected_hit when cooldown <= 0


class SimulationResult(BaseModel):
    """Server → client payload — every ability scored against the build."""

    hero_id: str
    per_ability: list[AbilityResult] = Field(default_factory=list)
    stat_totals: StatTotals
