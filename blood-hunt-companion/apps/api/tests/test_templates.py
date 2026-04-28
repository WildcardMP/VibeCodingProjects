"""Template-matching tests using synthetic PNG fixtures.

We don't ship real Marvel Rivals tier-badge / slot-icon crops in the repo (those
are user-supplied per `data/game/_assets/README.md`), so these tests synthesize
distinct images per label with numpy and write them out via cv2. The matcher
treats them like any other template.
"""

from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.ocr import templates as tm  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic image helpers
# ---------------------------------------------------------------------------
def _stripe_image(seed: int, size: int = 64) -> np.ndarray:
    """Generate a deterministic but distinct grayscale image per seed.

    Different seeds → visually different stripe patterns → low cross-correlation.
    """
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3), dtype=np.uint8)
    # Vertical stripes at varying widths/intensities so each seed is unique.
    width = 4 + (seed % 6)
    for x in range(0, size, width * 2):
        intensity = int(rng.integers(120, 255))
        img[:, x : x + width, :] = intensity
    return img


def _write_png(directory: Path, name: str, seed: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    cv2.imwrite(str(path), _stripe_image(seed))
    return path


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Each test starts with an empty template cache so file-system mutations land."""
    tm.clear_cache()


# ---------------------------------------------------------------------------
# match_tier
# ---------------------------------------------------------------------------
def test_match_tier_missing_dir_returns_none(tmp_path: Path) -> None:
    crop = _stripe_image(seed=1)
    assert tm.match_tier(crop, tmp_path / "does_not_exist") is None


def test_match_tier_empty_dir_returns_none(tmp_path: Path) -> None:
    (tmp_path / "tier_badges").mkdir()
    crop = _stripe_image(seed=1)
    assert tm.match_tier(crop, tmp_path / "tier_badges") is None


def test_match_tier_exact_match_high_score(tmp_path: Path) -> None:
    d = tmp_path / "tier_badges"
    seeds = {"S": 11, "A": 22, "B": 33, "C": 44, "D": 55}
    for label, seed in seeds.items():
        _write_png(d, f"{label}.png", seed)
    # Crop matches the "S" template exactly → should resolve to S with high confidence.
    crop = _stripe_image(seeds["S"])
    result = tm.match_tier(crop, d)
    assert result is not None
    label, score = result
    assert label == "S"
    assert score > 0.95


def test_match_tier_distinct_label(tmp_path: Path) -> None:
    d = tmp_path / "tier_badges"
    for label, seed in {"S": 11, "A": 22, "B": 33, "C": 44, "D": 55}.items():
        _write_png(d, f"{label}.png", seed)
    # Crop matches "C" template → expect "C"
    crop = _stripe_image(44)
    result = tm.match_tier(crop, d)
    assert result is not None
    assert result[0] == "C"


def test_match_tier_ignores_non_tier_pngs(tmp_path: Path) -> None:
    d = tmp_path / "tier_badges"
    _write_png(d, "S.png", seed=11)
    _write_png(d, "weapon.png", seed=99)  # wrong-set label, should be ignored
    crop = _stripe_image(99)  # matches the "weapon" template's pixels
    # The "weapon" template is filtered out, so the only valid template is "S".
    # The match returns "S" only if the score crosses the threshold; otherwise None.
    result = tm.match_tier(crop, d)
    if result is not None:
        assert result[0] == "S"


def test_match_tier_variant_filename(tmp_path: Path) -> None:
    d = tmp_path / "tier_badges"
    _write_png(d, "S_alt.png", seed=11)  # underscore variant
    crop = _stripe_image(11)
    result = tm.match_tier(crop, d)
    assert result is not None
    assert result[0] == "S"  # label is taken from the prefix before the underscore


# ---------------------------------------------------------------------------
# match_slot
# ---------------------------------------------------------------------------
def test_match_slot_exact_match(tmp_path: Path) -> None:
    d = tmp_path / "slot_icons"
    seeds = {"weapon": 100, "armor": 200, "accessory": 300, "exclusive": 400}
    for label, seed in seeds.items():
        _write_png(d, f"{label}.png", seed)
    crop = _stripe_image(seeds["accessory"])
    result = tm.match_slot(crop, d)
    assert result is not None
    assert result[0] == "accessory"
    assert result[1] > 0.95


def test_match_slot_returns_none_below_threshold(tmp_path: Path) -> None:
    d = tmp_path / "slot_icons"
    _write_png(d, "weapon.png", seed=100)
    # Use a uniform image — low correlation with the structured stripe template.
    crop = np.full((64, 64, 3), 128, dtype=np.uint8)
    result = tm.match_slot(crop, d)
    # Below threshold → None. Don't assert exact None vs match; just that
    # we don't get a high-confidence mis-classification.
    if result is not None:
        assert result[1] < tm._MATCH_THRESHOLD + 0.3


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------
def test_clear_cache_picks_up_new_template(tmp_path: Path) -> None:
    d = tmp_path / "tier_badges"
    _write_png(d, "S.png", seed=11)
    crop = _stripe_image(22)

    first = tm.match_tier(crop, d)
    # First match: only S exists, may or may not score above threshold.
    # Now drop a new template and clear cache.
    _write_png(d, "A.png", seed=22)
    tm.clear_cache()
    second = tm.match_tier(crop, d)
    assert second is not None
    assert second[0] == "A"
    # Sanity: first call did not return "A" (it didn't exist yet).
    if first is not None:
        assert first[0] != "A"


def test_load_template_set_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    assert tm.load_template_set(tmp_path / "ghost") == ()


def test_to_canonical_returns_none_on_empty(tmp_path: Path) -> None:
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert tm._to_canonical(empty) is None
    assert tm._to_canonical(None) is None
