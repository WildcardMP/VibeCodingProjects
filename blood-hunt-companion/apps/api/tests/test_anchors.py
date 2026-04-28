"""Stages 2 & 3 — proportional anchor and row-segmentation tests.

Unit-level checks on the math, not on real screenshots:

- `compute_anchors` returns regions whose proportions match `_PROPORTIONS` and
  always fall inside the card.
- `segment_rows` picks up the right number of text rows from synthetic strips
  with known row positions, ignores rows that are too thin, and caps at 4 rows.
"""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.ocr.anchors import (  # noqa: E402
    CardAnchors,
    Region,
    compute_anchors,
    crop,
    segment_rows,
)


# ---------------------------------------------------------------------------
# compute_anchors
# ---------------------------------------------------------------------------
def test_anchors_proportional_to_card_size() -> None:
    card = np.zeros((800, 400, 3), dtype=np.uint8)  # H=800, W=400
    anchors = compute_anchors(card)

    assert isinstance(anchors, CardAnchors)
    assert anchors.card_size == (400, 800)
    # Name region should sit in the top band.
    assert anchors.name.y < 100  # top band, well under 800/8
    # Rarity badge should be on the right side.
    assert anchors.rarity_badge.x + anchors.rarity_badge.w >= 0.95 * 400 - 8
    # Slot icon should be on the left.
    assert anchors.slot_icon.x < 50
    # Extended-effects block should occupy roughly the bottom half.
    assert anchors.extended_effects.y >= 0.30 * 800
    assert (anchors.extended_effects.y + anchors.extended_effects.h) <= 800


def test_anchors_clip_to_card_bounds() -> None:
    """Tiny cards must still produce non-degenerate regions."""
    card = np.zeros((40, 40, 3), dtype=np.uint8)
    anchors = compute_anchors(card)
    for region in (
        anchors.name,
        anchors.slot_icon,
        anchors.rarity_badge,
        anchors.level,
        anchors.base_effect,
        anchors.extended_effects,
    ):
        assert region.x >= 0
        assert region.y >= 0
        assert region.w >= 1
        assert region.h >= 1
        assert region.x + region.w <= 40
        assert region.y + region.h <= 40


def test_anchors_rejects_non_bgr_input() -> None:
    gray = np.zeros((400, 200), dtype=np.uint8)
    with pytest.raises(ValueError):
        compute_anchors(gray)


def test_crop_handles_out_of_bounds_region() -> None:
    card = np.zeros((100, 100, 3), dtype=np.uint8)
    cropped = crop(card, Region(x=200, y=200, w=50, h=50))
    assert cropped.shape == (0, 0, 3)


# ---------------------------------------------------------------------------
# segment_rows
# ---------------------------------------------------------------------------
def _strip_with_rows(
    n_rows: int,
    *,
    width: int = 400,
    row_h: int = 30,
    gap_h: int = 20,
    bg: int = 30,
    fg: int = 220,
) -> np.ndarray:
    """Build a synthetic extended-effects strip with `n_rows` of "text"."""
    height = max(1, n_rows * row_h + (n_rows + 1) * gap_h)
    strip = np.full((height, width, 3), bg, dtype=np.uint8)
    for i in range(n_rows):
        y = gap_h + i * (row_h + gap_h)
        # Draw a few horizontal "ink" bars so the row has dense pixels.
        cv2.rectangle(strip, (10, y + 5), (width - 10, y + row_h - 5), (fg, fg, fg), -1)
    return strip


def test_segment_rows_finds_three_rows() -> None:
    strip = _strip_with_rows(3)
    rows = segment_rows(strip)
    assert len(rows) == 3
    # Rows are sorted top-to-bottom.
    assert all(rows[i][0] < rows[i + 1][0] for i in range(len(rows) - 1))
    # Each row has positive height.
    for y0, y1 in rows:
        assert y1 > y0


def test_segment_rows_finds_one_row() -> None:
    strip = _strip_with_rows(1)
    assert len(segment_rows(strip)) == 1


def test_segment_rows_empty_strip_returns_empty() -> None:
    blank = np.full((200, 400, 3), 30, dtype=np.uint8)  # all background
    assert segment_rows(blank) == []


def test_segment_rows_handles_zero_size_input() -> None:
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert segment_rows(empty) == []


def test_segment_rows_caps_at_four() -> None:
    strip = _strip_with_rows(6)  # six rows; should clip to 4
    rows = segment_rows(strip)
    assert len(rows) == 4


def test_segment_rows_filters_thin_noise() -> None:
    """A 1-px ink streak is below the min-row-height threshold and should drop."""
    height, width = 400, 300
    strip = np.full((height, width, 3), 30, dtype=np.uint8)
    # One real row.
    cv2.rectangle(strip, (10, 50), (width - 10, 80), (220, 220, 220), -1)
    # One 1-pixel stray.
    strip[300, 50:200] = 220
    rows = segment_rows(strip)
    # Only the real row survives.
    assert len(rows) == 1
    y0, y1 = rows[0]
    assert 40 <= y0 <= 60 and 75 <= y1 <= 90
