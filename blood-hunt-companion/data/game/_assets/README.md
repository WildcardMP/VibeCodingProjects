# `_assets/` — User-supplied template images for OCR matching

The OCR pipeline can use template matching as a second signal alongside Tesseract.
This is documented in [DATA_PIPELINE.md §2.7](../../../DATA_PIPELINE.md#27-tier-letter-detection).
**Without these images the pipeline still works** — it falls back to Tesseract-only
for tier letters and a base-effect heuristic for slots — but accuracy improves
noticeably once you supply real reference crops.

## Two template sets

### `tier_badges/`

PNG crops of the **S / A / B / C / D** tier badges as rendered on a real gear
tooltip. One file per tier letter, named after the letter:

```
data/game/_assets/tier_badges/
  S.png
  A.png
  B.png
  C.png
  D.png
```

You may include variants (e.g. `S_alt.png`, `S_lowres.png`) — anything before the
first `_` in the filename stem is treated as the label, so all variants are
considered when matching.

### `slot_icons/`

PNG crops of the **weapon / armor / accessory / exclusive** slot icons:

```
data/game/_assets/slot_icons/
  weapon.png
  armor.png
  accessory.png
  exclusive.png
```

Same `_<suffix>` variant convention applies.

## How to capture clean templates

1. Take a screenshot of any gear tooltip in your normal play resolution.
2. Crop tightly around the badge or icon — leave only the symbol, no surrounding text or borders.
3. Save as PNG (lossless; JPEG compression hurts template matching).
4. Drop the file into the matching directory above.
5. Restart the API (`make api`) — templates are cached at process start.

Size and resolution don't have to be exact; the matcher resizes both the template
and the runtime crop to a canonical 32×32 grayscale before correlation.

## Confidence semantics

- **Both Tesseract and template match agree** → tier confidence `1.0`.
- **Only one method returned a letter** → confidence `0.65` (yellow band).
- **They disagree** → trust the template match, confidence `0.65`, log a warning.
- **Neither** → confidence `0.0`, surfaced for manual correction in the frontend.

For slot detection: if a matching template is found at the slot-icon anchor
inside the auto-detected tooltip card, slot confidence equals the template-match
score (0.55–1.0). Otherwise the heuristic fallback returns confidence `0.5`.

## What lives here long-term

These images are **per-installation** — they depend on the textures your local
client renders. They are gitignored by default; if you do commit them, accept
they may need to be re-captured after a Marvel Rivals UI patch.
