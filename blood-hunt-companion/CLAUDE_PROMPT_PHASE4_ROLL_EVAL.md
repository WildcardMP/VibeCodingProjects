# Claude Code Prompt — Phase 4 Kickoff: F2 Gear Roll Evaluator (API skeleton)

> Drop into Claude Code as a single message, or save in repo root and trigger with:
> `Read and execute the instructions in CLAUDE_PROMPT_PHASE4_ROLL_EVAL.md.`

---

## Context

Phase 3 F1 backend MVP shipped at commit `bef56cb` (197 tests green, `POST /api/simulate` live). Phase 2 OCR fixture-accuracy gate (`test_ocr_fixtures.py` ≥9/10) remains user-gated — only 3 of 10+ fixtures are committed (`03a3d48`).

This prompt is the next backend chunk: **F2 Gear Roll Evaluator** per `PROJECT.md` §3 F2 and `RESEARCH.md` §3.4.

The user's daily decision is "I just rolled this legendary — keep, reroll extended effects, or shard for Uru?" At ~200K shards per stack-of-10 forge attempt, every wrong call costs a session's worth of grinding. F2 turns that decision into a number.

### What's already on the shelf you'll reuse

- `app/services/stat_aggregator.py` — gear/trait/arcana stat folding, alias table, percentage-vs-flat unit convention. F2 doesn't need to re-do this.
- `app/services/damage_calc.py` — damage formula (out of scope for F2 directly, but the *stat priority weights* the user cares about are derivable from each ability's `scaling` list).
- `app/schemas/simulation.py` — `StatTotals` shape and `other` catch-all for OCR-discovered stats.
- `app/schemas/gear.py` — `ParsedGear`, `BaseEffect`, `ExtendedEffect`. Gear comes in here exactly as it does to the simulator.
- `data/game/gear_stats.seed.json` — 12 stats with **D/C/B/A/S tier ranges (`min`, `max`)**. This is the canonical "what's a good roll" reference.
- `data/game/heroes.seed.json` — SG `burst_acorn`, `squirrel_friends` and MK `ankh`, `moon_blade` with `scaling: [{stat, coefficient}, ...]`. F2 derives default stat weights from this.

---

## What you are building (Phase 4a — F2 API only)

### In scope (this PR)

1. **Pydantic schemas** — `RollScoreRequest`, `BuildContext`, `RollScoreResult`, `RollScoreBreakdown`. New module `app/schemas/roll_score.py`.
2. **Service module** `app/services/roll_score.py` — pure scoring math.
3. **Endpoint** `POST /api/gear/score` (matches `PROJECT.md` §8) — stateless, takes a gear piece + build context, returns score + threshold + forge recommendation.
4. **Tests** — score correctness against hand-computed cases, threshold boundary tests, forge-action mapping, build-weight derivation, edge cases.

### Anti-scope (do NOT do this PR)

- No frontend.
- No DB persistence of scoring results. Stateless only.
- **Do not modify `gear_stats.seed.json`** to fill in missing stats (the catalog is intentionally lean; F2 must handle uncatalogued stats gracefully — see "Stats outside the catalog" below).
- **Do not modify `damage_calc.py` or `stat_aggregator.py`.** F2 reads from the same seed data but does its own scoring math; it does NOT call `simulate()`.
- No multi-piece comparison endpoint. Caller compares two pieces by calling `/api/gear/score` twice and diffing.
- No FModel coefficient calibration (separate prompt later).
- No F4 Forge ROI work — separate prompt after F2 lands.
- No new top-level dependencies. All math is stdlib + pydantic.
- Do not import from `app/ocr/*`. Zero coupling to OCR.

---

## Required reading before you write the plan

- `CLAUDE.md` §3 (operating rules), §3.1 (plan format), §3.2 (tests non-optional), §3.3 (mypy --strict), §3.4 (one concern per module), §3.7 (sample-size honesty — relevant for the percentile claim shape), §12 (anti-patterns).
- `PROJECT.md` §3 F2 (problem / inputs / outputs — this is your contract), §8 (endpoint table — `POST /api/gear/score`), §10 (game-data JSON schemas — `gear_stats.json` shape).
- `RESEARCH.md` §3.1 (rarity → extended-effect count: legendary=5, epic=3, rare=2, advanced=1, normal=0), §3.2 (extended-effect tiers D/C/B/A/S — the ramp), §3.3 (canonical stat name catalog), §3.4 (stat priority by build — **the source of truth for default weights**), §3.5–3.6 (drop sources, level cap), §4.2 (forge math context — 200K shards per stack-of-10).
- `apps/api/app/services/stat_aggregator.py` (current alias table — do NOT duplicate it; export and reuse if needed).
- `apps/api/app/schemas/simulation.py` (current `StatTotals` shape, including `other: dict[str, float]` catch-all convention).
- `apps/api/app/schemas/gear.py` (`ParsedGear`, `BaseEffect`, `ExtendedEffect`).
- `data/game/gear_stats.seed.json` (the 12 stats and their tier ranges — read this, you will reference these names verbatim).
- `data/game/heroes.seed.json` (ability `scaling` lists — used to derive default stat weights when caller provides only `hero_id`).

---

## Plan format

Per `CLAUDE.md` §3.1, write a plan **before** code. Plan must cover:

1. **Files I will create / modify** — concrete paths.
2. **Public surface** — schemas, function signatures, endpoint signature.
3. **Tests I will add** — test file paths and at least one sentence per test describing what it asserts.
4. **Open questions** — flag anything that affects schema shape or the scoring formula. If the question affects only internal naming or test fixture values, decide and document inline. If it would change the response shape, **stop and ask Cowork before coding.**

---

## Detailed spec

### Schemas — `apps/api/app/schemas/roll_score.py` (new)

```python
from typing import Literal
from pydantic import BaseModel, Field
from .common import StatId
from .gear import ParsedGear

ThresholdTier = Literal["trash", "filler", "keep", "bis_candidate", "leaderboard_grade"]
ForgeAction = Literal["smelt", "use_temporarily", "keep", "reroll_low_tiers", "lock"]

class BuildContext(BaseModel):
    """How the caller tells F2 which stats matter for THIS build.

    Resolution order (first match wins):
      1. If `stat_weights` is provided non-empty → use it verbatim. Caller has full control.
      2. Else if `hero_id` (and optionally `ability_id`) is provided → derive weights from
         the hero's ability `scaling` lists. If `ability_id` given, weight = that ability's
         coefficients normalized; if not, weight = sum across all hero abilities, normalized.
      3. Else → "generic" defaults: Total Output Boost = 1.0, everything else = 0.0.
         (Per RESEARCH.md §3.4: TOB is universally best.)
    """
    hero_id: str | None = None
    ability_id: str | None = None
    stat_weights: dict[StatId, float] | None = Field(default=None,
        description="Optional explicit weights. When set, overrides hero/ability derivation.")

class RollScoreRequest(BaseModel):
    gear: ParsedGear
    build: BuildContext = Field(default_factory=BuildContext)

class StatBreakdown(BaseModel):
    """Per-stat contribution detail. Useful for the frontend tooltip / debugging."""
    stat_id: StatId
    weight: float                      # build-context weight (0..1)
    tier: str | None                   # "S".."D" or None for base_effects (no per-row tier)
    value: float
    in_catalog: bool                   # True if stat appears in gear_stats.seed.json
    s_tier_max: float | None           # the catalog's S-tier max for this stat, or None
    normalized_contribution: float     # value * weight / s_tier_max, or 0.0 if not in catalog

class RollScoreResult(BaseModel):
    score: float = Field(ge=0.0, le=100.0,
        description="0–100. 100 = a hypothetical roll with all five extended effects at S-tier-max "
                    "AND all on the build's highest-weighted stats.")
    threshold: ThresholdTier
    forge_action: ForgeAction
    percentile: float = Field(ge=0.0, le=100.0,
        description="Approximate percentile vs. a synthetic uniform distribution over the gear's "
                    "rarity-allowed extended-effect slots. Read with sample-size humility.")
    breakdown: list[StatBreakdown]
    stat_weights_used: dict[StatId, float] = Field(
        description="Echoes whatever weight resolution produced — caller can verify it matches "
                    "their intent.")
    uncatalogued_stats: list[str] = Field(default_factory=list,
        description="Stat names on the gear that were NOT in gear_stats.seed.json. They contributed "
                    "0 to the score; surface for the user to investigate (likely either a typo "
                    "in OCR or a real catalog gap).")
    explanation: str = Field(
        description="One- or two-sentence human-readable summary. Example: 'Mid-roll legendary "
                    "(64/100). Three extended effects on relevant stats, two filler. Consider "
                    "rerolling the D-tier Block Damage Reduction.' Frontend can show as-is.")
```

Re-export from `apps/api/app/schemas/__init__.py`.

### Service — `apps/api/app/services/roll_score.py` (new)

Public surface:

```python
def derive_stat_weights(
    *,
    hero_id: str | None,
    ability_id: str | None,
    game_data: GameData,
) -> dict[StatId, float]: ...

def compute_roll_score(
    gear: ParsedGear,
    build: BuildContext,
    *,
    game_data: GameData,
) -> RollScoreResult: ...
```

**Implementation rules:**

#### 1. Resolve stat weights (`BuildContext` → `dict[StatId, float]`)

Follow the resolution order documented on `BuildContext`:

- Explicit `stat_weights` provided → use as-is. Validate keys exist in the gear-stats catalog OR in `aliases.json` from `stat_aggregator` (whichever is canonical) — surface unknowns in `uncatalogued_stats`. Don't auto-normalize; trust the caller.
- `hero_id` (+/- `ability_id`) → look up hero in `game_data.heroes`. If `ability_id`, find that ability and use its `scaling` list. Else, sum each stat's coefficient across all the hero's abilities. Normalize: `weights[stat] = coefficient / sum(coefficients)` so weights sum to 1.0.
- Neither → return `{"Total Output Boost": 1.0}`. (Per `RESEARCH.md` §3.4: universally best stat.)

If `hero_id` doesn't exist in `game_data.heroes` → 422.
If `ability_id` doesn't exist for that hero → 422.

#### 2. Score the piece

For the gear's `extended_effects`:

```
For each (stat_id, tier, value) in gear.extended_effects:
    weight = stat_weights.get(stat_id, 0.0)
    catalog_entry = next((s for s in game_data.gear_stats if s["stat_id"] == stat_id), None)
    if catalog_entry is None:
        # Surface as uncatalogued; contributes 0 to score.
        record StatBreakdown(weight, tier, value, in_catalog=False, s_tier_max=None,
                             normalized_contribution=0.0)
        append stat_id to uncatalogued_stats
        continue
    s_tier_max = catalog_entry["tiers"][where tier=="S"].max
    contribution = value * weight / s_tier_max
    record StatBreakdown(weight, tier, value, in_catalog=True, s_tier_max=s_tier_max,
                         normalized_contribution=contribution)
```

Score formula:

```
max_extended_effects_for_rarity = {
    "normal":    0,  # 0 effects → score is always 0.0 (no rolls to evaluate)
    "advanced":  1,
    "rare":      2,
    "epic":      3,
    "legendary": 5,
}[gear.rarity]

if max_extended_effects_for_rarity == 0:
    score = 0.0
else:
    # Theoretical max: every slot S-tier max on the build's #1 weighted stat (weight ≤ 1.0).
    # When weights normalize to 1.0 total, max contribution per slot is exactly 1.0.
    score = sum(contribution for breakdown in breakdowns) / max_extended_effects_for_rarity * 100
    score = min(score, 100.0)  # clamp; some edge cases (multi-stat rolls all on top stats) can exceed
```

Score is clamped 0..100. Document the clamping in a code comment.

`base_effects` do NOT contribute to the score in V1 — they're slot-determined and don't differentiate rolls. Note this in a code comment with a `TODO: revisit if base_effect rolls are confirmed variable per-piece.`

#### 3. Threshold + forge action

```
def classify_threshold(score: float) -> ThresholdTier:
    if score < 20: return "trash"
    if score < 40: return "filler"
    if score < 60: return "keep"
    if score < 80: return "bis_candidate"
    return "leaderboard_grade"

def suggest_forge_action(threshold: ThresholdTier, gear: ParsedGear) -> ForgeAction:
    if threshold == "trash":              return "smelt"
    if threshold == "filler":             return "use_temporarily"
    if threshold == "keep":               return "reroll_low_tiers"  # if any extended effect is C or D
    if threshold == "bis_candidate":      return "keep"
    if threshold == "leaderboard_grade":  return "lock"
```

Special-case in `suggest_forge_action`: if `threshold == "keep"` but no extended effect is C-or-D-tier, downgrade the action to plain `"keep"` (no point rerolling all-B-or-better rolls).

#### 4. Percentile (approximate)

For a quick V1 percentile, treat the score itself as the percentile (since scoring is normalized 0..100 against theoretical max). Document this is a placeholder:

```python
percentile = score  # V1 placeholder — real Monte Carlo distribution lands in a follow-up.
```

This is the most defensible thing to ship without a real synthetic distribution. Add a `TODO` referencing `PROJECT.md` §3 F2 for the real implementation.

#### 5. Explanation string

Build it from the breakdown:

```
"<rarity_word> piece at score X/100. [Y of Z] extended effects on build-relevant stats, [W] uncatalogued. [Forge advice]."
```

Examples:
- `"Legendary at 64/100. 4 of 5 extended effects on build-relevant stats, 0 uncatalogued. Reroll the D-tier Block Damage Reduction to push higher."`
- `"Epic at 18/100. 0 of 3 extended effects on build-relevant stats. Smelt for Uru Shards."`
- `"Legendary at 91/100. 5 of 5 effects on top stats. Lock it."`

Keep the string under 200 characters. The frontend can elaborate.

### Router — `apps/api/app/routers/gear.py` (modify) OR new module

Look at how `routers/simulation.py` handles this — match its pattern (`Depends` for `GameData` injection, `HTTPException(422)` for invalid input). Add the route to the existing `gear` router (since the path is `/api/gear/score`):

```python
@router.post("/api/gear/score", response_model=RollScoreResult)
def score_gear(
    req: RollScoreRequest,
    game_data: GameData = Depends(_game_data),
) -> RollScoreResult:
    return roll_score.compute_roll_score(req.gear, req.build, game_data=game_data)
```

If `gear.py` doesn't already use a `Depends(_game_data)` pattern, lift the helper from `routers/simulation.py` into a shared `routers/_deps.py` module (cleaner than duplicating). Note the move in your plan if you do.

422 cases:
- Unknown `hero_id` (when provided).
- Unknown `ability_id` (when provided alongside a valid hero_id).
- Empty `gear.extended_effects` AND `gear.rarity != "normal"` — that's a parsing artifact, not a valid roll. (Normals can have 0 effects legitimately.)

### Tests — `apps/api/tests/services/test_roll_score.py` and `apps/api/tests/test_gear_score_router.py`

Build a synthetic `GameData` fixture (reuse `tests/services/conftest.py` patterns from F1 if possible — the simulator tests already build one). Include:
- Two heroes, SG (burst_acorn scales on `Total Output Boost` + `Precision Damage`) and MK (ankh scales on `Total Output Boost` + `Boss Damage`).
- Three stats in catalog: `Total Output Boost` (S-tier max 8500), `Precision Damage` (S-tier max 8500), `Boss Damage` (S-tier max 4500).

**Weight derivation tests:**
- `derive_stat_weights(hero_id="squirrel_girl", ability_id=None)` → weights aggregated across both SG abilities, normalized.
- `derive_stat_weights(hero_id="squirrel_girl", ability_id="burst_acorn")` → just that ability's coefficients normalized.
- Explicit `stat_weights` in `BuildContext` overrides hero/ability derivation.
- No hero, no weights → `{"Total Output Boost": 1.0}`.
- Unknown `hero_id` raises 422 (test through router).
- Unknown `ability_id` for a valid hero raises 422.

**Scoring math tests:**
- Legendary with 5 extended effects all S-tier at S-tier-max value, all on stats with weight 1.0 each (caller-provided absurd weights) → score is clamped to 100.
- Legendary with 5 extended effects all S-tier at S-tier-max, weights normalized to sum to 1.0 → score is exactly 100.
- Same piece but all stats have weight 0 → score is 0.
- Legendary with 1 effect at S-tier-max on weight=1.0 stat, 4 effects on weight=0 stats → score = `1.0 / 5 * 100 = 20.0`.
- Epic with 3 effects all at A-tier mid-value on weighted stats → score reflects A-tier proportional contribution, no out-of-range artefacts.
- Normal-rarity piece (rarity = "normal") → score 0, threshold "trash", forge_action "smelt", explanation mentions "no rolls to evaluate".
- Uncatalogued stat → counted in `uncatalogued_stats`, contributes 0 to score, doesn't crash.

**Threshold + forge tests:**
- Score 19.9 → "trash" / "smelt".
- Score 20.0 → "filler" / "use_temporarily".
- Score 59.9 with at least one D-tier roll → "keep" / "reroll_low_tiers".
- Score 59.9 with all rolls at B-or-better → "keep" / "keep" (downgrade case).
- Score 80.0 → "leaderboard_grade" / "lock".

**Route tests:**
- `POST /api/gear/score` with a minimal valid SG legendary returns 200 with a parseable `RollScoreResult`.
- `POST /api/gear/score` with `BuildContext.hero_id` unknown → 422.
- `POST /api/gear/score` with `gear.extended_effects=[]` and `rarity="legendary"` → 422.
- `POST /api/gear/score` with explicit `stat_weights` echoes them in `stat_weights_used`.
- Response includes `breakdown` for every extended effect (length matches `gear.extended_effects`).

### Lint / type / boot

- `ruff check apps/api` clean.
- `mypy --strict apps/api` clean.
- `make api` boots without errors.
- Smoke curl with one of the fixture-01 (Runic Armor) `expected.json` payloads:
  ```bash
  curl -X POST http://localhost:8000/api/gear/score \
    -H 'Content-Type: application/json' \
    -d '{"gear": {<fixture_01 expected.json>}, "build": {"hero_id": "moon_knight", "ability_id": "ankh"}}'
  ```

### Things to double-check before declaring done

- All 197 prior tests still pass.
- Phase 2 OCR fixture-skip gate still skips with the canonical "got empty parameter set" message.
- No imports from `app.ocr.*` in the new schema, service, or router code.
- `make lint` and `make test` both green.

---

## Phase 2 deferral statement (include in your commit message body, verbatim)

> Defers Phase 2 acceptance criterion: test_ocr_fixtures.py >=9/10 pass rate
> at TARGET_PASS_RATE=0.9. User fixture capture is at 3 of 10+. Code-side
> Phase 2 (persistence, calibration-free pipeline, tier dual strategy, slot
> detection) remains complete; only the user-gated accuracy gate is open.
> Pivoting to Phase 4 F2 Roll Evaluator per CLAUDE.md sec 10.

---

## What I expect back from you

After your `§3.1` plan, execute. Then report:

(a) Final test count (passing / skipped) and confirmation `test_ocr_fixtures.py` still skips cleanly.
(b) Files created / modified — table or list, same format as the F1 report.
(c) The commit message you used (single commit on `main`, imperative present tense, with the Phase 2 deferral statement in the body).
(d) Anything you noticed that wasn't in the brief — particularly:
    - Any stat referenced in `heroes.seed.json` `scaling` but missing from `gear_stats.seed.json` (real data-consistency bug if found).
    - Any place where the V1 percentile placeholder feels misleading enough to warrant immediate revisiting.
    - Whether the `_deps.py` extraction (if you did one) felt right or noisy.
    - Any case where `BuildContext` resolution order was unclear during implementation.
(e) Confirmation that no `app/ocr/*` files were touched and `test_ocr_fixtures.py` skip behaviour is preserved.
(f) Push status — pushed to `origin/main`, or held locally pending user push.

If `make test`, `make lint`, or `make api` are not green, **do not declare done** — keep the task `in_progress` and surface the failure for triage.

---

## Calibration & follow-up work (NOT this PR)

Future prompts will cover:

1. **Real percentile via Monte Carlo** over the canonical tier-range distribution — replaces the V1 placeholder.
2. **F4 Forge ROI calculator** — uses the same scoring infrastructure to estimate "expected attempts to beat current best."
3. **Multi-piece comparison endpoint** — bulk score N gear pieces and rank them. Probably lands as `POST /api/gear/score/batch`.
4. **Frontend Gear page** — Next.js UI showing the score, threshold pill, forge recommendation. Uses this endpoint.
5. **base_effect contribution to score** — only if confirmed variable per-piece (currently treated as slot-determined and inert).

Don't anticipate any of that this PR. Stay focused on the scoring math + endpoint + tests.
