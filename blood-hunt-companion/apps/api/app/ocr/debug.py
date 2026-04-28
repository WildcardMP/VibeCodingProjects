"""Annotated debug-image dumps for the OCR pipeline.

Gated on the `BLOOD_HUNT_OCR_DEBUG=1` environment variable (read once at process
start via `app.config.settings()`). When enabled, intermediate stage outputs are
written as annotated PNGs under `data/debug/<stage>/<timestamp>_<label>.png`.

This is the single most useful tool when tuning Stages 1–3 against real
fixtures. The cost is a few PNGs per call when the flag is on; zero overhead
when off (every helper short-circuits at the top).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)


def is_enabled() -> bool:
    return settings().ocr_debug


def _stage_dir(stage: str) -> Path | None:
    if not is_enabled():
        return None
    d = settings().debug_dir / stage
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def dump_image(stage: str, label: str, image: Any) -> Path | None:
    """Write a raw or annotated image. No-op unless debug is on.

    Returns the written path (or None) so callers can log it.
    """
    d = _stage_dir(stage)
    if d is None:
        return None
    import cv2

    path = d / f"{_timestamp()}_{label}.png"
    try:
        cv2.imwrite(str(path), image)
    except Exception:  # noqa: BLE001
        log.exception("debug dump failed for %s/%s", stage, label)
        return None
    return path


def dump_with_box(
    stage: str,
    label: str,
    image: Any,
    bbox: tuple[int, int, int, int],
    color: tuple[int, int, int] = (0, 255, 0),
) -> Path | None:
    """Annotate `image` with a rectangle at `bbox` and dump."""
    if not is_enabled():
        return None
    import cv2
    import numpy as np

    canvas = np.asarray(image).copy()
    x, y, w, h = bbox
    cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
    return dump_image(stage, label, canvas)


def dump_with_boxes(
    stage: str,
    label: str,
    image: Any,
    boxes: list[tuple[str, tuple[int, int, int, int]]],
    color: tuple[int, int, int] = (0, 255, 0),
) -> Path | None:
    """Annotate `image` with multiple labeled rectangles and dump."""
    if not is_enabled():
        return None
    import cv2
    import numpy as np

    canvas = np.asarray(image).copy()
    for name, (x, y, w, h) in boxes:
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            canvas, name, (x, max(15, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    return dump_image(stage, label, canvas)
