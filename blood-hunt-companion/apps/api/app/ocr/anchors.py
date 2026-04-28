"""Stages 2 & 3 — Proportional anchors + row segmentation inside the card.

Stage 2 (anchors): given a cropped tooltip card, return regions for the item
name, rarity badge, level text, slot icon, base-effect row, and the
extended-effects block. Regions are computed as **proportions of card
dimensions** — no absolute pixels, no resolution coupling.

Stage 3 (row segmentation): given the extended-effects region, split it into
0–4 individual rows by detecting horizontal whitespace gaps. The number of rows
is detected, not assumed.

The proportions in `_PROPORTIONS` are the main tuning surface. They're sized to
typical Marvel Rivals tooltip layouts and will be revisited once real fixtures
land — adjust by inspecting the debug PNGs (`BLOOD_HUNT_OCR_DEBUG=1`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from . import debug

log = logging.getLogger(__name__)

# All proportions are (x_start, y_start, w, h) as fractions of card dims.
# Each is a best-guess starting point; tune against real fixtures.
_PROPORTIONS: dict[str, tuple[float, float, float, float]] = {
    # Top band — name spans the top, slot icon sits in the top-left,
    # rarity badge in the top-right.
    "slot_icon":      (0.04, 0.04, 0.16, 0.14),
    "name":           (0.20, 0.04, 0.60, 0.10),
    "rarity_badge":   (0.82, 0.04, 0.14, 0.10),
    # Level usually sits just under the name.
    "level":          (0.20, 0.14, 0.30, 0.06),
    # Base-effect is the prominent row separating the name area from the list
    # of extended effects. Roughly the band ~25–35% down the card.
    "base_effect":    (0.05, 0.24, 0.90, 0.10),
    # Extended-effects block fills the bottom half, padded.
    "extended_effects": (0.05, 0.36, 0.90, 0.55),
}

# Row segmentation thresholds.
# Minimum row height as a fraction of the **extended-effects region** height.
# Anything thinner is whitespace noise.
_MIN_ROW_HEIGHT_FRAC = 0.06
# A pixel-row is "ink" (text) if its mean grayscale below this is dense enough
# to count. We use the OCR-friendly inverted-binary preprocessor, so ink = high.
_INK_FRAC_THRESHOLD = 0.04  # 4% of pixels in the row are above the gray cutoff
_GRAY_INK_CUTOFF = 80


@dataclass(frozen=True)
class Region:
    """A bounding box (x, y, w, h) in card-local pixel coordinates."""

    x: int
    y: int
    w: int
    h: int

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


@dataclass(frozen=True)
class CardAnchors:
    """All structural regions inside a card crop, in card-local pixels."""

    card_size: tuple[int, int]  # (W, H) of the card crop
    name: Region
    slot_icon: Region
    rarity_badge: Region
    level: Region
    base_effect: Region
    extended_effects: Region


def _scale(prop: tuple[float, float, float, float], card_w: int, card_h: int) -> Region:
    px, py, pw, ph = prop
    return Region(
        x=max(0, int(round(px * card_w))),
        y=max(0, int(round(py * card_h))),
        w=max(1, int(round(pw * card_w))),
        h=max(1, int(round(ph * card_h))),
    )


def compute_anchors(card_bgr: Any) -> CardAnchors:
    """Compute all anchor regions for a card crop.

    Args:
        card_bgr: HxWx3 BGR card image (output of `detect.crop_card`).

    Returns:
        A `CardAnchors` with every region populated. All regions are clipped to
        the card bounds; even pathologically small cards get something
        non-degenerate.
    """
    import numpy as np

    arr = np.asarray(card_bgr)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"compute_anchors: expected BGR card, got shape={arr.shape}")
    h, w = arr.shape[:2]

    anchors = CardAnchors(
        card_size=(w, h),
        name=_scale(_PROPORTIONS["name"], w, h),
        slot_icon=_scale(_PROPORTIONS["slot_icon"], w, h),
        rarity_badge=_scale(_PROPORTIONS["rarity_badge"], w, h),
        level=_scale(_PROPORTIONS["level"], w, h),
        base_effect=_scale(_PROPORTIONS["base_effect"], w, h),
        extended_effects=_scale(_PROPORTIONS["extended_effects"], w, h),
    )

    if debug.is_enabled():
        debug.dump_with_boxes(
            "anchors",
            "regions",
            arr,
            [
                ("name", anchors.name.bbox),
                ("slot", anchors.slot_icon.bbox),
                ("rarity", anchors.rarity_badge.bbox),
                ("level", anchors.level.bbox),
                ("base", anchors.base_effect.bbox),
                ("ext", anchors.extended_effects.bbox),
            ],
        )

    return anchors


def crop(card_bgr: Any, region: Region) -> Any:
    """Crop a `Region` out of the card. Bounds-checked."""
    import numpy as np

    arr = np.asarray(card_bgr)
    img_h, img_w = arr.shape[:2]
    x0 = max(0, region.x)
    y0 = max(0, region.y)
    x1 = min(img_w, region.x + region.w)
    y1 = min(img_h, region.y + region.h)
    if x1 <= x0 or y1 <= y0:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    return arr[y0:y1, x0:x1].copy()


def segment_rows(extended_bgr: Any) -> list[tuple[int, int]]:
    """Split the extended-effects region into individual row y-bands.

    Args:
        extended_bgr: cropped BGR image of the extended-effects region.

    Returns:
        A list of `(y_start, y_end)` tuples in region-local coordinates, in
        top-to-bottom order. Empty list when no rows detected (e.g. common-tier
        gear with zero extended effects).

    The detection works on the binarised image: dark gaps between rows show up
    as runs of pixel-rows where almost no ink is present.
    """
    import cv2
    import numpy as np

    arr = np.asarray(extended_bgr)
    if arr.size == 0:
        return []
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr

    region_h, region_w = gray.shape[:2]
    # In a screenshot the tooltip background is dark; text is light. Mark "ink"
    # where pixel intensity exceeds the cutoff.
    ink_mask = (gray >= _GRAY_INK_CUTOFF).astype(np.uint8)
    # Per-row ink density.
    row_density = ink_mask.sum(axis=1) / max(1, region_w)

    is_text = row_density >= _INK_FRAC_THRESHOLD
    rows: list[tuple[int, int]] = []
    in_row = False
    start = 0
    for y in range(region_h):
        if is_text[y] and not in_row:
            start = y
            in_row = True
        elif not is_text[y] and in_row:
            rows.append((start, y))
            in_row = False
    if in_row:
        rows.append((start, region_h))

    # Filter rows shorter than the minimum height threshold.
    min_h = max(1, int(round(_MIN_ROW_HEIGHT_FRAC * region_h)))
    rows = [(y0, y1) for (y0, y1) in rows if (y1 - y0) >= min_h]

    # Cap at 4 — Marvel Rivals legendary gear has at most 4 extended effects.
    rows = rows[:4]

    if debug.is_enabled():
        debug.dump_with_boxes(
            "anchors",
            "rows",
            arr,
            [(f"r{i}", (0, y0, region_w, y1 - y0)) for i, (y0, y1) in enumerate(rows)],
            color=(255, 0, 255),
        )

    log.debug("segment_rows: %d rows in %dx%d region", len(rows), region_w, region_h)
    return rows
