"""Roll-score schemas — what `POST /api/gear/score` exchanges.

The Phase 4 F2 Gear Roll Evaluator takes a single `ParsedGear` plus a
build-context (which stats matter for THIS hero/ability) and returns a
0-100 quality score, a coarse threshold tier, and a forge action
recommendation. Stateless — no DB writes.

See PROJECT.md §3 F2 for the contract; RESEARCH.md §3.1 for the
per-rarity extended-effect counts that anchor the scoring math.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import StatId
from .gear import ParsedGear

# Five threshold bands the user actually cares about. The numeric cuts live
# in `services.roll_score.classify_threshold` so this Literal stays the
# single source of truth for the *names*.
ThresholdTier = Literal["trash", "filler", "keep", "bis_candidate", "leaderboard_grade"]

# Forge actions map 1:1 from threshold tier with one downgrade case (see
# `services.roll_score.suggest_forge_action`): "keep" with no D/C-tier rolls
# downgrades to plain "keep" because there's nothing low-tier to reroll.
ForgeAction = Literal["smelt", "use_temporarily", "keep", "reroll_low_tiers", "lock"]


class BuildContext(BaseModel):
    """How the caller tells F2 which stats matter for THIS build.

    Resolution order (first match wins):

    1. Non-empty ``stat_weights`` → use verbatim. Caller has full control;
       the service does NOT auto-normalize. Useful for theorycrafting probes
       like "what if I weight Boss Damage 3x?".
    2. ``hero_id`` (and optionally ``ability_id``) → derive from the hero's
       ability ``scaling`` lists in ``heroes.seed.json``. With ``ability_id``,
       weights = that ability's coefficients, normalized to sum to 1.0. Without,
       weights = sum across all the hero's abilities, normalized.
    3. Neither → ``{"Total Output Boost": 1.0}``. Per RESEARCH.md §3.4 TOB is
       universally best.
    """

    hero_id: str | None = None
    ability_id: str | None = None
    stat_weights: dict[StatId, float] | None = Field(
        default=None,
        description=(
            "Optional explicit weights. When set (and non-empty), overrides "
            "hero/ability derivation."
        ),
    )


class RollScoreRequest(BaseModel):
    """Client → server payload for a single gear roll evaluation."""

    gear: ParsedGear
    build: BuildContext = Field(default_factory=BuildContext)


class StatBreakdown(BaseModel):
    """Per-extended-effect contribution detail.

    Frontend uses this to render a per-row tooltip ("this row contributed
    X% to the score because tier S on the build's #1 stat at value Y").
    Tests assert on it for breakdown completeness.
    """

    stat_id: StatId
    weight: float  # build-context weight (typically 0..1 after normalization)
    tier: str | None  # "S".."D"; None for base_effects (don't apply in V1)
    value: float
    in_catalog: bool  # True if stat appears in gear_stats.json
    s_tier_max: float | None  # catalog's S-tier max for this stat, or None if uncatalogued
    normalized_contribution: float  # value * weight / s_tier_max; 0.0 when uncatalogued


class RollScoreResult(BaseModel):
    """Server → client payload — full scoring breakdown for one gear piece."""

    score: float = Field(
        ge=0.0,
        le=100.0,
        description=(
            "0-100. 100 = a hypothetical roll with all rarity-allowed extended "
            "effects at S-tier-max value AND all on the build's highest-weighted "
            "stats. Clamped — synthetic edge cases can technically exceed."
        ),
    )
    threshold: ThresholdTier
    forge_action: ForgeAction
    percentile: float = Field(
        ge=0.0,
        le=100.0,
        description=(
            "Approximate percentile vs. a synthetic distribution over the "
            "rarity-allowed slots. V1 placeholder = score itself; real Monte "
            "Carlo distribution is a follow-up (PROJECT.md §3 F2)."
        ),
    )
    breakdown: list[StatBreakdown]
    stat_weights_used: dict[StatId, float] = Field(
        description=(
            "Echoes whatever weight resolution produced — caller can verify "
            "it matches their intent."
        ),
    )
    uncatalogued_stats: list[str] = Field(
        default_factory=list,
        description=(
            "Stat names on the gear that were NOT in gear_stats.json. They "
            "contributed 0 to the score; surface for the user to investigate "
            "(likely either a typo in OCR or a real catalog gap)."
        ),
    )
    explanation: str = Field(
        description=(
            "One- or two-sentence human-readable summary the frontend can show "
            "as-is. Under 200 chars. Includes the score, how many effects "
            "landed on relevant stats, and a forge nudge."
        ),
    )
