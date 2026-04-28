"""End-to-end fixture accuracy gate.

Every directory under `apps/api/tests/fixtures/ocr/fixture_*` must contain:

    screenshot.png   — a full-screen Marvel Rivals screenshot with a tooltip
    expected.json    — ground-truth schema:
        {
          "name": str | null,
          "slot": "weapon"|"armor"|"accessory"|"exclusive",
          "rarity": "common"|"uncommon"|"rare"|"epic"|"legendary",
          "level": int,
          "base_effect": str,
          "base_value": float,
          "extended_effects": [{"stat_id": str, "tier": "S".."D", "value": float}, ...]
        }

The pipeline runs against each `screenshot.png`; the result is compared field-
by-field against `expected.json` with tolerance on numeric values (±2% or ±1).

When no fixtures exist (early Phase 2, before user captures), the test
collection is **skipped** so `make test` stays green. As soon as fixtures land
this becomes the accuracy gate from CLAUDE.md §7.1: ≥9 of 10 must pass.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")  # whole suite needs cv2 + tesseract; skip if absent

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ocr"

# Numeric tolerance for OCR-read values vs. ground truth.
ABS_TOL = 1.0
REL_TOL = 0.02

# Item-name OCR rarely matches stylised in-game fonts exactly; use a fuzzy ratio
# instead of strict equality. 80 is a reasonable starting threshold; tighten
# once we've seen the pipeline's actual accuracy on real fixtures.
NAME_FUZZ_THRESHOLD = 80.0

# Required pass rate to count Phase 2 as accuracy-met.
TARGET_PASS_RATE = 0.9


def _fixtures() -> list[Path]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in FIXTURES_DIR.glob("fixture_*") if p.is_dir())


@dataclass
class Mismatch:
    field: str
    expected: object
    actual: object


def _within_tolerance(expected: float, actual: float) -> bool:
    if expected == actual:
        return True
    if abs(expected - actual) <= ABS_TOL:
        return True
    return expected != 0 and abs((expected - actual) / expected) <= REL_TOL


def _compare_extended_effects(
    expected: list[dict[str, object]],
    actual: list[dict[str, object]],
) -> list[Mismatch]:
    """Compare extended-effect lists by stat_id (order-insensitive — the whole
    point of content-based identification is that row order doesn't matter)."""
    out: list[Mismatch] = []
    e_by_stat = {e["stat_id"]: e for e in expected}
    a_by_stat = {a["stat_id"]: a for a in actual}
    missing = sorted(set(e_by_stat) - set(a_by_stat))
    extra = sorted(set(a_by_stat) - set(e_by_stat))
    for stat in missing:
        out.append(Mismatch(f"extended_effects[{stat}]", "present", "missing"))
    for stat in extra:
        out.append(Mismatch(f"extended_effects[{stat}]", "absent", "extra"))
    for stat in sorted(set(e_by_stat) & set(a_by_stat)):
        e = e_by_stat[stat]
        a = a_by_stat[stat]
        if e["tier"] != a["tier"]:
            out.append(Mismatch(f"extended_effects[{stat}].tier", e["tier"], a["tier"]))
        ev = float(e["value"])  # type: ignore[arg-type]
        av = float(a["value"])  # type: ignore[arg-type]
        if not _within_tolerance(ev, av):
            out.append(Mismatch(f"extended_effects[{stat}].value", ev, av))
    return out


def _name_matches(expected: object, actual: object) -> bool:
    """Fuzzy item-name match. Both sides may legitimately be None for items
    without a display name; if the ground truth has a name, the pipeline must
    return one that's close enough."""
    from rapidfuzz import fuzz

    if expected is None or expected == "":
        return True  # nothing to verify
    if actual is None or actual == "":
        return False
    return fuzz.WRatio(str(expected), str(actual)) >= NAME_FUZZ_THRESHOLD


def _compare(expected: dict[str, object], actual: dict[str, object]) -> list[Mismatch]:
    out: list[Mismatch] = []
    for key in ("slot", "rarity"):
        if expected.get(key) != actual.get(key):
            out.append(Mismatch(key, expected.get(key), actual.get(key)))
    if expected.get("level") != actual.get("level"):
        out.append(Mismatch("level", expected.get("level"), actual.get("level")))
    if not _name_matches(expected.get("name"), actual.get("name")):
        out.append(Mismatch("name", expected.get("name"), actual.get("name")))
    if expected.get("base_effect") != actual.get("base_effect"):
        out.append(
            Mismatch("base_effect", expected.get("base_effect"), actual.get("base_effect"))
        )
    ev = float(expected.get("base_value", 0))  # type: ignore[arg-type]
    av = float(actual.get("base_value", 0))  # type: ignore[arg-type]
    if not _within_tolerance(ev, av):
        out.append(Mismatch("base_value", ev, av))
    out.extend(
        _compare_extended_effects(
            list(expected.get("extended_effects", [])),  # type: ignore[arg-type]
            list(actual.get("extended_effects", [])),  # type: ignore[arg-type]
        )
    )
    return out


def _serialize_actual(parsed: object) -> dict[str, object]:
    """Pull just the comparable fields out of a ParsedGear."""
    # Imported here so the module-level skipif still triggers cleanly.
    from app.schemas.gear import ParsedGear

    assert isinstance(parsed, ParsedGear)
    return {
        "name": parsed.name,
        "slot": parsed.slot,
        "rarity": parsed.rarity,
        "level": parsed.level,
        "base_effect": parsed.base_effect,
        "base_value": parsed.base_value,
        "extended_effects": [
            {"stat_id": e.stat_id, "tier": e.tier, "value": e.value}
            for e in parsed.extended_effects
        ],
    }


def _stat_catalog() -> list[str]:
    from app.data_loader import load_game_data, stat_catalog

    return stat_catalog(load_game_data())


@pytest.fixture(scope="module")
def fixtures_present() -> list[Path]:
    fixtures = _fixtures()
    if not fixtures:
        pytest.skip(
            "No OCR fixtures yet under tests/fixtures/ocr/. "
            "Capture screenshots per PHASE2_OCR_INPUTS.md to enable this gate."
        )
    return fixtures


def _iter_fixture_ids(fixtures: Iterable[Path]) -> list[str]:
    return [p.name for p in fixtures]


# ---------------------------------------------------------------------------
# Per-fixture parametrized test
# ---------------------------------------------------------------------------
def _parametrized_fixtures() -> list[Path]:
    """Eager fixture discovery for parametrize. Empty list → 0 tests collected."""
    return _fixtures()


@pytest.mark.parametrize(
    "fixture_dir",
    _parametrized_fixtures(),
    ids=_iter_fixture_ids(_parametrized_fixtures()) or ["__none__"],
)
def test_fixture_parses_correctly(fixture_dir: Path) -> None:
    """Each fixture must parse with no field mismatches."""
    pytest.importorskip("pytesseract")  # skip per-test if tesseract isn't installed
    from app.ocr.pipeline import parse_gear_screenshot

    screenshot = fixture_dir / "screenshot.png"
    expected_path = fixture_dir / "expected.json"
    assert screenshot.exists(), f"missing {screenshot}"
    assert expected_path.exists(), f"missing {expected_path}"

    expected = json.loads(expected_path.read_text("utf-8"))
    parsed = parse_gear_screenshot(str(screenshot), _stat_catalog())
    actual = _serialize_actual(parsed)
    mismatches = _compare(expected, actual)
    assert not mismatches, "\n".join(
        f"  {m.field}: expected={m.expected!r} actual={m.actual!r}" for m in mismatches
    )


# ---------------------------------------------------------------------------
# Aggregate accuracy gate
# ---------------------------------------------------------------------------
def test_aggregate_accuracy_meets_target(fixtures_present: list[Path]) -> None:
    """≥9/10 fixtures must pass without manual correction (CLAUDE.md §7.1)."""
    pytest.importorskip("pytesseract")
    from app.ocr.pipeline import parse_gear_screenshot

    catalog = _stat_catalog()
    passes = 0
    failures: list[tuple[str, list[Mismatch]]] = []
    for fx in fixtures_present:
        expected = json.loads((fx / "expected.json").read_text("utf-8"))
        try:
            parsed = parse_gear_screenshot(str(fx / "screenshot.png"), catalog)
        except Exception as exc:  # noqa: BLE001
            failures.append((fx.name, [Mismatch("pipeline", "ParsedGear", repr(exc))]))
            continue
        actual = _serialize_actual(parsed)
        mismatches = _compare(expected, actual)
        if mismatches:
            failures.append((fx.name, mismatches))
        else:
            passes += 1

    total = len(fixtures_present)
    rate = passes / total
    if rate < TARGET_PASS_RATE:
        msg = [f"{passes}/{total} fixtures passed (target ≥{TARGET_PASS_RATE:.0%})."]
        for name, mismatches in failures:
            msg.append(f"  {name}:")
            for m in mismatches:
                msg.append(f"    {m.field}: expected={m.expected!r} actual={m.actual!r}")
        pytest.fail("\n".join(msg))
