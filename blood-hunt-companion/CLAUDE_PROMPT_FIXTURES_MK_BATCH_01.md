# Claude Code Prompt — OCR Fixtures Batch 01: Moon Knight Legendaries

> Mechanical filesystem task — not an architecture task. A 1-line plan is
> sufficient, no need for the full §3.1 plan template; this is fixture data
> prep, not a new module.

---

## Context

We're starting Phase B fixture capture per `PHASE2_OCR_INPUTS.md`. The user (Cowork) has hand-transcribed three Moon Knight legendary gear tooltips and verified the schema. Your job is to land them in the repo as proper fixture folders so the test suite can find them once the user drops in the matching screenshot PNGs.

This batch is **Moon Knight only by user choice** — the multi-hero coverage target from `PHASE2_OCR_INPUTS.md` is deferred to a later batch. Don't worry about Squirrel Girl or other heroes in this PR.

The OCR fixture-accuracy gate (`test_ocr_fixtures.py` ≥9/10 pass rate) **stays open** — these three fixtures alone won't satisfy it; we still need 4–6 more MK pieces (different rarities) before tuning. This PR is data prep only.

---

## Scope (this PR)

**Folders already exist.** The user created `apps/api/tests/fixtures/ocr/fixture_01/` through `fixture_15/` via PowerShell before triggering this prompt. Do not create or delete folders. If any are missing when you go to write a file inside them, **report and stop** — do not auto-create.

1. **Write `expected.json`** in `apps/api/tests/fixtures/ocr/fixture_01/`, `fixture_02/`, and `fixture_03/` with the contents below, byte-for-byte. Folders `fixture_04/` through `fixture_15/` stay empty — the user fills them in over time as they capture more screenshots.
2. **Validate** the three JSON files parse against whatever Pydantic schema/loader the existing `test_ocr_fixtures.py` uses (e.g., load each via `app.schemas.gear.Gear` or whatever the canonical loader is). If validation surfaces any issues, surface them in your report — **do not silently fix the JSONs without flagging the user**, since they came from the user's own tooltip transcription and may indicate a real schema gap.
3. **Run `make test` and `make lint`** to confirm nothing broke. The OCR fixture skip-when-empty gate must continue to skip cleanly (3 fixtures with `expected.json` but no `screenshot.png` should still register as skipped, not failed — the existing test gates on both files being present per `PHASE2_OCR_INPUTS.md`).

## Anti-scope (do NOT do this PR)

- Do **not** modify anything under `app/ocr/*`. Calibration-free pipeline stays untouched until user fixtures land with screenshots.
- Do **not** modify `app/services/*`, `app/routers/*`, `app/schemas/*`, or any router. This is fixture data only.
- Do **not** generate placeholder `screenshot.png` files. The user will drop real captures in.
- Do **not** create empty `expected.json` templates in fixture_04–15. Empty folders are correct.
- Do **not** touch the F1 Damage Simulator work (separate prompt, separate PR).
- Do **not** make schema changes — if a JSON below doesn't validate, **report it, don't auto-fix**.

---

## Files to create

### `apps/api/tests/fixtures/ocr/fixture_01/expected.json`

```json
{
  "name": "Runic Armor",
  "slot": "armor",
  "rarity": "legendary",
  "hero": "Moon Knight",
  "level": 60,
  "rating": 6636,
  "base_effects": [
    { "name": "Health", "value": 2419 },
    { "name": "Armor Value", "value": 438 }
  ],
  "extended_effects": [
    { "stat_id": "Armor Value", "tier": "A", "value": 437 },
    { "stat_id": "Health restored per/s during Restorative Respire", "tier": "S", "value": 360 },
    { "stat_id": "Block Damage Reduction", "tier": "D", "value": 108 },
    { "stat_id": "Health", "tier": "S", "value": 107 },
    { "stat_id": "Dodge Rate", "tier": "A", "value": 6.9 }
  ]
}
```

### `apps/api/tests/fixtures/ocr/fixture_02/expected.json`

```json
{
  "name": "Scepter of Rites",
  "slot": "weapon",
  "rarity": "legendary",
  "hero": "Moon Knight",
  "level": 60,
  "rating": 6252,
  "base_effects": [
    { "name": "Crescent Dart base damage", "value": 120 },
    { "name": "Moonblade base damage", "value": 177 }
  ],
  "extended_effects": [
    { "stat_id": "Damage Bonus against Healthy Enemies", "tier": "D", "value": 458 },
    { "stat_id": "Waxing Moon Enhancement: Crescent Darts bounce between Ankhs", "tier": "D", "value": 12 },
    { "stat_id": "Precision Damage", "tier": "S", "value": 1942 },
    { "stat_id": "Precision Rate", "tier": "S", "value": 6.2 },
    { "stat_id": "Lunar Glide Enhancement: Firing interval of Crescent Darts during Night Glider", "tier": "A", "value": -0.34 }
  ]
}
```

### `apps/api/tests/fixtures/ocr/fixture_03/expected.json`

```json
{
  "name": "Alchemy Amulet",
  "slot": "accessory",
  "rarity": "legendary",
  "hero": "Moon Knight",
  "level": 60,
  "rating": 6421,
  "base_effects": [
    { "name": "Critical Hit Rate", "value": 16.2 },
    { "name": "Block Rate", "value": 18.5 }
  ],
  "extended_effects": [
    { "stat_id": "Bonus Damage against Close-Range Enemies", "tier": "S", "value": 830 },
    { "stat_id": "Block Damage Reduction", "tier": "C", "value": 119 },
    { "stat_id": "Precision Damage", "tier": "S", "value": 1942 },
    { "stat_id": "Total Damage Bonus", "tier": "A", "value": 469 },
    { "stat_id": "Fist of Eclipse Enhancement: Fist of Eclipse applies Eclipse Mark stacks", "tier": "C", "value": 15 }
  ]
}
```

### Empty folders

`fixture_04/` through `fixture_15/` already exist (user created them) and stay empty. The user populates them as they capture more screenshots over time. Do not write anything inside these folders.

---

## Edge cases worth flagging in your report (don't auto-fix — surface them)

These came up during transcription and may indicate schema-level questions:

1. **Pendant of Oshtur (Moon Knight Legendary Exclusive)** — its base effect is a single descriptive paragraph rather than discrete `{name, value}` lines: *"Ankh charges and maximum on the field +6, Ankh health +72000, and gain 50% damage reduction; holding the ability key on an Ankh recalls it and restores a charge."* Cowork deferred capturing this fixture pending a schema decision (split into multiple base_effects? Single entry with full text?). **No action needed this PR**, but note in your report that the exclusive-slot row is intentionally missing from this batch.

2. **Negative values in extended effects** — `Lunar Glide Enhancement` has value `-0.34` (cooldown reduction expressed as negative seconds). Confirm the Pydantic schema accepts negative floats here. If not, flag.

3. **Narrative extended-effect names** — e.g., `"Waxing Moon Enhancement: Crescent Darts bounce between Ankhs"` and `"Fist of Eclipse Enhancement: Fist of Eclipse applies Eclipse Mark stacks"`. These are long, contain colons, and pair with `(Not Activated)` status text in-game (which the schema doesn't currently capture — Cowork is aware). Confirm the schema's `stat_id` field has no length limit or character restrictions that block these.

4. **Percent vs. flat values** — per `PHASE2_OCR_INPUTS.md`, percent values use the integer/decimal form (e.g., `107` for `+107%`, `6.9` for `+6.9%`) without a unit field. The three JSONs above follow this convention; confirm the schema doesn't require a separate `unit` discriminator.

If any of (2), (3), or (4) actually fail Pydantic validation, **report and stop** — don't proceed with the commit. Cowork will resolve.

---

## Commit message

Single commit on `main`, imperative present tense, with body:

```
Add OCR fixtures batch 01: Moon Knight legendaries (slots weapon/armor/accessory)

Three hand-transcribed expected.json files for Moon Knight legendary gear:
- fixture_01: Runic Armor (legendary armor, rating 6636)
- fixture_02: Scepter of Rites (legendary weapon, rating 6252)
- fixture_03: Alchemy Amulet (legendary accessory, rating 6421)

Folders fixture_04 through fixture_15 created empty; user fills as captures
land. Multi-hero and multi-rarity coverage targets deferred to future batch
(Moon Knight only by user choice).

Pendant of Oshtur (legendary exclusive) intentionally omitted - its base
effect is descriptive prose rather than discrete {name, value} entries,
pending schema decision.

OCR fixture-accuracy gate (>=9/10 pass rate) remains open. Screenshots
will be added by the user in a follow-up commit.

Refs: PHASE2_OCR_INPUTS.md sec 3.
```

---

## Report back format

(a) Confirmation that the three `expected.json` files were written byte-for-byte to `fixture_01/`, `fixture_02/`, `fixture_03/`. Also confirm `fixture_04/` through `fixture_15/` still exist and remain empty (no files written inside).

(b) Pydantic validation result on the three JSONs — pass / fail per file. If any failed, the exact validation error and what schema field it complained about. **Do not commit until all three pass or until Cowork resolves the failure.**

(c) `make test` result — should still show 164+ passing, 2 skipped (the OCR fixture gate). Specifically confirm `test_ocr_fixtures.py` continues to skip cleanly, not fail.

(d) `make lint` result — should be clean.

(e) The exact commit SHA, push status (pushed to origin/main, or held locally pending user push).

(f) Anything you noticed that wasn't in this brief — particularly any of the four edge cases above if they triggered, or any Pydantic schema gap that would block future fixtures from validating.

---

## What happens after this PR

The user (Nolan, IGN WildcardMP) will:

1. Drop `screenshot.png` files into `fixture_01/`, `fixture_02/`, `fixture_03/` from his existing Moon Knight tooltip captures.
2. Capture 4–6 more Moon Knight fixtures at lower rarities (epic, rare, advanced, normal) plus an exclusive-slot piece — to satisfy the rarity-coverage target before OCR tuning runs.
3. Push when ready.
4. Cowork will write a Phase B tuning prompt that runs `BLOOD_HUNT_OCR_DEBUG=1 py -m pytest apps/api/tests/test_ocr_fixtures.py -s` and iterates `app/ocr/detect.py` + `app/ocr/anchors.py` against real fixtures.

Don't anticipate any of that work this PR. Stay focused on the data prep.
