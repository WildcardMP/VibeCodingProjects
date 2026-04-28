"""Stage 1 — Tooltip card detection.

Find the gear tooltip's bounding box anywhere on a full-screen screenshot. The
tooltip has consistent visual properties: a roughly portrait/square card with a
semi-opaque dark background and a colored / light border.

Two strategies, tried in order:

1. **Edge + contour.** Canny edges → external contours → filter by area
   (≥`MIN_AREA_FRACTION` of screen) and aspect ratio (portrait-ish).
2. **HSV dark-background fallback.** When the game world has busy edges that
   swamp the tooltip border, threshold on low-V HSV pixels. The tooltip's
   semi-opaque dark background creates a large connected dark region that's
   relatively easy to find.

Both strategies emit annotated debug PNGs when `BLOOD_HUNT_OCR_DEBUG=1`.

Constants are tunable. Once real fixtures land, expect to revisit
`MIN_AREA_FRACTION`, `ASPECT_RANGE`, and the HSV-V threshold by inspecting the
debug dumps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from . import debug

log = logging.getLogger(__name__)

# A tooltip is at least this fraction of the full screenshot's area. At 3840×2160
# a 5% threshold is ~415K px which a real card comfortably exceeds.
MIN_AREA_FRACTION = 0.03
MAX_AREA_FRACTION = 0.55  # if a candidate covers > half the screen it's not a card

# Aspect ratio = height / width. Tooltips are usually portrait (>1.0) or close
# to square (~0.8–2.5). Allowing a wide range keeps single-stat / variant cards
# discoverable; the area filter does most of the rejection.
ASPECT_MIN = 0.6
ASPECT_MAX = 3.0

# Canny thresholds for the edge strategy. Tuneable.
CANNY_LOW = 60
CANNY_HIGH = 180

# HSV V (brightness) ceiling for the dark-background fallback. A tooltip's
# semi-opaque overlay sits well below the typical game-world brightness.
HSV_V_MAX = 70


class TooltipNotFound(RuntimeError):  # noqa: N818 — user-facing name, not "*Error"
    """Raised when neither detection strategy finds a plausible tooltip card."""


@dataclass(frozen=True)
class DetectedCard:
    """Bounding box of the detected tooltip card on the full screenshot.

    `bbox` is `(x, y, w, h)` in screen pixels. `confidence` is a 0..1 score
    derived from how well the candidate matched expected geometry — perfect
    aspect + large clean contour ≈ 1.0; HSV-fallback hit ≈ 0.6.
    """

    bbox: tuple[int, int, int, int]
    confidence: float
    method: str  # "canny" | "hsv" | "synthetic"


def _aspect_ok(w: int, h: int) -> bool:
    if w <= 0:
        return False
    aspect = h / w
    return ASPECT_MIN <= aspect <= ASPECT_MAX


def _area_ok(w: int, h: int, screen_area: int) -> bool:
    a = w * h
    return MIN_AREA_FRACTION * screen_area <= a <= MAX_AREA_FRACTION * screen_area


def _try_canny(bgr: Any) -> DetectedCard | None:
    """Edge + external-contour strategy. Returns None if no plausible card."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Slight blur to suppress game-world micro-edges.
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)
    # Dilate so border gaps close into a continuous outline.
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_h, img_w = bgr.shape[:2]
    screen_area = img_h * img_w

    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if not _area_ok(w, h, screen_area):
            continue
        if not _aspect_ok(w, h):
            continue
        # Score: contour solidity (filled area / bbox area). Closer to 1 = more
        # rectangle-like = more likely a tooltip.
        bbox_area = float(w * h)
        cnt_area = float(cv2.contourArea(cnt))
        solidity = cnt_area / bbox_area if bbox_area > 0 else 0.0
        candidates.append((solidity, (x, y, w, h)))

    if debug.is_enabled():
        debug.dump_image("detect", "canny_edges", edges)

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    solidity, bbox = candidates[0]
    # Map solidity 0.3..1.0 → confidence 0.55..1.0. Below 0.3 is suspect.
    confidence = max(0.55, min(1.0, 0.55 + (solidity - 0.3) * 0.65))
    debug.dump_with_box("detect", "canny_choice", bgr, bbox)
    return DetectedCard(bbox=bbox, confidence=confidence, method="canny")


def _try_hsv(bgr: Any) -> DetectedCard | None:
    """Dark-background fallback. Returns None if nothing of the right shape."""
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # V (brightness) ≤ HSV_V_MAX → mask of dark regions.
    v = hsv[..., 2]
    mask = (v <= HSV_V_MAX).astype(np.uint8) * 255
    # Close small holes inside the tooltip body so it forms one connected region.
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_h, img_w = bgr.shape[:2]
    screen_area = img_h * img_w

    best: tuple[int, tuple[int, int, int, int]] | None = None
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if not _area_ok(w, h, screen_area):
            continue
        if not _aspect_ok(w, h):
            continue
        area = w * h
        if best is None or area > best[0]:
            best = (area, (x, y, w, h))

    if debug.is_enabled():
        debug.dump_image("detect", "hsv_mask", mask)

    if best is None:
        return None
    debug.dump_with_box("detect", "hsv_choice", bgr, best[1], color=(0, 200, 255))
    # HSV fallback is genuinely less specific than the edge strategy; cap conf.
    return DetectedCard(bbox=best[1], confidence=0.6, method="hsv")


def detect_tooltip(bgr: Any) -> DetectedCard:
    """Detect the gear tooltip card on a full-screen screenshot.

    Args:
        bgr: HxWx3 BGR uint8 image (output of `cv2.imread`).

    Returns:
        `DetectedCard(bbox, confidence, method)` for the best candidate.

    Raises:
        TooltipNotFound: if neither strategy yields a plausible card. The
            message includes the screenshot's resolution so the caller can
            include it in a 422 response.
    """
    import numpy as np

    arr = np.asarray(bgr) if bgr is not None else None
    if arr is None or arr.size == 0:
        raise TooltipNotFound("input image is empty")
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise TooltipNotFound(f"expected HxWx3 BGR image, got shape={arr.shape}")

    h, w = arr.shape[:2]
    log.debug("detect_tooltip: image %dx%d", w, h)

    if debug.is_enabled():
        debug.dump_image("detect", "input", arr)

    canny = _try_canny(arr)
    if canny is not None:
        log.info("tooltip detected via canny conf=%.2f bbox=%s", canny.confidence, canny.bbox)
        return canny

    hsv = _try_hsv(arr)
    if hsv is not None:
        log.info("tooltip detected via hsv conf=%.2f bbox=%s", hsv.confidence, hsv.bbox)
        return hsv

    raise TooltipNotFound(
        f"no plausible tooltip card on {w}x{h} screenshot "
        f"(tried canny edges + HSV fallback). "
        "Set BLOOD_HUNT_OCR_DEBUG=1 and re-run to inspect intermediate images."
    )


def crop_card(bgr: Any, card: DetectedCard) -> Any:
    """Crop the detected card region out of the full-screen image."""
    import numpy as np

    x, y, w, h = card.bbox
    arr = np.asarray(bgr)
    img_h, img_w = arr.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img_w, x + w), min(img_h, y + h)
    if x1 <= x0 or y1 <= y0:
        raise TooltipNotFound(
            f"card bbox {card.bbox} fell outside image {img_w}x{img_h}"
        )
    return arr[y0:y1, x0:x1].copy()
