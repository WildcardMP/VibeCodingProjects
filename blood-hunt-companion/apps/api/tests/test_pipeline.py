"""Pipeline reconciliation tests — tier dual strategy + slot resolution.

These exercise `resolve_tier` and `resolve_slot` directly so we can cover all
four reconciliation cases without standing up a full screenshot fixture suite.
The full end-to-end OCR test lives in `test_ocr_fixtures.py` (TODO — Phase 2 §7.1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.ocr import templates as tm  # noqa: E402
from app.ocr.calibration import Calibration, CalibrationRegions  # noqa: E402
from app.ocr.pipeline import resolve_slot, resolve_tier  # noqa: E402


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


@pytest.fixture
def empty_calibration() -> Calibration:
    """Calibration with no slot_icon region — forces heuristic fallback for slots."""
    return Calibration(
        resolution=(1920, 1080),
        ui_scale=1.0,
        regions=CalibrationRegions(
            card=(0, 0, 100, 100),
            name=(0, 0, 50, 20),
            rarity_badge=(0, 0, 20, 20),
            level=(0, 0, 30, 20),
            base_effect=(0, 0, 100, 30),
            extended_effects=[],
            slot_icon=None,
        ),
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
    # No template directory → only Tesseract has a signal.
    crop = _stripe(11)
    letter, conf = resolve_tier(crop, "B", templates_dir=tmp_path / "missing")
    assert letter == "B"
    assert conf == pytest.approx(0.65)


def test_resolve_tier_only_template_returns_yellow_band(tier_dir: Path) -> None:
    # Empty Tesseract output (e.g., low-resolution badge OCR fails) but template hits.
    crop = _stripe(33)  # matches "B" template
    letter, conf = resolve_tier(crop, "", templates_dir=tier_dir)
    assert letter == "B"
    assert conf == pytest.approx(0.65)


def test_resolve_tier_neither_returns_none(tmp_path: Path) -> None:
    # No template dir AND empty Tesseract.
    crop = _stripe(1)
    letter, conf = resolve_tier(crop, "", templates_dir=tmp_path / "ghost")
    assert letter is None
    assert conf == 0.0


def test_resolve_tier_disagreement_trusts_template(tier_dir: Path) -> None:
    # Crop matches "A" template, Tesseract says "S" — template wins.
    crop = _stripe(22)
    letter, conf = resolve_tier(crop, "S", templates_dir=tier_dir)
    assert letter == "A"
    assert conf == pytest.approx(0.65)


def test_resolve_tier_strips_garbage_from_tesseract(tier_dir: Path) -> None:
    # Tesseract sometimes emits punctuation around the letter. Should still parse.
    crop = _stripe(55)  # matches "D" template
    letter, conf = resolve_tier(crop, "  D.", templates_dir=tier_dir)
    assert letter == "D"
    assert conf == 1.0


# ---------------------------------------------------------------------------
# resolve_slot — heuristic fallback
# ---------------------------------------------------------------------------
def test_resolve_slot_falls_back_to_heuristic_without_calibration(
    empty_calibration: Calibration,
) -> None:
    img = _stripe(7)  # not used; calibration has no slot_icon region
    slot, conf = resolve_slot(img, empty_calibration, "Total Output Boost")
    assert slot == "armor"
    assert conf == 0.5


def test_resolve_slot_heuristic_distinct_per_base_effect(
    empty_calibration: Calibration,
) -> None:
    img = _stripe(7)
    assert resolve_slot(img, empty_calibration, "Precision Damage")[0] == "weapon"
    assert resolve_slot(img, empty_calibration, "Boss Damage")[0] == "accessory"
    assert resolve_slot(img, empty_calibration, "HP")[0] == "armor"


def test_resolve_slot_heuristic_unknown_stat_defaults_to_armor(
    empty_calibration: Calibration,
) -> None:
    img = _stripe(7)
    slot, conf = resolve_slot(img, empty_calibration, "Some Future Stat")
    assert slot == "armor"
    assert conf == 0.5


def test_resolve_slot_uses_template_match_when_calibration_has_region(
    tmp_path: Path,
) -> None:
    slot_dir = tmp_path / "slot_icons"
    seeds = {"weapon": 100, "armor": 200, "accessory": 300, "exclusive": 400}
    for label, seed in seeds.items():
        cv2.imwrite(str(slot_dir / f"{label}.png"), _stripe(seed))
        slot_dir.mkdir(parents=True, exist_ok=True) if not slot_dir.exists() else None
    # Re-write since mkdir may not have been needed first time
    slot_dir.mkdir(parents=True, exist_ok=True)
    for label, seed in seeds.items():
        cv2.imwrite(str(slot_dir / f"{label}.png"), _stripe(seed))

    # 200x200 image: at coords (10,10,64,64) we'll embed the "exclusive" stripe pattern.
    big = np.zeros((200, 200, 3), dtype=np.uint8)
    big[10:74, 10:74] = _stripe(seeds["exclusive"])

    calibration = Calibration(
        resolution=(200, 200),
        ui_scale=1.0,
        regions=CalibrationRegions(
            card=(0, 0, 200, 200),
            name=(0, 0, 50, 20),
            rarity_badge=(0, 0, 20, 20),
            level=(0, 0, 30, 20),
            base_effect=(0, 0, 100, 30),
            extended_effects=[],
            slot_icon=(10, 10, 64, 64),
        ),
    )
    slot, conf = resolve_slot(big, calibration, "Total Output Boost", templates_dir=slot_dir)
    assert slot == "exclusive"
    assert conf > 0.8
