"""Stage 1 (tooltip detection) tests using synthetic full-screen images.

We can't ship real Marvel Rivals screenshots in the repo (those land later
under `tests/fixtures/ocr/fixture_NN/`). Instead we synthesize backgrounds with
random noise and embed a "tooltip"-shaped rectangle at known coordinates, then
verify `detect_tooltip` finds something close to where we put it.

These tests guard the geometry-filter logic — area floor, aspect ratio, raise
on missing tooltip — without claiming anything about how well the detector
performs against the real game UI.
"""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.ocr.detect import (  # noqa: E402
    DetectedCard,
    TooltipNotFound,
    crop_card,
    detect_tooltip,
)


def _noise_background(width: int = 1920, height: int = 1080, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(60, 180, size=(height, width, 3), dtype=np.uint8)


def _embed_tooltip(
    bg: np.ndarray,
    bbox: tuple[int, int, int, int],
    *,
    fill: int = 30,        # dark, opaque-ish background
    border: int = 220,     # bright border so Canny edges are obvious
    border_thick: int = 3,
) -> np.ndarray:
    out = bg.copy()
    x, y, w, h = bbox
    out[y : y + h, x : x + w] = fill
    cv2.rectangle(out, (x, y), (x + w, y + h), (border, border, border), border_thick)
    return out


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def test_detect_finds_synthetic_card_via_canny() -> None:
    bg = _noise_background(1920, 1080)
    bbox = (1300, 200, 480, 720)  # right side, portrait, ~16% of screen
    image = _embed_tooltip(bg, bbox)

    card = detect_tooltip(image)
    assert isinstance(card, DetectedCard)
    # Allow some slack — the dilation step expands the bbox a few pixels.
    dx = abs(card.bbox[0] - bbox[0])
    dy = abs(card.bbox[1] - bbox[1])
    dw = abs(card.bbox[2] - bbox[2])
    dh = abs(card.bbox[3] - bbox[3])
    assert dx <= 8 and dy <= 8 and dw <= 16 and dh <= 16, (
        f"detected {card.bbox} too far from {bbox}"
    )
    assert 0.55 <= card.confidence <= 1.0


def test_detect_handles_card_at_left_edge() -> None:
    bg = _noise_background()
    bbox = (40, 120, 420, 700)
    image = _embed_tooltip(bg, bbox)
    card = detect_tooltip(image)
    # Centre of detection is within the embedded region.
    cx = card.bbox[0] + card.bbox[2] // 2
    cy = card.bbox[1] + card.bbox[3] // 2
    assert bbox[0] <= cx <= bbox[0] + bbox[2]
    assert bbox[1] <= cy <= bbox[1] + bbox[3]


def test_detect_raises_on_empty_image() -> None:
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(TooltipNotFound):
        detect_tooltip(empty)


def test_detect_raises_on_blank_screen() -> None:
    """Uniform image — no edges, no dark patches — should fail cleanly."""
    blank = np.full((600, 800, 3), 128, dtype=np.uint8)
    with pytest.raises(TooltipNotFound):
        detect_tooltip(blank)


def test_detect_rejects_non_bgr_input() -> None:
    grayscale = np.zeros((600, 800), dtype=np.uint8)
    with pytest.raises(TooltipNotFound):
        detect_tooltip(grayscale)


def test_detect_skips_too_small_candidate() -> None:
    """A tooltip-shaped rectangle below the area floor should be ignored."""
    bg = _noise_background(1920, 1080)
    # 80x80 = 0.3% of the 1920x1080 screen; well below 3% floor.
    image = _embed_tooltip(bg, (100, 100, 80, 80))
    with pytest.raises(TooltipNotFound):
        detect_tooltip(image)


def test_detect_skips_extremely_wide_candidate() -> None:
    """A bar that's wider than tall (aspect <0.6) should be filtered out."""
    bg = _noise_background(1920, 1080)
    # 1700x150 — wide and short.
    image = _embed_tooltip(bg, (100, 400, 1700, 150))
    with pytest.raises(TooltipNotFound):
        detect_tooltip(image)


# ---------------------------------------------------------------------------
# crop_card
# ---------------------------------------------------------------------------
def test_crop_card_returns_correct_region() -> None:
    bg = _noise_background()
    bbox = (1300, 200, 480, 720)
    image = _embed_tooltip(bg, bbox)
    card = detect_tooltip(image)
    cropped = crop_card(image, card)
    assert cropped.shape[0] == card.bbox[3]
    assert cropped.shape[1] == card.bbox[2]
    assert cropped.shape[2] == 3


def test_crop_card_raises_on_out_of_bounds() -> None:
    bg = _noise_background(800, 600)
    fake_card = DetectedCard(bbox=(2000, 2000, 100, 100), confidence=0.9, method="canny")
    with pytest.raises(TooltipNotFound):
        crop_card(bg, fake_card)
