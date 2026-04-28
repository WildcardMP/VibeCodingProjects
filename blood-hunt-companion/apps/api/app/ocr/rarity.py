"""Color-based rarity classification.

Tooltip badge colors map cleanly to the five rarities. We classify by the dominant
hue of a small region (the rarity badge anchor inside the auto-detected tooltip
card; see `app/ocr/anchors.py`).

Hue ranges below are starting points; tune against real fixture screenshots.
"""

from __future__ import annotations

from typing import Any

from ..schemas.common import Rarity

# (rarity, hue_low, hue_high, sat_min, val_min)  — OpenCV H is 0-179
_HUE_RANGES: list[tuple[Rarity, int, int, int, int]] = [
    ("uncommon", 40, 80, 60, 80),  # green
    ("rare", 95, 130, 80, 80),  # blue
    ("epic", 130, 165, 60, 80),  # purple
    ("legendary", 15, 35, 120, 120),  # gold/orange (high saturation)
]


def classify_rarity_by_color(bgr_patch: Any) -> Rarity:
    """Return the rarity whose hue range best matches the patch's median pixel.

    Falls back to "common" (white/grey) when saturation is too low to be a colored badge.
    """
    import cv2
    import numpy as np

    if bgr_patch is None or bgr_patch.size == 0:
        return "common"

    hsv = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV)
    h, s, v = (np.median(hsv[..., i]) for i in range(3))

    # Low saturation + high value → white/grey → common.
    if s < 40 and v > 180:
        return "common"

    for rarity, h_lo, h_hi, s_min, v_min in _HUE_RANGES:
        if h_lo <= h <= h_hi and s >= s_min and v >= v_min:
            return rarity

    return "common"
