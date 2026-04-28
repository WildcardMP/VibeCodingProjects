"""Image template matching for tier badges and slot icons.

Templates are PNG files dropped by the user under
    data/game/_assets/tier_badges/{S,A,B,C,D}.png
    data/game/_assets/slot_icons/{weapon,armor,accessory,exclusive}.png

Variant images may use a `_<suffix>` filename, e.g. `S_alt.png` — the suffix is
ignored when picking the label so the user can ship multiple references for the
same letter or slot.

Pipeline calls `match_tier()` / `match_slot()` with a pre-cropped region from
calibration; we resize-and-correlate against each loaded template and return the
best label plus its score (0..1). If the templates directory is missing or empty
every match function returns `None`, leaving the pipeline free to fall back to
its OCR-only or heuristic path.

Module is unit-tested without Tesseract (uses cv2 + numpy only).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args

from ..schemas.common import GearSlot, TierLetter

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)

# Both template and crop are resized to this canonical (square) size before
# correlation. Small enough to keep matching cheap (hundreds of µs); big enough
# to preserve UI-badge stroke shape.
_CANONICAL_SIZE = 32

# `cv2.TM_CCOEFF_NORMED` returns scores in roughly [-1.0, 1.0]. Anything below this
# threshold is treated as "no confident match" and the function returns None so the
# pipeline can fall through to its secondary strategy.
_MATCH_THRESHOLD = 0.55


def _to_canonical(bgr: Any) -> np.ndarray | None:
    """Convert a BGR (or grayscale) crop to a 32x32 grayscale square.

    Returns None for empty or missing inputs so callers can no-op gracefully.
    """
    import cv2  # local import keeps the module importable without native deps in tests
    import numpy as np

    if bgr is None:
        return None
    arr = np.asarray(bgr)
    if arr.size == 0:
        return None
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr
    return cv2.resize(gray, (_CANONICAL_SIZE, _CANONICAL_SIZE), interpolation=cv2.INTER_AREA)


def _label_from_stem(stem: str) -> str:
    """Filename stem `S_alt` → label `S`. Stem `weapon` → label `weapon`."""
    return stem.split("_", 1)[0] if "_" in stem else stem


@lru_cache(maxsize=8)
def _load_cached(directory_str: str) -> tuple[tuple[str, np.ndarray], ...]:
    import cv2

    d = Path(directory_str)
    if not d.is_dir():
        return ()
    pairs: list[tuple[str, Any]] = []
    for path in sorted(d.glob("*.png")):
        img = cv2.imread(str(path))
        if img is None:
            log.warning("template at %s could not be decoded; skipping", path)
            continue
        canon = _to_canonical(img)
        if canon is None:
            continue
        pairs.append((_label_from_stem(path.stem), canon))
    return tuple(pairs)


def load_template_set(directory: Path) -> tuple[tuple[str, np.ndarray], ...]:
    """Return cached (label, canonical_image) pairs from a templates directory.

    The cache key is the resolved directory path, so dropping a new PNG into the
    folder requires the process to restart (or the cache to be cleared via
    `load_template_set.cache_clear()`).
    """
    return _load_cached(str(directory.resolve()))


def clear_cache() -> None:
    """Drop all cached template sets — useful in tests that mutate template dirs."""
    _load_cached.cache_clear()


def _best_match(
    crop_canon: np.ndarray | None,
    templates: tuple[tuple[str, np.ndarray], ...],
) -> tuple[str, float] | None:
    import cv2

    if crop_canon is None or not templates:
        return None
    best_label = ""
    best_score = -1.0
    for label, tmpl in templates:
        # Same-sized inputs → matchTemplate returns a 1x1 array; .max() gives the score.
        result = cv2.matchTemplate(crop_canon, tmpl, cv2.TM_CCOEFF_NORMED)
        score = float(result.max())
        if score > best_score:
            best_score = score
            best_label = label
    if best_score < _MATCH_THRESHOLD:
        return None
    return best_label, best_score


def _match_constrained(
    crop: Any,
    directory: Path,
    allowed: frozenset[str],
) -> tuple[str, float] | None:
    templates = tuple((lbl, t) for lbl, t in load_template_set(directory) if lbl in allowed)
    if not templates:
        return None
    return _best_match(_to_canonical(crop), templates)


_TIER_LABELS: frozenset[str] = frozenset(get_args(TierLetter))
_SLOT_LABELS: frozenset[str] = frozenset(get_args(GearSlot))


def match_tier(crop: Any, directory: Path) -> tuple[TierLetter, float] | None:
    """Match a tier-badge crop against template PNGs. Returns (letter, score) or None."""
    res = _match_constrained(crop, directory, _TIER_LABELS)
    if res is None:
        return None
    label, score = res
    return label, score  # type: ignore[return-value]


def match_slot(crop: Any, directory: Path) -> tuple[GearSlot, float] | None:
    """Match a slot-icon crop against template PNGs. Returns (slot, score) or None."""
    res = _match_constrained(crop, directory, _SLOT_LABELS)
    if res is None:
        return None
    label, score = res
    return label, score  # type: ignore[return-value]
