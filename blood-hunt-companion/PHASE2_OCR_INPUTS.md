# Phase 2 OCR Inputs — Capture Guide

Step-by-step checklist for capturing what Claude Code needs to finish the Phase 2 OCR pipeline. **No calibration required.** This guide reflects the post-2026-04-27 architecture pivot to calibration-free, content-based OCR.

---

## What changed (and why)

Earlier drafts of this guide asked you to run a calibration tool to record bounding boxes for each field on the gear tooltip. **That step has been eliminated.** The new OCR pipeline:

- **Auto-detects** the tooltip's location anywhere on screen using OpenCV.
- **Identifies stats by their text label** (via fuzzy matching), not by their position. So if Attack Power is on row 1 in one screenshot and row 3 in another, the pipeline doesn't care.
- **Works at any resolution** with zero user configuration.

What you still need to capture is much simpler: a few reference PNGs and a set of test fixtures.

---

## Before you start

**Tools you'll need:**
- Marvel Rivals running at your normal resolution
- Windows Snipping Tool (`Win + Shift + S`) for screenshots and crops
- File Explorer at: `C:\Users\nolan_vahhx7s\Desktop\VibeCodingProjects\blood-hunt-companion\`

**Folders to create** (PowerShell, in the project folder):

```powershell
mkdir data\game\_assets\tier_badges
mkdir data\game\_assets\slot_icons
mkdir apps\api\tests\fixtures\ocr
```

**Estimated total time:** 60–90 minutes, doable in one or two sittings.

---

## Step 1 — Tier badge reference PNGs

**Goal:** five tightly-cropped images, one per tier, used by the OCR pipeline for template matching.

**Time:** ~15 minutes

### What to do

For **each** tier (S, A, B, C, D), capture one cropped PNG of just the tier badge as it appears on a real gear tooltip.

1. Find a piece of gear at each tier in your inventory. (Workaround if you don't own one: see below.)
2. Open its tooltip.
3. `Win + Shift + S` → "Rectangular snip" → crop **as tightly as possible** around the tier badge. No background, no extra UI.
4. Save to:
   - `data/game/_assets/tier_badges/S.png`
   - `data/game/_assets/tier_badges/A.png`
   - `data/game/_assets/tier_badges/B.png`
   - `data/game/_assets/tier_badges/C.png`
   - `data/game/_assets/tier_badges/D.png`

### If you don't own a piece of every tier

- **Shop or preview screens** in-game often show every tier — crop from there.
- **Skip the missing tier** for now. The pipeline will still work for the tiers you have. Note as a TODO.

### Done when

- [ ] 5 PNG files in `data/game/_assets/tier_badges/`
- [ ] Each is tightly cropped, no background or neighboring UI
- [ ] Filenames are exactly `S.png`, `A.png`, `B.png`, `C.png`, `D.png` (capital letter)

---

## Step 2 — Slot icon reference PNGs

**Goal:** four tightly-cropped images of each slot icon for template matching.

**Time:** ~10 minutes

### What to do

Same process as tier badges, but for slot icons. Slots are: `weapon`, `armor`, `accessory`, `exclusive`.

1. Open one piece of gear in each slot.
2. Crop tightly around the slot icon.
3. Save to:
   - `data/game/_assets/slot_icons/weapon.png`
   - `data/game/_assets/slot_icons/armor.png`
   - `data/game/_assets/slot_icons/accessory.png`
   - `data/game/_assets/slot_icons/exclusive.png`

### Done when

- [ ] 4 PNG files in `data/game/_assets/slot_icons/`
- [ ] Each is tightly cropped
- [ ] Filenames are lowercase: `weapon.png`, `armor.png`, `accessory.png`, `exclusive.png`

---

## Step 3 — Test fixture screenshots (the big one)

**Goal:** 10+ real gear tooltip screenshots, each paired with a hand-labeled `expected.json`. The pipeline runs against these in tests to verify accuracy.

**Time:** ~30–45 minutes

### Coverage targets

Aim to hit all of these across your 10+ fixtures:

- [ ] At least one of each slot: weapon, armor, accessory, exclusive
- [ ] At least one of each tier: S, A, B, C, D
- [ ] A mix of tooltip positions on screen (some left, some right, some center)
- [ ] At least one item with a long or unusual name (stress-tests fuzzy matching)
- [ ] At least one tooltip with the busiest possible game world behind it (stress-tests detection)
- [ ] At least one tooltip with stats in clearly different orders (e.g., one weapon shows Attack Power on row 1, another shows it on row 3) — this is the whole point of content-based identification

### What to do for each fixture

1. Hover over a gear item in-game so the tooltip appears.
2. Screenshot the **entire screen** with `Win + Shift + S` → "Full screen." (Don't crop — the auto-detector needs the full screen so it can find the tooltip itself.)
3. Create a folder: `apps/api/tests/fixtures/ocr/fixture_01/` (then `fixture_02`, `fixture_03`, etc.)
4. Save the screenshot inside as `screenshot.png`.
5. Create `expected.json` in the same folder with ground-truth data.

### `expected.json` schema

```json
{
  "name": "Mjolnir Fragment",
  "slot": "weapon",
  "rarity": "legendary",
  "level": 60,
  "base_effect": "Precision Damage",
  "base_value": 8300,
  "extended_effects": [
    {"stat_id": "Total Output Boost", "tier": "S", "value": 4200},
    {"stat_id": "Boss Damage", "tier": "A", "value": 1800},
    {"stat_id": "Crit Rate", "tier": "B", "value": 8.5}
  ]
}
```

**Field rules:**

- `name` — exact item name as shown in-game (case-sensitive)
- `slot` — one of: `"weapon"`, `"armor"`, `"accessory"`, `"exclusive"` (lowercase)
- `rarity` — one of: `"common"`, `"uncommon"`, `"rare"`, `"epic"`, `"legendary"` (lowercase). This is the **item's overall rarity**, indicated by the tooltip border color. Determines how many extended effects the item has (legendaries get up to 4).
- `level` — integer, no quotes (cap is 60)
- `base_effect` — name of the item's base/main effect (the headline stat at the top of the tooltip)
- `base_value` — numeric value of the base effect
- `extended_effects` — array of `{stat_id, tier, value}`, in the order they appear on screen (top to bottom). The number of entries depends on rarity (legendaries up to 4, lower rarities fewer).
  - `stat_id` — the stat label exactly as shown in-game
  - `tier` — **per-row tier**, one of `"S"`, `"A"`, `"B"`, `"C"`, `"D"`. This is the magnitude band of *that specific rolled stat*, NOT the item's overall rarity.
  - `value` — numeric value of the rolled stat. Use a decimal for percentages (e.g., `8.5` for 8.5%).

**Two important distinctions:**

1. **Rarity ≠ Tier.** `rarity` is the item's color/border (legendary, epic, etc.). `tier` is the S/A/B/C/D grade of an individual extended-effect roll. A legendary item can have a D-tier roll on it.
2. **Order matters.** List `extended_effects` in the order they appear on screen, top to bottom. The pipeline doesn't care about position when *identifying* stats (it uses content), but order is needed so tests can verify the pipeline reported them in the correct visual order.

### Validating your JSON

Before moving on, sanity-check each `expected.json` is valid JSON. PowerShell tip:

```powershell
Get-Content apps\api\tests\fixtures\ocr\fixture_01\expected.json | ConvertFrom-Json
```

If it errors, the JSON is malformed.

### Done when

- [ ] At least 10 folders under `apps/api/tests/fixtures/ocr/`, each named `fixture_NN/`
- [ ] Every folder has both `screenshot.png` and `expected.json`
- [ ] Coverage targets above are met
- [ ] All `expected.json` files are valid JSON

---

## Step 4 — Commit and push

```powershell
git add data/game/_assets/ apps/api/tests/fixtures/ocr/
git commit -m "Add Phase 2 OCR inputs: tier badges, slot icons, 10+ fixtures"
git push
```

---

## Step 5 — Hand off to Claude Code

Open Claude Code in the project folder. The repo already contains a detailed prompt at `CLAUDE_PROMPT_PHASE2_OCR.md` — paste its contents into Claude Code as your first message in the new session.

That prompt instructs Claude Code to:

1. Implement the calibration-free, content-based OCR pipeline.
2. Run it against your fixtures.
3. Tune until ≥9 of 10 parse correctly with no manual edits.
4. Add `tests/test_ocr_fixtures.py` to lock in the accuracy bar.
5. Report back with pass/fail counts.

CLAUDE.md will give it the broader project context automatically.

---

## Quick reference — cheatsheet

```
data/game/_assets/tier_badges/S.png
data/game/_assets/tier_badges/A.png
data/game/_assets/tier_badges/B.png
data/game/_assets/tier_badges/C.png
data/game/_assets/tier_badges/D.png
data/game/_assets/slot_icons/weapon.png
data/game/_assets/slot_icons/armor.png
data/game/_assets/slot_icons/accessory.png
data/game/_assets/slot_icons/exclusive.png
apps/api/tests/fixtures/ocr/fixture_01/screenshot.png
apps/api/tests/fixtures/ocr/fixture_01/expected.json
... fixture_02 through fixture_10+ ...
```

---

## Stopping points

If you can't finish in one sitting, good places to stop:

1. After Step 1 (tier badges only) — partial state.
2. After Step 2 (tier badges + slot icons) — all template assets done.
3. After Step 3 with however many fixtures you got — even 5 is useful; aim for 10 eventually.

Commit and push at each stopping point so progress isn't lost.

---

## Things you can ignore from earlier guidance

- ❌ Running `tools/ocr_calibration.py` — no longer needed.
- ❌ Creating `data/game/calibration/` or `data/calibration/` folders — no longer needed.
- ❌ Recording bounding boxes by drawing rectangles — no longer needed.
- ❌ Caring about your monitor resolution or UI scale — pipeline handles any.

If `calibration_source.png` is sitting in your project folder from earlier, you can delete it.
