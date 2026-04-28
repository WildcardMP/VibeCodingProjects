# Claude Code Prompt — Phase 2 OCR (Calibration-Free, Content-Based)

**How to use this file:** copy the entire contents below the `---` line and paste it as your first message in a fresh Claude Code session inside the `blood-hunt-companion/` folder. CLAUDE.md will load automatically and give Claude the broader project context.

---

## Phase 2 OCR — Implementation Brief

### Architectural pivot (read first)

The OCR pipeline previously planned to use **per-resolution calibration JSON** with hard-coded bounding boxes. This has been **eliminated**. The new architecture is calibration-free and content-based. Both PROJECT.md §9 Phase 2 and PHASE2_OCR_INPUTS.md have been updated; if anything in the codebase or docs still references the old calibration approach, treat that as legacy to remove or rewrite.

### Why the pivot

1. **Tooltip position is dynamic.** In Marvel Rivals, the gear tooltip pops up wherever the user is hovering. Fixed-position bounding boxes don't work.
2. **Stat order within a tooltip is randomized per gear roll.** Reading "row 1 = Attack Power" by position is incorrect; the same stat can appear on different rows in different tooltips.
3. **The app must work for any user with zero setup.** Calibration is a non-starter for shareability.

### Pipeline design — six stages

You are implementing this pipeline. Each stage is its own module under `apps/api/app/ocr/`. Existing modules (fuzzy.py, templates.py, parse.py, preprocess.py) stay; you're adding new ones and rewriting `pipeline.py` to chain them.

#### Stage 1 — Tooltip card detection (`app/ocr/detect.py`, NEW)

Find the tooltip's bounding box on the full-screen screenshot.

- Input: full-screen screenshot (numpy array from cv2.imread).
- Output: `(x, y, w, h)` of the detected tooltip card, plus a confidence score.
- Approach: edge detection + contour filtering. Tooltip has consistent border style (likely a glowing/colored edge against game world) and semi-opaque dark background.
- Suggested techniques to try in order:
  1. Convert to grayscale, apply Canny edge detection, find contours, filter by aspect ratio (tooltips are roughly portrait or square-ish, not extremely wide/tall) and minimum area (probably >5% of screen area).
  2. If edge detection is unreliable due to busy game world, fall back to color-space filtering — convert to HSV and threshold on the dark semi-opaque background.
  3. As a last resort, use template matching against a tooltip border crop, but this is brittle.
- Implement with debug logging: optionally write annotated debug images to `data/debug/detect/` showing detected contours and the chosen card. Gate with a `BLOOD_HUNT_OCR_DEBUG=1` env var.
- Return value should be a dataclass: `DetectedCard(bbox: tuple[int,int,int,int], confidence: float)`.

#### Stage 2 — Anchor detection inside the card (`app/ocr/anchors.py`, NEW)

Once the card is found, locate structural elements with known *relative* positions inside it.

- Input: the cropped card image.
- Output: dataclass `CardAnchors` with regions for: `name_region`, `rarity_badge_region`, `level_region`, `slot_icon_region`, `base_effect_region`, `extended_effects_region`. All as `(x, y, w, h)` *relative to the card crop*.
- Approach: anchors are defined as **proportions of card dimensions**, not pixels. Examples:
  - `name_region` = top 12% of card height, full width minus 10% padding
  - `rarity_badge_region` = top-right corner, ~15% of card width and height
  - `extended_effects_region` = bottom 50% of card, full width minus padding
- These proportions are tunable constants in `anchors.py`. Document each constant with a comment explaining what visual element it targets.
- Tune the proportions empirically against the user-provided fixture screenshots.

#### Stage 3 — Row segmentation (`app/ocr/anchors.py`, same module)

Given the `extended_effects_region`, segment it into individual rows.

- Approach: detect horizontal whitespace gaps. Convert region to grayscale, take horizontal projection (sum of pixel intensities per row), find local minima representing gaps between text lines.
- Output: list of `(y_start, y_end)` row boundaries within the extended-effects region. **Number of rows is detected, not assumed** — supports tooltips with 1, 2, 3, or 4 extended effects.
- Add a sanity check: rows should have minimum height (>~3% of card height) to filter out noise.

#### Stage 4 — Row content extraction (`app/ocr/pipeline.py`, REWRITE)

For each detected row, extract the stat label, stat value, and tier indicator.

- For each row:
  1. Crop the row image.
  2. OCR the text portion (left ~70% of row width) to get the stat label + value.
  3. Use `app/ocr/fuzzy.py` to fuzzy-match the OCR'd label against the canonical stat list. Return the best match + confidence.
  4. Parse the value (integer, decimal, or percentage) using existing parse logic in `app/ocr/parse.py`.
  5. Extract the tier indicator from the right ~30% of the row using template matching against `data/game/_assets/tier_badges/*.png` (existing logic in `app/ocr/templates.py`).
- Output per row: `ExtractedRow(stat_name: str, stat_value: float, tier: str, confidence: dict)`.

#### Stage 5 — Top-of-card extraction (also in `pipeline.py`)

Extract item name, overall rarity badge, level, and slot icon from the anchored regions.

- `name_region` → OCR → fuzzy-match against canonical item name list (if available) or accept raw OCR.
- `rarity_badge_region` → template match against tier badges → overall tier.
- `level_region` → OCR → parse integer.
- `slot_icon_region` → template match against `data/game/_assets/slot_icons/*.png` → slot string.

#### Stage 6 — Confidence scoring + assembly (`pipeline.py`)

Assemble the full result with per-field confidence scores.

- Build the final result conforming to `apps/api/app/schemas/gear.py` Gear schema, plus a parallel `confidence` dict with the same field structure.
- Confidence sources:
  - Detection confidence (Stage 1)
  - Fuzzy-match scores (Stages 4, 5)
  - Template-match scores (Stages 4, 5)
- Define a global confidence threshold (start at 0.7); fields below threshold get flagged for user review in the API response.

### Required code changes

**New modules:**
- `apps/api/app/ocr/detect.py`
- `apps/api/app/ocr/anchors.py`

**Rewritten:**
- `apps/api/app/ocr/pipeline.py` — chain the six stages above.

**Removed (legacy):**
- `tools/ocr_calibration.py` — delete or move to `tools/_archive/` with a comment.
- `apps/api/app/ocr/calibration.py` — delete or stub out if anything still imports it (then remove imports).
- Any per-resolution calibration JSON loading logic anywhere in the codebase.

**Updated tests:**
- Existing `tests/test_pipeline.py` — update to use the new pipeline signature.
- New `tests/test_detect.py` — unit tests for tooltip detection on synthetic images and at least 3 real fixture screenshots.
- New `tests/test_anchors.py` — unit tests for anchor proportions and row segmentation.
- New `tests/test_ocr_fixtures.py` — **the accuracy gate.** Loads every fixture in `apps/api/tests/fixtures/ocr/fixture_*/`, runs the pipeline against `screenshot.png`, asserts the result matches `expected.json` (with reasonable tolerance for OCR'd numeric values, ±2% or ±1 absolute).

### Acceptance criteria

1. `make test` passes (currently 98 tests; new total should be 110+).
2. `tests/test_ocr_fixtures.py` runs against ≥10 user-provided fixtures and **at least 9 of 10 fixtures pass with no manual correction**. Document which fixture(s) failed and why in a brief report.
3. The pipeline runs end-to-end on a fresh fixture **with zero configuration files** — no calibration JSON, no per-resolution tweaks.
4. The `/api/gear/ingest` endpoint accepts a screenshot and returns the parsed gear with per-field confidence scores.
5. Code is type-hinted, passes `make lint` (ruff + mypy strict), and includes docstrings on all new public functions.

### Tuning workflow

You'll iterate on Stages 1–3 the most. Recommended approach:

1. Implement skeletons for all six stages with hardcoded reasonable defaults.
2. Run pipeline against fixture_01. Debug log every stage's intermediate output.
3. Eyeball where it goes wrong. Adjust the stage that's failing.
4. Run against all fixtures. See which pass.
5. Tune until ≥9 of 10 pass.
6. Lock in with `test_ocr_fixtures.py`.

### Things to avoid

- **Don't reintroduce calibration.** No "just one config file" — the whole point is zero config.
- **Don't hardcode pixel values for resolution-dependent measurements.** Always use proportions of detected card dimensions.
- **Don't fail silently.** If detection fails, raise a clear exception with the screenshot path and reason; the API should return a 422 with a useful error to the user.
- **Don't skip the debug logging.** When you're tuning Stages 1–3, you'll need annotated images. Build that infrastructure early.

### Inputs already in the repo

- `data/game/_assets/tier_badges/{S,A,B,C,D}.png` — tier badge templates.
- `data/game/_assets/slot_icons/{weapon,armor,accessory,exclusive}.png` — slot icon templates.
- `apps/api/tests/fixtures/ocr/fixture_NN/{screenshot.png, expected.json}` — 10+ fixtures.
- `apps/api/app/ocr/fuzzy.py` — fuzzy matching against canonical stat list (already implemented).
- `apps/api/app/ocr/parse.py` — value parsing (already implemented).
- `apps/api/app/ocr/templates.py` — template matching (already implemented; reuse for badges and slot icons).

### Final deliverable

When you're done:

1. All tests passing including `test_ocr_fixtures.py` at ≥9/10.
2. A short markdown report at `apps/api/tests/fixtures/ocr/README.md` listing every fixture, whether it passed, and notes on any tuning you did.
3. A commit message that summarizes the pivot and references PROJECT.md §9 Phase 2.
4. A status comment on completion: pass/fail counts, where the pipeline lives, what to test next.
