# Claude Code Prompt — Phase 4b: F4 Forge ROI + arcana doc fix + F2 percentile upgrade

> Drop into Claude Code as a single message, or save in repo root and trigger with:
> `Read and execute the instructions in CLAUDE_PROMPT_PHASE4_FORGE_ROI.md.`

---

## Context

Phase 4 F2 Roll Evaluator shipped at `fc02141` (237 tests green, `POST /api/gear/score` live). This prompt lands the next backend chunk: **F4 Forge ROI Calculator** per `PROJECT.md` §3 F4. It bundles three tightly-coupled changes that all hinge on the same Monte Carlo distribution:

1. **F4 Forge ROI** — new endpoint that simulates forge attempts and returns expected-attempts-to-beat-current-piece.
2. **F2 percentile upgrade** — replaces F2's V1 placeholder (`percentile = score`) with the real distribution from F4's Monte Carlo. This was filed as a follow-up when F2 shipped; it lands naturally with F4.
3. **Arcana cost correction** — `PROJECT.md` §3 F4 currently claims forge "opportunity cost (shards not spent on Arcana)." That is **factually wrong**: per `RESEARCH.md` §5.1, Arcana upgrades come from hero EXP / level-ups, not Uru Shards. The two economies don't connect.

### Why bundle all three

F4 needs a canonical "what does a forged piece look like" distribution. F2's percentile needs the same distribution. The arcana correction is one paragraph in PROJECT.md — too small to justify its own PR. Cohesive enough to land together; small enough to stay below `CLAUDE.md` §12's "400-line every-layer PR" anti-pattern.

---

## What you are building (Phase 4b — F4 backend + percentile + doc fix)

### In scope (this PR)

1. **Doc correction** — `PROJECT.md` §3 F4. Replace the wrong "shards not spent on Arcana" parenthetical. Audit `CLAUDE.md` and `README.md` for any similar shards-buy-arcana claim and fix in the same commit. **Do not** modify `RESEARCH.md` §5.1 — it's already correct ("Spend Arcana points earned at level-ups").
2. **F4 schemas** — `apps/api/app/schemas/forge.py` (new). `ForgeROIRequest`, `SimulatedRoll`, `ForgeROIResult`, `ForgeRecommendation`.
3. **F4 service** — `apps/api/app/services/forge_roi.py` (new). Monte Carlo simulator + canonical placeholder drop tables.
4. **F4 endpoint** — `POST /api/forge/roi`. Add to existing `routers/gear.py` OR new `routers/forge.py` (your call — see "Routing decision" below).
5. **F2 percentile upgrade** — modify `services/roll_score.py::compute_roll_score` to call into the F4 Monte Carlo distribution rather than aliasing `percentile = score`. Update `RollScoreResult.percentile` field docstring with the backwards-compat note CC recommended at F2 close-out.
6. **Tests** — F4 service tests, F4 route tests, F2 percentile tests (verify it's no longer aliased to score), regression checks on F2's other behaviour.

### Anti-scope (do NOT do this PR)

- No frontend.
- No DB writes for forge simulations (stateless, like F1/F2).
- No real datamined drop tables. Use the placeholder distributions specified below; gate behind a `meta.placeholder_distributions=True` flag like F1's `placeholder_coefficients`.
- **No arcana scroll cost modeling** — arcana is EXP-driven, not shard-driven. There is nothing to cost in this PR. Don't add a "scroll point cost" field anywhere.
- Do NOT modify `app/services/stat_aggregator.py` or `app/services/damage_calc.py`.
- Do NOT add a multi-piece comparison endpoint. Caller compares forge outcomes by calling `/api/forge/roi` and `/api/gear/score` separately.
- No new top-level dependencies. Monte Carlo uses stdlib `random` (with seedable instance for tests). `numpy` is acceptable if it simplifies the percentile computation, but not required.
- Do not import from `app/ocr/*`. Zero coupling.
- No FModel coefficient calibration in this PR. Separate prompt later.

---

## Required reading before you write the plan

- `CLAUDE.md` §3 (operating rules), §3.1 (plan format), §3.2 (tests non-optional), §3.3 (mypy --strict), §3.4 (one concern per module), §3.7 (sample-size honesty — relevant for the "expected attempts" language), §12 (anti-patterns).
- `PROJECT.md` §3 F4 (problem / inputs / outputs — note the line you're fixing), §8 (endpoint table — `POST /api/forge/roi`), §10 (game-data JSON schemas — `gear_stats.json` shape).
- `RESEARCH.md` §3.1 (rarity → extended-effect count), §3.2 (extended-effect tier ramp), §3.5 (drop sources), §3.6 (gear levels — drop level scales with run difficulty; cap at 60), §4 (full forge system — workflow, math, smelt value), §4.2 specifically (community-observed ~10% legendary rate at level 60, ~200K shards per stack-of-10), §5.1 (Arcana — **read this so you understand exactly why the doc correction matters**).
- `apps/api/app/services/roll_score.py` — `compute_roll_score`, `derive_stat_weights`. F4 reuses these to score simulated rolls.
- `apps/api/app/schemas/roll_score.py` — `BuildContext`, `RollScoreResult`. The `percentile` field is what you're upgrading.
- `apps/api/app/services/__init__.py` — to know what's exported.
- `data/game/gear_stats.seed.json` — the 12 stats with tier ranges. Forge sampling reads these for rarity/tier distributions.
- `data/game/heroes.seed.json` — for `applies_to_slots` cross-reference (which stats can land on which slot).
- `apps/api/tests/services/conftest.py` — the synthetic GameData fixture from F2. Reuse it; extend if needed.

---

## Plan format

Per `CLAUDE.md` §3.1, write a plan **before** code. Plan must cover:

1. **Files I will create / modify** — concrete paths, including the doc files.
2. **Public surface** — schemas, function signatures, endpoint signature.
3. **Tests I will add or modify** — test file paths and at least one sentence per test.
4. **Routing decision** — see below; state which way you went and why.
5. **Open questions** — flag anything that affects schema shape, distribution semantics, or the F2 percentile interface contract.

If your plan diverges from this spec, say which item and why.

---

## Detailed spec

### Doc correction (small but mandatory)

In `PROJECT.md` §3 F4, the current text reads:

> **Outputs:**
> - Expected number of attempts to beat current piece, given datamined drop tables.
> - **Cost in shards, time, and opportunity cost (shards not spent on Arcana).**
> - Break-even threshold: "Don't reroll until your current piece scores below X."

Replace the bolded line with:

> - Cost in shards and time, plus opportunity cost (shards retained for higher-level forge attempts in later sessions, or for cross-hero crafting per RESEARCH.md §4.4).

Then `grep` `CLAUDE.md` and `README.md` for any phrase pairing `shards` and `arcana` as fungible costs. If you find any, fix them with the same framing (shards stay in the forging economy; arcana points are earned via hero EXP). If you find none in those two files, note that in your report. Do **not** modify `RESEARCH.md` §5.1 — it already says the right thing.

Bundle these doc edits into the same commit as the F4 implementation.

### F4 schemas — `apps/api/app/schemas/forge.py` (new)

```python
from typing import Literal
from pydantic import BaseModel, Field
from .common import GearSlot, Rarity, StatId
from .gear import ParsedGear
from .roll_score import BuildContext

ForgeRecommendation = Literal[
    "reroll",        # Expected EV is positive at acceptable confidence.
    "hold",          # Current piece is good; rerolling has neutral or negative EV.
    "lock",          # Current piece is leaderboard-grade; do not consider rerolling.
    "warn_low_probability",  # Beating current would take >500 attempts on average.
]

class ForgeROIRequest(BaseModel):
    """Caller asks: 'I have current_best_piece in slot X. If I roll N attempts at hero level L,
    what's the expected outcome?'"""

    slot: GearSlot
    hero_id: str
    hero_level: int = Field(ge=1, le=60, default=60,
        description="Hero level at the time of forging. Affects rarity distribution per "
                    "RESEARCH.md §4.2 (Jeff lvl 32 vs fresh Jeff). At lvl 60 we use the cap "
                    "distribution; below 60 we scale rarities down (placeholder until FModel).")
    current_best: ParsedGear | None = Field(default=None,
        description="The piece you're trying to beat. Score is computed via F2 with the same "
                    "build context. If None, treats current_best_score as 0 (any forge wins).")
    build: BuildContext = Field(default_factory=BuildContext,
        description="Same BuildContext F2 takes. Determines stat weights for scoring rolls.")
    shard_balance: int | None = Field(default=None, ge=0,
        description="Optional. If provided, the response includes 'attempts_affordable' and "
                    "'shard_cost_total'. Otherwise those fields are None.")
    n_simulations: int = Field(default=10_000, ge=100, le=200_000,
        description="Monte Carlo sample size. Default 10K is fast and stable for the typical "
                    "decision; bump to 100K for tighter confidence intervals.")
    seed: int | None = Field(default=None,
        description="Optional RNG seed for reproducible tests. Production calls leave None.")

class SimulatedRoll(BaseModel):
    """Aggregate stats over the simulated rolls — the *distribution*, not the rolls themselves."""

    p10_score: float
    p50_score: float
    p90_score: float
    mean_score: float
    p_beats_current: float = Field(ge=0.0, le=1.0,
        description="Fraction of N simulations that scored higher than current_best.")
    legendary_rate: float = Field(ge=0.0, le=1.0,
        description="Fraction of N simulations that produced a Legendary rarity (sanity-check on "
                    "the placeholder distribution).")

class ForgeROIResult(BaseModel):
    expected_attempts_to_beat: float | None = Field(default=None,
        description="1 / p_beats_current if non-zero, else None (capped at infinity in practice — "
                    "the recommendation will be 'warn_low_probability').")
    expected_shard_cost: int | None = Field(default=None,
        description="expected_attempts × shard_per_attempt. None if expected_attempts is None.")
    shard_per_attempt: int = Field(
        description="The cost-per-forge constant used. Currently 20_000 at lvl 60 per "
                    "RESEARCH.md §4.2 (200K / 10).")
    attempts_affordable: int | None = Field(default=None,
        description="floor(shard_balance / shard_per_attempt) if shard_balance was provided.")
    p_beat_within_balance: float | None = Field(default=None, ge=0.0, le=1.0,
        description="P(at least one of attempts_affordable rolls beats current). None if "
                    "shard_balance was None.")
    breakeven_score_threshold: float = Field(ge=0.0, le=100.0,
        description="The score below which the *current* piece's expected attempts to beat drops "
                    "to 1 average forge. Computed by binary search over the simulated distribution. "
                    "Use this as 'don't reroll if your current piece is above X'.")
    distribution: SimulatedRoll
    recommendation: ForgeRecommendation
    explanation: str = Field(
        description="One- or two-sentence human summary. Example: 'At score 64/100 you'd need ~7 "
                    "forges (~140K shards) on average to beat. Threshold to start rerolling: 78. "
                    "Recommendation: hold.'")
    meta: dict[str, str | bool] = Field(
        default_factory=lambda: {"placeholder_distributions": True},
        description="Mirrors F1's `placeholder_coefficients` flag. Flips False when FModel "
                    "drop tables land.")
```

Re-export from `apps/api/app/schemas/__init__.py`.

### F4 service — `apps/api/app/services/forge_roi.py` (new)

Public surface:

```python
def simulate_forge(
    req: ForgeROIRequest,
    *,
    game_data: GameData,
    rng: random.Random | None = None,
) -> ForgeROIResult: ...

def sample_one_roll(
    *,
    slot: GearSlot,
    hero_level: int,
    game_data: GameData,
    rng: random.Random,
) -> ParsedGear: ...

def score_distribution_from_simulations(
    samples: Sequence[ParsedGear],
    build: BuildContext,
    *,
    game_data: GameData,
) -> SimulatedRoll: ...

def percentile_for_score(score: float, samples: Sequence[ParsedGear], build: BuildContext, *, game_data: GameData) -> float:
    """Empirical CDF — fraction of samples whose score is <= the given score, *100. Used by F2."""
    ...
```

**Implementation rules:**

#### 1. Placeholder drop tables (canonical for this PR)

Constants at top of `forge_roi.py`. Document each with a `# TODO(calibration):` comment.

```python
# Per RESEARCH.md §4.2: ~10% legendary at lvl 60, "huge variance: 0–3 per stack of 10".
# Below lvl 60 we scale legendary down linearly to 0 at lvl 1; epic scales similarly.
_RARITY_DIST_LVL_60: dict[Rarity, float] = {
    "normal": 0.10,
    "advanced": 0.25,
    "rare": 0.30,
    "epic": 0.25,
    "legendary": 0.10,
}

# Per-extended-effect tier distribution. No primary source; placeholder skew toward middle tiers.
# TODO(calibration): A/B against in-game observations; FModel may carry the real table.
_TIER_DIST: dict[str, float] = {
    "S": 0.05,
    "A": 0.15,
    "B": 0.30,
    "C": 0.30,
    "D": 0.20,
}

# Per RESEARCH.md §4.2: stack of 10 ≈ 200,000 Uru at lvl 60. Pro-rate linearly under 60.
_SHARD_COST_PER_FORGE_LVL_60: int = 20_000
```

`shard_per_attempt = round(_SHARD_COST_PER_FORGE_LVL_60 * (hero_level / 60))` for sub-60 levels.

#### 2. `sample_one_roll`

- Sample `rarity` from `_RARITY_DIST_LVL_60` (or scaled-by-level variant for sub-60).
- Determine `n_extended` per rarity (per `RESEARCH.md` §3.1: normal=0, advanced=1, rare=2, epic=3, legendary=5).
- Determine candidate stats: filter `game_data.gear_stats` by `applies_to_slots` matching `slot`. **If no stats apply to the slot, raise an internal `ValueError`** with a clear message — surface as 500 from the route. (This shouldn't happen for the four canonical slots but is defensive.)
- For each of `n_extended` rolls:
  - Pick a stat uniformly from the candidates.
  - Pick a tier from `_TIER_DIST`.
  - Pick a value uniformly in `[tier.min, tier.max]` from the stat's catalog entry.
  - **Don't repeat the same stat** across rolls on one piece (model the in-game uniqueness — one stat per row). If the candidate pool runs out (legendary needs 5, slot has fewer applicable stats), allow repeats and add a debug-log warning.
- `base_effects` for now: empty list. Slot-determined base effects aren't part of the score per F2's design; populating them adds noise without changing decisions.
- `level = hero_level`, `rating = 0` (rating is the in-game cosmetic; we don't model it for synthetic rolls).
- `hero` and `hero_id` come from `req.hero_id` for traceability.

Return a `ParsedGear`.

#### 3. `simulate_forge` orchestration

```
rng = rng or random.Random(req.seed)
samples = [sample_one_roll(...) for _ in range(req.n_simulations)]
current_score = compute_roll_score(req.current_best, req.build, game_data=game_data).score \
                if req.current_best else 0.0

# Score every sample
sample_scores = [
    compute_roll_score(s, req.build, game_data=game_data).score
    for s in samples
]

# Distribution
dist = SimulatedRoll(
    p10_score = percentile(sample_scores, 10),
    p50_score = percentile(sample_scores, 50),
    p90_score = percentile(sample_scores, 90),
    mean_score = mean(sample_scores),
    p_beats_current = sum(1 for s in sample_scores if s > current_score) / len(sample_scores),
    legendary_rate = sum(1 for r in samples if r.rarity == "legendary") / len(samples),
)

# Expected attempts (handle zero probability gracefully)
if dist.p_beats_current > 0:
    expected_attempts = 1.0 / dist.p_beats_current
    expected_cost = round(expected_attempts * shard_per_attempt)
else:
    expected_attempts = None
    expected_cost = None

# Affordability
if req.shard_balance is not None:
    attempts_affordable = req.shard_balance // shard_per_attempt
    p_beat_within = 1 - (1 - dist.p_beats_current) ** attempts_affordable
else:
    attempts_affordable = None
    p_beat_within = None

# Breakeven score: binary-search the score s* such that P(roll > s*) ≈ 1/expected_attempts ≈ 1.0.
# Practically: the score at which 50%+ of simulations beat it (median of the simulated distribution).
breakeven = dist.p50_score  # median; this is "what an average forge produces"

# Recommendation
if expected_attempts is None:
    recommendation = "warn_low_probability"
elif expected_attempts > 500:
    recommendation = "warn_low_probability"
elif current_score >= 80:
    recommendation = "lock"
elif current_score < breakeven * 0.7:
    recommendation = "reroll"
else:
    recommendation = "hold"
```

The threshold values (80 for lock, 0.7×breakeven for reroll) are heuristics — document them in code comments and surface in the explanation string.

#### 4. F2 percentile upgrade — modify `services/roll_score.py::compute_roll_score`

Replace the V1 placeholder:

```python
percentile = score  # V1 placeholder — real Monte Carlo lands in F4.
```

with:

```python
# Empirical CDF: what fraction of rolls (at this gear's slot/rarity, with this build) score
# at-or-below the current piece. Uses F4's Monte Carlo with a small sample (1K) cached per
# (slot, rarity, build_weights_signature) tuple within process lifetime. Real synthetic
# distribution — no longer aliased to score.
from .forge_roi import percentile_for_score  # late import to avoid cycle if any
percentile = percentile_for_score(score, _cached_samples_for(gear.slot, gear.rarity, build, game_data))
```

Implement `_cached_samples_for` as a module-level `lru_cache`-decorated helper that:
- Takes `(slot, rarity, build_signature, n=1000)`.
- Returns 1000 samples from `sample_one_roll` for that slot/rarity at lvl 60.
- Cached by signature; cache survives within a process restart.

`build_signature` should be a hashable tuple representation of the resolved `stat_weights` — derive it inside the helper.

**Update the docstring** on `RollScoreResult.percentile`:

```python
percentile: float = Field(ge=0.0, le=100.0,
    description="Empirical CDF over a simulated roll distribution for this slot/rarity/build "
                "(N=1000 samples). Read with sample-size humility per CLAUDE.md §3.7. "
                "**Backwards-compat note:** prior to this version the field was aliased to `score` "
                "as a V1 placeholder; consumers that built around the placeholder shape should "
                "expect divergence here.")
```

Update F2 tests where the test asserts `result.percentile == result.score`. They should now assert `0 <= result.percentile <= 100` and `result.percentile != result.score` for at least one non-degenerate case.

### Routing decision

Two acceptable choices:

**A. Add to existing `routers/gear.py`** alongside `score_gear`. The argument: `/api/forge/roi` is conceptually about gear, the file already has the dependency-loading pattern, scope stays small.

**B. New `routers/forge.py`.** The argument: PROJECT.md §6 calls out `routers/forge.py` as a planned module; F4 is "Forge ROI" not "gear scoring"; cleaner if forge ever expands beyond ROI (e.g., smelt-value calc).

Either is fine. Pick one, justify in your plan. If A, leave a `# TODO(forge module)` comment for future migration. If B, mirror the imports from `routers/gear.py` exactly so the patterns stay aligned.

### Tests — `apps/api/tests/services/test_forge_roi.py` and `apps/api/tests/test_forge_roi_router.py` (new), plus modifications to `tests/services/test_roll_score.py` and `tests/test_gear_score_router.py`

**`test_forge_roi.py`:**
- Seeded RNG: with `seed=42, n_simulations=1000`, the result is bitwise-deterministic across runs (regression check).
- `current_best=None` → `p_beats_current ≈ mean_score / 100` (any positive score beats 0).
- `current_best` with score 100 → `p_beats_current == 0`, `expected_attempts is None`, `recommendation == "warn_low_probability"`.
- `current_best` with score 0 → `expected_attempts ≈ 1`, `recommendation == "reroll"`.
- `hero_level=60` produces ~10% legendary rate ± 2% (verifies the placeholder distribution sampling).
- `hero_level=30` produces fewer legendaries than `hero_level=60` (sanity on the level scaling).
- `slot="weapon"` only samples stats with `applies_to_slots` containing `weapon`.
- `n_simulations < 100` is rejected by Pydantic; `n_simulations > 200_000` likewise.
- `shard_balance=200_000` at lvl 60 → `attempts_affordable == 10`.
- `shard_balance=None` → `attempts_affordable == None` and `p_beat_within_balance == None`.

**`test_forge_roi_router.py`:**
- POST with a minimal valid request → 200, parseable `ForgeROIResult`.
- Unknown `hero_id` → 422.
- Unknown `slot` (not in the canonical four) → 422 (Pydantic catches via Literal).
- Response `meta.placeholder_distributions == True`.

**Modifications to existing F2 tests:**
- The test that asserts `result.percentile == result.score` (or implicitly relies on it) needs updating. New assertion: percentile is a float in `[0, 100]` and **for a non-degenerate gear piece (legendary with extended effects on weighted stats), percentile differs from score by at least 1.0** — i.e., the placeholder-vs-real difference is observable.
- Add one positive test: percentile for a known-good legendary (all S-tier rolls on top stats) should be near 100. Percentile for a known-bad legendary (all D-tier rolls on weight=0 stats) should be near 0.
- Lock the docstring update with a test that imports the field's `description` and asserts the backwards-compat phrase is present.

### Lint / type / boot

- `ruff check apps/api` clean.
- `mypy --strict apps/api` clean.
- `make api` boots without errors.
- Smoke curl:
  ```bash
  curl -X POST http://localhost:8000/api/forge/roi \
    -H 'Content-Type: application/json' \
    -d '{"slot":"armor","hero_id":"moon_knight","hero_level":60,"build":{"hero_id":"moon_knight"},"n_simulations":1000,"seed":42}'
  ```

### Things to double-check before declaring done

- All 237 prior tests still pass.
- Phase 2 OCR fixture-skip gate still skips with the canonical "got empty parameter set" message.
- No imports from `app.ocr.*` in the new code.
- F2's percentile change doesn't break existing F2 tests (you'll need to update them, not delete them).
- `make lint` and `make test` both green.

---

## Phase 2 deferral statement (include in your commit message body, verbatim)

> Defers Phase 2 acceptance criterion: test_ocr_fixtures.py >=9/10 pass rate
> at TARGET_PASS_RATE=0.9. User fixture capture is at 3 of 10+. Code-side
> Phase 2 (persistence, calibration-free pipeline, tier dual strategy, slot
> detection) remains complete; only the user-gated accuracy gate is open.
> Continuing Phase 4 backend work per CLAUDE.md sec 10.

---

## What I expect back from you

After your `§3.1` plan, execute. Then report:

(a) Final test count (passing / skipped) and confirmation `test_ocr_fixtures.py` still skips cleanly.
(b) Files created / modified — table or list, same format as F1/F2 reports.
(c) The commit message you used (single commit on `main`, imperative present tense, with the Phase 2 deferral statement in the body).
(d) Anything you noticed that wasn't in the brief — particularly:
    - Any place where the placeholder rarity / tier distribution skew gave counterintuitive results.
    - Any case where the F2 percentile upgrade exposed a regression in F2 tests beyond the docstring + value updates anticipated above.
    - Whether you went with routing decision A (extend `gear.py`) or B (new `forge.py`), and why.
    - Any docs beyond `PROJECT.md` §3 F4 that needed the arcana-shards correction.
(e) Confirmation that no `app/ocr/*` files were touched and `test_ocr_fixtures.py` skip behaviour is preserved.
(f) Confirmation that `RESEARCH.md` §5.1 was NOT modified (it was already correct).
(g) Push status — pushed to `origin/main`, or held locally pending user push.

If `make test`, `make lint`, or `make api` are not green, **do not declare done** — keep the task `in_progress` and surface the failure for triage.

---

## Calibration & follow-up work (NOT this PR)

Future prompts will cover:

1. **Real datamined drop tables** via FModel — replaces `_RARITY_DIST_LVL_60` and `_TIER_DIST` constants. Flips `meta.placeholder_distributions=False`.
2. **Sub-60 hero level scaling** — currently linear; FModel may carry actual per-level rates.
3. **Forge stack-of-10 modeling** — current code costs single forges; per RESEARCH.md §4.2 stack-of-10 has its own variance. Worth modeling once real numbers land.
4. **Stopgap interactive console** — single-file static HTML page that hits all three backend endpoints (simulate, score, forge ROI) so you can interact without a real frontend. Cowork will draft this prompt next.
5. **Frontend Gear and Forge pages** — Next.js, real UI. Phase 3/4 deliverable per PROJECT.md §9.
6. **F1/F2 conftest migration** — F1 tests currently inline their fixtures; the shared `conftest.py` from F2 is a better pattern. Small cleanup.

Don't anticipate any of that this PR. Stay focused on F4 + percentile + arcana fix.
