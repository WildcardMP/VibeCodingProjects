"""Image preprocessing for Tesseract.

Marvel Rivals tooltip text is white on a dark, slightly textured background. The
two transformations that matter most are:
    1. Upscale (Tesseract is tuned for ~30px x-height; upscale 2× covers it).
    2. Adaptive threshold to handle the gradient background.

Imports of cv2/numpy are local-only inside functions where it matters, so unit
tests that don't actually decode images can still import this module on machines
without the native deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np


def preprocess_for_tesseract(bgr: Any, *, upscale: int = 2) -> Any:
    """Convert a BGR image into a Tesseract-friendly black-on-white binary image.

    Args:
        bgr: HxWx3 BGR uint8 array (output of cv2.imread).
        upscale: integer upscale factor. 2 is a sweet spot for tooltip text.

    Returns:
        HxW uint8 binary image (text dark, background light).
    """
    import cv2  # local import keeps test imports cheap

    if bgr is None:
        raise ValueError("preprocess_for_tesseract: input image is None")

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    if upscale and upscale != 1:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    # Bilateral keeps text edges sharp while smoothing the tooltip gradient.
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    th = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=31,
        C=10,
    )
    # Tesseract prefers dark text on a light background.
    return cv2.bitwise_not(th)


def crop(bgr: "np.ndarray", region: tuple[int, int, int, int]) -> "np.ndarray":
    """Crop a (x, y, w, h) region. Bounds-checked; out-of-range returns empty array."""
    import numpy as np

    x, y, w, h = region
    if bgr is None or bgr.size == 0:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    H, W = bgr.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return np.zeros((0, 0, *bgr.shape[2:]), dtype=bgr.dtype)
    return bgr[y0:y1, x0:x1].copy()
