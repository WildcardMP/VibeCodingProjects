# Phase 2 OCR Inputs — Capture Guide

A step-by-step checklist for everything you need to capture from Marvel Rivals so Claude Code can finish the OCR pipeline. Designed to be done in one or two sittings, with clear stopping points.

---

## Before you start

**Tools you'll need:**
- Marvel Rivals running at your normal play resolution
- Windows Snipping Tool (Win + Shift + S) for screenshots and crops
- File Explorer open to: `C:\Users\nolan_vahhx7s\Desktop\VibeCodingProjects\blood-hunt-companion\`

**Resolution check:**
Before doing anything, confirm your monitor resolution. In Windows: `Settings → System → Display → Display resolution`. Write it down (e.g., `1920x1080`, `2560x1440`, `3840x2160`). You'll need it for the calibration filename.

**Folder structure to create:**
```
blood-hunt-companion/
├── data/
│   └── game/
│       ├── calibration/                ← create this
│       └── _assets/
│           ├── tier_badges/            ← create this
│           └── slot_icons/             ← create this
└── apps/
    └── api/
        └── tests/
            └── fixtures/
                └── ocr/                ← create this
```

You can create these folders in File Explorer or in PowerShell:
```powershell
mkdir data\game\calibration
mkdir data\game\_assets\tier_badges
mkdir data\game\_assets\slot_icons
mkdir apps\api\tests\fixtures\ocr
```

---

## Step 1 — Calibration JSON

**Goal:** define bounding boxes that tell the OCR pipeline where each field lives on the gear inspect screen.

**Time:** ~10 minutes
**Frequency:** once per resolution

### What to do

1. Launch Marvel Rivals at your normal resolution.
2. Open any gear item's inspect screen (the detailed view showing name, tier, slot, level, and stats).
3. Take a clean screenshot of the entire screen with `Win + Shift + S` → "Full screen" → save it as `calibration_source.png` in the project folder.
4. Open PowerShell in the project folder and run:
   ```powershell
   .venv\Scripts\python.exe tools\ocr_calibration.py calibration_source.png
   ```
5. The tool opens the screenshot in a window. For each field it asks about, **click and drag a tight rectangle around that field**. The tool will prompt for these in order:
   - Item name
   - Tier badge (the S/A/B/C/D icon)
   - Slot icon (weapon/armor/accessory/exclusive icon)
   - Item level
   - Stats area (the full block listing all stats)
6. When done, the tool saves a JSON file. **Move it to `data/game/calibration/<your_resolution>.json`**, e.g., `data/game/calibration/1920x1080.json`.

### Done when

- [ ] One JSON file exists in `data/game/calibration/` named after your resolution
- [ ] The JSON has bounding boxes for: name, tier, slot, level, stats

---

## Step 2 — Tier badge reference PNGs

**Goal:** five tightly-cropped images of each tier badge so the OCR pipeline can do template matching instead of guessing from text.

**Time:** ~15 minutes
**Frequency:** once per resolution

### What to do

For **each** tier (S, A, B, C, D), you need one cropped PNG of just the tier badge.

1. Find a piece of gear of each tier in your inventory. (If you don't have all five, see the workaround below.)
2. Open the gear's inspect screen.
3. Use `Win + Shift + S` → "Rectangular snip" and crop **as tightly as possible** around the tier badge. No background, no extra UI — just the badge itself.
4. Save each one to:
   - `data/game/_assets/tier_badges/S.png`
   - `data/game/_assets/tier_badges/A.png`
   - `data/game/_assets/tier_badges/B.png`
   - `data/game/_assets/tier_badges/C.png`
   - `data/game/_assets/tier_badges/D.png`

### If you don't own a piece of every tier

Two workarounds:
- **In-game shop / preview screens** often display gear at every tier — crop from there.
- **Skip the missing tier for now**; OCR will still work for the tiers you have. Note it as a TODO and add later when you find the missing tier.

### Done when

- [ ] Five PNG files in `data/game/_assets/tier_badges/`
- [ ] Each is tightly cropped, no extra background
- [ ] Filenames are exactly `S.png`, `A.png`, `B.png`, `C.png`, `D.png` (capital letter)

---

## Step 3 — Slot icon reference PNGs

**Goal:** four tightly-cropped images of each slot icon for template matching.

**Time:** ~10 minutes
**Frequency:** once per resolution

### What to do

Same process as tier badges, but for slot icons. The four slots are:
- `weapon`
- `armor`
- `accessory`
- `exclusive`

1. Open a piece of gear in each slot.
2. Crop tightly around the slot icon (the small icon indicating what kind of gear it is).
3. Save to:
   - `data/game/_assets/slot_icons/weapon.png`
   - `data/game/_assets/slot_icons/armor.png`
   - `data/game/_assets/slot_icons/accessory.png`
   - `data/game/_assets/slot_icons/exclusive.png`

### Done when

- [ ] Four PNG files in `data/game/_assets/slot_icons/`
- [ ] Each is tightly cropped
- [ ] Filenames are lowercase: `weapon.png`, `armor.png`, `accessory.png`, `exclusive.png`

---

## Step 4 — Test fixture screenshots (the big one)

**Goal:** 10+ real gear inspect screenshots, each paired with a hand-written `expected.json` describing exactly what's on screen. This is what makes the OCR pipeline self-verifying.

**Time:** ~30–45 minutes
**Frequency:** once (more is better; 10 is the floor)

### Coverage targets

Aim to hit all of these across your 10+ fixtures:
- [ ] At least one of each slot: weapon, armor, accessory, exclusive
- [ ] At least one of each tier: S, A, B, C, D
- [ ] A mix of high-level and low-level items
- [ ] At least one item with a long or unusual name (stress-tests fuzzy matching)
- [ ] At least one item with special characters in stats if any exist

### What to do for each fixture

1. Open a gear item's inspect screen in-game.
2. Screenshot the **entire screen** (full screen, not cropped) with `Win + Shift + S` → "Full screen."
3. Create a folder: `apps/api/tests/fixtures/ocr/fixture_01/` (then `fixture_02`, `fixture_03`, etc.)
4. Save the screenshot inside as `screenshot.png`.
5. Create a file in the same folder named `expected.json` with the ground-truth data — exactly what's visible on screen.

### `expected.json` schema

```json
{
  "name": "Mjolnir Fragment",
  "slot": "weapon",
  "tier": "S",
  "level": 47,
  "stats": [
    {"name": "Attack Power", "value": 142},
    {"name": "Crit Rate", "value": 8.5}
  ]
}
```

**Field rules:**
- `name` — exact item name as shown in-game (case-sensitive)
- `slot` — one of: `"weapon"`, `"armor"`, `"accessory"`, `"exclusive"` (lowercase)
- `tier` — one of: `"S"`, `"A"`, `"B"`, `"C"`, `"D"` (capital letter)
- `level` — integer, no quotes
- `stats` — array of `{name, value}` objects. Names should match the in-game label exactly. Values are numbers — use a decimal for percentages (e.g., `8.5` for 8.5%, not `"8.5%"`).

### Done when

- [ ] At least 10 folders under `apps/api/tests/fixtures/ocr/`, each named `fixture_NN/`
- [ ] Every folder has both `screenshot.png` and `expected.json`
- [ ] Coverage targets above are met
- [ ] All `expected.json` files are valid JSON (PowerShell tip: `Get-Content path\to\expected.json | ConvertFrom-Json` will error if it's malformed)

---

## Step 5 — Commit and push

Once everything's in place, push it all to GitHub so Claude Code can see it:

```powershell
git add data/game/calibration/ data/game/_assets/ apps/api/tests/fixtures/ocr/
git commit -m "Add Phase 2 OCR inputs: calibration, badge/icon templates, 10 fixtures"
git push
```

---

## Step 6 — Hand off to Claude Code

Open Claude Code in the project folder and prompt it with:

> Phase 2 §7.1 OCR fixtures are ready. Calibration JSON is at `data/game/calibration/<resolution>.json`. Tier badges are in `data/game/_assets/tier_badges/`, slot icons in `data/game/_assets/slot_icons/`, and test fixtures in `apps/api/tests/fixtures/ocr/`. Please run the OCR pipeline against each fixture, address any failures, and add `tests/test_ocr_fixtures.py` that asserts pipeline output matches each `expected.json`. Report back with pass/fail counts and any items that needed accuracy tuning.

CLAUDE.md will give it the full project context automatically.

---

## Quick reference — folder + filename cheatsheet

```
data/game/calibration/1920x1080.json          ← your resolution
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

1. After Step 1 (calibration only) — partial state, but a milestone.
2. After Step 3 (calibration + all template assets) — all "configuration" inputs done; only fixtures remain.
3. After Step 4 with however many fixtures you got — even 5 fixtures is useful; aim for 10 eventually.

Commit and push at each stopping point so progress isn't lost.
