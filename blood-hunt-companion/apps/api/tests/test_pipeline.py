"""Pipeline reconciliation tests — tier dual strategy + slot resolution.

These exercise `resolve_tier` and `resolve_slot` directly so we can cover all
four reconciliation cases without standing up a full screenshot fixture suite.
The end-to-end OCR test lives in `test_ocr_fixtures.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.ocr import templates as tm  # noqa: E402
from app.ocr.anchors import CardAnchors, Region  # noqa: E402
from app.ocr.pipeline import (  # noqa: E402
    fields_below_review_threshold,
    resolve_slot,
    resolve_tier,
)
from app.schemas.gear import ExtendedEffect, ParsedGear  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stripe(seed: int, size: int = 64) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3), dtype=np.uint8)
    width = 4 + (seed % 6)
    for x in range(0, size, width * 2):
        img[:, x : x + width, :] = int(rng.integers(120, 255))
    return img


def _write_tier_templates(directory: Path, mapping: dict[str, int]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for label, seed in mapping.items():
        cv2.imwrite(str(directory / f"{label}.png"), _stripe(seed))


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    tm.clear_cache()


@pytest.fixture
def tier_dir(tmp_path: Path) -> Path:
    d = tmp_path / "tier_badges"
    _write_tier_templates(d, {"S": 11, "A": 22, "B": 33, "C": 44, "D": 55})
    return d


def _stub_anchors(card_w: int = 200, card_h: int = 400) -> CardAnchors:
    """Build CardAnchors with all regions defaulted to small, valid boxes.

    Tests that don't actually exercise template-matched slots can use this to
    skip the slot_icon path and force the heuristic fallback.
    """
    return CardAnchors(
        card_size=(card_w, card_h),
        name=Region(0, 0, card_w, 20),
        slot_icon=Region(0, 0, 1, 1),
        rarity_badge=Region(0, 0, 10, 10),
        level=Region(0, 0, 30, 20),
        base_effect=Region(0, 0, card_w, 30),
        extended_effects=Region(0, 0, card_w, card_h - 60),
    )


# ---------------------------------------------------------------------------
# resolve_tier — four reconciliation cases
# ---------------------------------------------------------------------------
def test_resolve_tier_both_agree_returns_full_confidence(tier_dir: Path) -> None:
    crop = _stripe(11)  # matches "S" template
    letter, conf = resolve_tier(crop, "S", templates_dir=tier_dir)
    assert letter == "S"
    assert conf == 1.0


def test_resolve_tier_only_tesseract_returns_yellow_band(tmp_path: Path) -> None:
    crop = _stripe(11)
    letter, conf = resolve_tier(crop, "B", templates_dir=tmp_path / "missing")
    assert letter == "B"
    assert conf == pytest.approx(0.65)


def test_resolve_tier_only_template_returns_yellow_band(tier_dir: Path) -> None:
    crop = _stripe(33)  # matches "B"
    letter, conf = resolve_tier(crop, "", templates_dir=tier_dir)
    assert letter == "B"
    assert conf == pytest.approx(0.65)


def test_resolve_tier_neither_returns_none(tmp_path: Path) -> None:
    crop = _stripe(1)
    letter, conf = resolve_tier(crop, "", templates_dir=tmp_path / "ghost")
    assert letter is None
    assert conf == 0.0


def test_resolve_tier_disagreement_trusts_template(tier_dir: Path) -> None:
    crop = _stripe(22)  # "A" template
    letter, conf = resolve_tier(crop, "S", templates_dir=tier_dir)
    assert letter == "A"
    assert conf == pytest.approx(0.65)


def test_resolve_tier_strips_garbage_from_tesseract(tier_dir: Path) -> None:
    crop = _stripe(55)  # "D"
    letter, conf = resolve_tier(crop, "  D.", templates_dir=tier_dir)
    assert letter == "D"
    assert conf == 1.0


# ---------------------------------------------------------------------------
# resolve_slot — heuristic fallback (template miss)
# ---------------------------------------------------------------------------
def test_resolve_slot_falls_back_to_heuristic_without_templates(tmp_path: Path) -> None:
    card = np.zeros((400, 200, 3), dtype=np.uint8)
    anchors = _stub_anchors()
    slot, conf = resolve_slot(
        card, anchors, "Total Output Boost", templates_dir=tmp_path / "missing"
    )
    assert slot == "armor"
    assert conf == 0.5


def test_resolve_slot_heuristic_distinct_per_base_effect(tmp_path: Path) -> None:
    card = np.zeros((400, 200, 3), dtype=np.uint8)
    anchors = _stub_anchors()
    missing = tmp_path / "missing"
    assert resolve_slot(card, anchors, "Precision Damage", templates_dir=missing)[0] == "weapon"
    assert resolve_slot(card, anchors, "Boss Damage", templates_dir=missing)[0] == "accessory"
    assert resolve_slot(card, anchors, "HP", templates_dir=missing)[0] == "armor"


def test_resolve_slot_heuristic_unknown_stat_defaults_to_armor(tmp_path: Path) -> None:
    card = np.zeros((400, 200, 3), dtype=np.uint8)
    anchors = _stub_anchors()
    slot, conf = resolve_slot(
        card, anchors, "Some Future Stat", templates_dir=tmp_path / "missing"
    )
    assert slot == "armor"
    assert conf == 0.5


def test_resolve_slot_uses_template_match_when_available(tmp_path: Path) -> None:
    slot_dir = tmp_path / "slot_icons"
    slot_dir.mkdir(parents=True, exist_ok=True)
    seeds = {"weapon": 100, "armor": 200, "accessory": 300, "exclusive": 400}
    for label, seed in seeds.items():
        cv2.imwrite(str(slot_dir / f"{label}.png"), _stripe(seed))

    card = np.zeros((400, 200, 3), dtype=np.uint8)
    # Embed the "exclusive" stripe pattern at the slot_icon anchor.
    card[10:74, 10:74] = _stripe(seeds["exclusive"])
    anchors = CardAnchors(
        card_size=(200, 400),
        name=Region(0, 0, 200, 20),
        slot_icon=Region(10, 10, 64, 64),
        rarity_badge=Region(0, 0, 10, 10),
        level=Region(0, 0, 30, 20),
        base_effect=Region(0, 0, 200, 30),
        extended_effects=Region(0, 0, 200, 340),
    )
    slot, conf = resolve_slot(
        card, anchors, "Total Output Boost", templates_dir=slot_dir
    )
    assert slot == "exclusive"
    assert conf > 0.8


# ---------------------------------------------------------------------------
# fields_below_review_threshold
# ---------------------------------------------------------------------------
def test_review_threshold_flags_low_top_fields_and_low_rows() -> None:
    parsed = ParsedGear(
        slot="weapon",
        rarity="legendary",
        level=60,
        base_effect="Precision Damage",
        base_value=8300.0,
        extended_effects=[
            ExtendedEffect(stat_id="Total Output Boost", tier="S", value=4200.0, confidence=0.92),
            ExtendedEffect(stat_id="Boss Damage",        tier="A", value=1800.0, confidence=0.55),
        ],
        field_confidences={
            "name": 0.9,
            "rarity": 0.9,
            "level": 0.4,            # below threshold
            "slot": 0.65,            # below threshold
            "base_effect": 0.95,
            "base_value": 0.95,
            "detection": 0.9,
        },
    )
    flagged = fields_below_review_threshold(parsed)
    assert "level" in flagged
    assert "slot" in flagged
    assert "extended_effects[1]" in flagged
    assert "rarity" not in flagged
    assert "extended_effects[0]" not in flagged
