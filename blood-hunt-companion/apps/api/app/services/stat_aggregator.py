"""Fold gear + traits + arcana into a single `StatTotals` pool.

Pure function — no I/O, no DB, no game-data loader. The caller passes the
trait/arcana catalogs in (typically pulled from `data_loader.load_game_data()`
in the router) so this module stays unit-testable on synthetic input.

Stat-name resolution is **fuzzy on the canonical set**: the aggregator walks
a curated alias table (`_STAT_FIELD_MAP`) to map display names like
`"Total Output Boost"` → `StatTotals.total_output_boost`. Anything that
doesn't match a canonical field lands in `StatTotals.other` keyed by the
original display name, so OCR-discovered stats outside the catalog still
flow through (the damage formula won't use them, but the simulator can
still surface them in its response).

See PROJECT.md §11 for the formula skeleton this feeds; RESEARCH.md §3.3
for the canonical stat catalog.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..schemas.arcana import ArcanaScroll
from ..schemas.gear import ParsedGear
from ..schemas.simulation import StatTotals
from ..schemas.trait import TraitNode

# ---------------------------------------------------------------------------
# Stat-name → StatTotals attribute resolution
# ---------------------------------------------------------------------------
# Lower-cased / punctuation-stripped display names → StatTotals attribute.
# Multiple aliases per attribute cover the variants seen in-game and in the
# datamined catalog (e.g. "HP" vs "Health" both → `health`).
_STAT_FIELD_MAP: dict[str, str] = {
    # --- Damage scaling (percentage stats) -------------------------------
    "total output boost": "total_output_boost",
    "total damage bonus": "total_damage_bonus",
    "damage bonus": "total_damage_bonus",  # tooltip sometimes drops "Total"
    "ability damage bonus": "ability_damage_bonus",
    "primary damage bonus": "primary_damage_bonus",
    "primary attack bonus": "primary_damage_bonus",
    "boss damage": "boss_damage",
    "bonus damage against bosses": "boss_damage",
    "close-range damage": "close_range_damage",
    "close range damage": "close_range_damage",
    "bonus damage against close-range enemies": "close_range_damage",
    "damage bonus against healthy enemies": "healthy_enemy_damage",
    "damage vs healthy enemies": "healthy_enemy_damage",
    # --- Precision channel ------------------------------------------------
    "precision rate": "precision_rate",
    "precision damage": "precision_damage",
    # --- Crit channel -----------------------------------------------------
    "critical hit rate": "crit_rate",
    "crit rate": "crit_rate",
    "critical damage": "crit_damage",
    "crit damage": "crit_damage",
    # --- Debuffs ----------------------------------------------------------
    "vulnerability inflicted": "vulnerability_inflicted",
    # --- Cooldowns --------------------------------------------------------
    "cooldown reduction": "cooldown_reduction",
    "rune cooldown reduction": "rune_cooldown_reduction",
    "healing rune cooldown reduction": "rune_cooldown_reduction",
    # --- Survivability (flat) --------------------------------------------
    "hp": "health",
    "health": "health",
    "armor value": "armor_value",
    "block rate": "block_rate",
    "block damage reduction": "block_damage_reduction",
    "dodge rate": "dodge_rate",
}


def _normalize_stat_key(name: str) -> str:
    """Lowercase + strip stray spacing for alias lookup."""
    return name.strip().lower()


def _resolve_field(name: str) -> str | None:
    """Map a stat display name to a `StatTotals` attribute, or None if unknown."""
    return _STAT_FIELD_MAP.get(_normalize_stat_key(name))


def _add(totals: StatTotals, name: str, value: float) -> None:
    """Add a stat contribution to the right `StatTotals` field (or `.other`)."""
    field = _resolve_field(name)
    if field is None:
        # Preserve the OCR'd / catalogued name as-is so the frontend can show
        # the unmapped stat in its breakdown.
        totals.other[name] = totals.other.get(name, 0.0) + value
        return
    setattr(totals, field, getattr(totals, field) + value)


# ---------------------------------------------------------------------------
# Aggregation entry point
# ---------------------------------------------------------------------------
def aggregate_stats(
    *,
    gear: Iterable[ParsedGear] = (),
    trait_alloc: dict[str, int] | None = None,
    arcana_ids: Iterable[str] = (),
    traits_catalog: Iterable[TraitNode] = (),
    arcana_catalog: Iterable[ArcanaScroll] = (),
) -> StatTotals:
    """Sum every stat contribution from gear, traits, and arcana.

    Args:
        gear: equipped gear pieces (typically 4: weapon/armor/accessory/exclusive).
        trait_alloc: `{node_id: points_allocated}` from the player's tree.
        arcana_ids: equipped Arcana scroll ids (e.g. `["scroll_of_conquest"]`).
        traits_catalog: every trait node from `data_loader.load_game_data().traits`.
            Required to look up `node_id` → effects + multipliers.
        arcana_catalog: every Arcana scroll from `data_loader.load_game_data().arcana`.
            Required to look up `arcana_id` → effects.

    Returns:
        A populated `StatTotals` ready to hand to `damage_calc.simulate`.

    The aggregator never mutates its inputs and never raises on unknown ids
    (a missing trait node or arcana scroll just contributes nothing). This
    keeps the simulator robust against game-data drift between patches.
    """
    totals = StatTotals()

    # --- Gear: walk both base_effects and extended_effects ------------------
    for piece in gear:
        for be in piece.base_effects:
            _add(totals, be.name, be.value)
        for ee in piece.extended_effects:
            _add(totals, ee.stat_id, ee.value)

    # --- Traits: per-point scaling, optionally multiplicative ---------------
    trait_alloc = trait_alloc or {}
    trait_lookup = {node.node_id: node for node in traits_catalog}
    for node_id, points in trait_alloc.items():
        node = trait_lookup.get(node_id)
        if node is None or points <= 0:
            continue
        for trait_effect in node.effects:
            # Multiplicative trait effects are rare but some exist; for now we
            # treat them additively too (deliberate MVP simplification — flag
            # for future: separate multiplicative bucket per RESEARCH.md §6).
            contribution = trait_effect.per_point * points
            _add(totals, trait_effect.stat, contribution)

    # --- Arcana: flat per-scroll contribution -------------------------------
    arcana_lookup = {scroll.id: scroll for scroll in arcana_catalog}
    for arcana_id in arcana_ids:
        scroll = arcana_lookup.get(arcana_id)
        if scroll is None:
            continue
        for arcana_effect in scroll.effects:
            # `multiplicative` flag from arcana.seed.json indicates a
            # percentage-style modifier; we collapse to the same additive
            # bucket and let the damage formula divide by 100. This matches
            # PROJECT.md §11's pseudocode (single Arcana_multiplier term).
            _add(totals, arcana_effect.stat, arcana_effect.value)

    return totals
