"""F2 Gear Roll Evaluator — score a single gear piece against a build context.

Pure-Python scoring math. No I/O, no DB, no Tesseract. The router pulls
``GameData`` from ``data_loader.load_game_data()`` and hands it in.

**Score formula** (per PROJECT.md §3 F2 + RESEARCH.md §3.1/§3.4):

    For each extended effect on the gear:
        weight = stat_weights.get(stat_id, 0.0)
        s_tier_max = catalog[stat_id].tiers["S"].max
        contribution = value * weight / s_tier_max

    score = sum(contribution) / max_extended_effects_for_rarity * 100
    score = min(score, 100.0)  # clamp; multi-stat absurd weights can exceed

A score of 100 means every rarity-allowed slot rolled at S-tier-max value
on the build's highest-weighted stat. Lower score = either fewer slots
filled, lower tier, lower value, or rolls landing on stats the build
doesn't care about.

``base_effects`` do NOT contribute to the score in V1 — they're slot-
determined and don't differentiate rolls of the same slot+rarity. Revisit
if base-effect rolls turn out to be variable per-piece.

**Two sentinel exceptions** (``UnknownHeroError``, ``UnknownAbilityError``) so the
router can map them cleanly to HTTP 422 without relying on string matching.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..data_loader import GameData
from ..schemas.common import StatId
from ..schemas.gear import ParsedGear
from ..schemas.roll_score import (
    BuildContext,
    ForgeAction,
    RollScoreResult,
    StatBreakdown,
    ThresholdTier,
)

# Per-rarity extended-effect counts (RESEARCH.md §3.1, confirmed against
# user screenshots 2026-04-27). Anchors the scoring denominator.
_MAX_EXTENDED_EFFECTS: dict[str, int] = {
    "normal": 0,
    "advanced": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 5,
}

# Threshold band cuts, exclusive lower bound on the higher band:
#   [0, 20)   trash
#   [20, 40)  filler
#   [40, 60)  keep
#   [60, 80)  bis_candidate
#   [80, 100] leaderboard_grade
_THRESHOLD_CUTS: list[tuple[float, ThresholdTier]] = [
    (20.0, "trash"),
    (40.0, "filler"),
    (60.0, "keep"),
    (80.0, "bis_candidate"),
]

# 1:1 mapping from threshold to forge action; "keep" has a downgrade case
# applied in `suggest_forge_action`.
_FORGE_BY_THRESHOLD: dict[ThresholdTier, ForgeAction] = {
    "trash": "smelt",
    "filler": "use_temporarily",
    "keep": "reroll_low_tiers",
    "bis_candidate": "keep",
    "leaderboard_grade": "lock",
}

_LOW_TIERS: frozenset[str] = frozenset({"C", "D"})


# ---------------------------------------------------------------------------
# Sentinel exceptions
# ---------------------------------------------------------------------------
class UnknownHeroError(ValueError):
    """Raised when ``BuildContext.hero_id`` doesn't match any hero in the catalog."""


class UnknownAbilityError(ValueError):
    """Raised when ``BuildContext.ability_id`` doesn't match any ability for that hero."""


# ---------------------------------------------------------------------------
# Stat weight resolution
# ---------------------------------------------------------------------------
def _normalize(weights: dict[StatId, float]) -> dict[StatId, float]:
    """Scale weights so they sum to 1.0. Returns ``{}`` if the sum is non-positive."""
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in weights.items()}


def derive_stat_weights(
    *,
    hero_id: str | None,
    ability_id: str | None,
    game_data: GameData,
) -> dict[StatId, float]:
    """Resolve a build's stat weights from hero / ability metadata.

    See ``BuildContext`` for the resolution-order contract. Raises
    ``UnknownHeroError`` / ``UnknownAbilityError`` when the caller-provided id
    doesn't match the catalog.
    """
    if hero_id is None:
        # Generic fallback — Total Output Boost is universally best per
        # RESEARCH.md §3.4. Already normalized (single key sums to 1.0).
        return {"Total Output Boost": 1.0}

    hero = next((h for h in game_data.heroes if h.id == hero_id), None)
    if hero is None:
        raise UnknownHeroError(f"unknown hero_id: {hero_id!r}")

    if ability_id is not None:
        ability = next((a for a in hero.abilities if a.id == ability_id), None)
        if ability is None:
            raise UnknownAbilityError(
                f"unknown ability_id {ability_id!r} for hero {hero_id!r}"
            )
        raw: dict[StatId, float] = {}
        for s in ability.scaling:
            raw[s.stat] = raw.get(s.stat, 0.0) + s.coefficient
        return _normalize(raw)

    # Hero only — sum coefficients across every ability the hero owns.
    summed: dict[StatId, float] = defaultdict(float)
    for ability in hero.abilities:
        for s in ability.scaling:
            summed[s.stat] += s.coefficient
    return _normalize(dict(summed))


def _resolve_weights(
    build: BuildContext, *, game_data: GameData
) -> dict[StatId, float]:
    """Apply the BuildContext resolution order in one place."""
    if build.stat_weights:  # non-empty dict wins
        return dict(build.stat_weights)
    return derive_stat_weights(
        hero_id=build.hero_id,
        ability_id=build.ability_id,
        game_data=game_data,
    )


# ---------------------------------------------------------------------------
# Catalog lookup
# ---------------------------------------------------------------------------
def _catalog_lookup(game_data: GameData) -> dict[str, dict[str, Any]]:
    """Index gear-stats catalog by stat_id for O(1) tier-range lookup."""
    return {
        str(entry.get("stat_id", "")): entry
        for entry in game_data.gear_stats
        if entry.get("stat_id")
    }


def _s_tier_max(catalog_entry: dict[str, Any]) -> float | None:
    """Pull the S-tier max from a catalog entry's ``tiers`` list."""
    for tier in catalog_entry.get("tiers", []):
        if tier.get("tier") == "S":
            try:
                return float(tier["max"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


# ---------------------------------------------------------------------------
# Threshold + forge action
# ---------------------------------------------------------------------------
def classify_threshold(score: float) -> ThresholdTier:
    """Five-band classifier matching ``ThresholdTier``."""
    for cutoff, label in _THRESHOLD_CUTS:
        if score < cutoff:
            return label
    return "leaderboard_grade"


def suggest_forge_action(
    threshold: ThresholdTier, gear: ParsedGear
) -> ForgeAction:
    """Map threshold → forge action with the "keep + no low-tier rolls" downgrade.

    A "keep"-tier piece with no C-or-D-tier extended effects has nothing
    worth rerolling, so we soften the action from ``reroll_low_tiers``
    back to plain ``keep``.
    """
    action = _FORGE_BY_THRESHOLD[threshold]
    if threshold == "keep":
        has_low_tier = any(e.tier in _LOW_TIERS for e in gear.extended_effects)
        if not has_low_tier:
            return "keep"
    return action


# ---------------------------------------------------------------------------
# Explanation string
# ---------------------------------------------------------------------------
_RARITY_WORD: dict[str, str] = {
    "normal": "Normal",
    "advanced": "Advanced",
    "rare": "Rare",
    "epic": "Epic",
    "legendary": "Legendary",
}

# Forge advice phrases keyed by action — short, frontend can elaborate.
_FORGE_ADVICE: dict[ForgeAction, str] = {
    "smelt": "Smelt for Uru Shards.",
    "use_temporarily": "Slot it for now; replace at the next forge stack.",
    "keep": "Keep — nothing low enough to reroll productively.",
    "reroll_low_tiers": "Reroll the low-tier rows to push higher.",
    "lock": "Lock it.",
}


def _build_explanation(
    *,
    gear: ParsedGear,
    score: float,
    relevant_count: int,
    total_effects: int,
    uncatalogued_count: int,
    forge_action: ForgeAction,
) -> str:
    """Compose the human-readable summary."""
    rarity_word = _RARITY_WORD.get(gear.rarity, gear.rarity.capitalize())
    if total_effects == 0:
        # Normal-rarity (or otherwise effect-less). Don't mention "X of 0".
        return (
            f"{rarity_word} piece at {score:.0f}/100. "
            f"No extended-effect rolls to evaluate. {_FORGE_ADVICE[forge_action]}"
        )
    base = (
        f"{rarity_word} at {score:.0f}/100. "
        f"{relevant_count} of {total_effects} extended effects on build-relevant stats"
    )
    if uncatalogued_count:
        base += f", {uncatalogued_count} uncatalogued"
    return f"{base}. {_FORGE_ADVICE[forge_action]}"


# ---------------------------------------------------------------------------
# Scoring entry point
# ---------------------------------------------------------------------------
def compute_roll_score(
    gear: ParsedGear,
    build: BuildContext,
    *,
    game_data: GameData,
) -> RollScoreResult:
    """Score a gear roll against the build's stat priorities.

    Returns a ``RollScoreResult`` populated with the score, threshold band,
    forge recommendation, per-row breakdown, the resolved stat-weight map,
    a list of uncatalogued stats encountered, and a one-line explanation
    suitable for the frontend.

    Caller is responsible for handling sentinel exceptions
    (``UnknownHeroError`` / ``UnknownAbilityError``) when ``BuildContext`` references
    catalog entries that don't exist — typically by mapping them to HTTP 422.
    """
    weights = _resolve_weights(build, game_data=game_data)
    catalog = _catalog_lookup(game_data)

    breakdowns: list[StatBreakdown] = []
    uncatalogued: list[str] = []

    for ee in gear.extended_effects:
        weight = weights.get(ee.stat_id, 0.0)
        catalog_entry = catalog.get(ee.stat_id)

        if catalog_entry is None:
            uncatalogued.append(ee.stat_id)
            breakdowns.append(
                StatBreakdown(
                    stat_id=ee.stat_id,
                    weight=weight,
                    tier=ee.tier,
                    value=ee.value,
                    in_catalog=False,
                    s_tier_max=None,
                    normalized_contribution=0.0,
                )
            )
            continue

        s_max = _s_tier_max(catalog_entry)
        if s_max is None or s_max <= 0:
            # Catalogued but no usable S-tier max — treat as uncatalogued for
            # scoring purposes. (Won't crash on a malformed seed entry.)
            uncatalogued.append(ee.stat_id)
            breakdowns.append(
                StatBreakdown(
                    stat_id=ee.stat_id,
                    weight=weight,
                    tier=ee.tier,
                    value=ee.value,
                    in_catalog=True,
                    s_tier_max=s_max,
                    normalized_contribution=0.0,
                )
            )
            continue

        contribution = (ee.value * weight) / s_max
        breakdowns.append(
            StatBreakdown(
                stat_id=ee.stat_id,
                weight=weight,
                tier=ee.tier,
                value=ee.value,
                in_catalog=True,
                s_tier_max=s_max,
                normalized_contribution=contribution,
            )
        )

    max_slots = _MAX_EXTENDED_EFFECTS.get(gear.rarity, 0)
    if max_slots == 0:
        score = 0.0
    else:
        # Sum normalized contributions, normalize by slot count, scale to 100.
        # Clamp at 100 — synthetic absurd weights (e.g. multiple stats each at
        # weight 1.0) can technically push the sum past the slot count.
        raw_score = sum(b.normalized_contribution for b in breakdowns) / max_slots * 100
        score = min(raw_score, 100.0)

    threshold = classify_threshold(score)
    forge_action = suggest_forge_action(threshold, gear)

    relevant_count = sum(
        1 for b in breakdowns if b.in_catalog and b.weight > 0
    )

    return RollScoreResult(
        score=score,
        threshold=threshold,
        forge_action=forge_action,
        # V1 percentile placeholder = score itself. Real Monte Carlo
        # distribution lands in a follow-up (PROJECT.md §3 F2).
        # TODO: replace with a synthetic distribution over the catalog's
        # tier-range probabilities.
        percentile=score,
        breakdown=breakdowns,
        stat_weights_used=weights,
        uncatalogued_stats=uncatalogued,
        explanation=_build_explanation(
            gear=gear,
            score=score,
            relevant_count=relevant_count,
            total_effects=len(gear.extended_effects),
            uncatalogued_count=len(uncatalogued),
            forge_action=forge_action,
        ),
    )
