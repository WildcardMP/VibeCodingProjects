"""End-to-end fixture accuracy gate.

Every directory under `apps/api/tests/fixtures/ocr/fixture_*` must contain:

    screenshot.png   — a full-screen Marvel Rivals screenshot with a tooltip
    expected.json    — ground-truth schema (mirrors PHASE2_OCR_INPUTS.md):
        {
          "name": str | null,
          "slot": "weapon"|"armor"|"accessory"|"exclusive",
          "rarity": "normal"|"advanced"|"rare"|"epic"|"legendary",
          "hero": str,                    # in-game display name, e.g. "Moon Knight"
          "level": int,
          "rating": int,                  # tooltip overall rating, e.g. 7086
          "base_effects": [{"name": str, "value": float}, ...],
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


def _compare_base_effects(
    expected: list[dict[str, object]],
    actual: list[dict[str, object]],
) -> list[Mismatch]:
    """Compare base-effect lists by stat name (order-insensitive)."""
    out: list[Mismatch] = []
    e_by_name = {str(e["name"]): e for e in expected}
    a_by_name = {str(a["name"]): a for a in actual}
    missing = sorted(set(e_by_name) - set(a_by_name))
    extra = sorted(set(a_by_name) - set(e_by_name))
    for name in missing:
        out.append(Mismatch(f"base_effects[{name}]", "present", "missing"))
    for name in extra:
        out.append(Mismatch(f"base_effects[{name}]", "absent", "extra"))
    for name in sorted(set(e_by_name) & set(a_by_name)):
        ev = float(e_by_name[name]["value"])  # type: ignore[arg-type]
        av = float(a_by_name[name]["value"])  # type: ignore[arg-type]
        if not _within_tolerance(ev, av):
            out.append(Mismatch(f"base_effects[{name}].value", ev, av))
    return out


def _compare(expected: dict[str, object], actual: dict[str, object]) -> list[Mismatch]:
    out: list[Mismatch] = []
    for key in ("slot", "rarity", "hero"):
        if expected.get(key) != actual.get(key):
            out.append(Mismatch(key, expected.get(key), actual.get(key)))
    for key in ("level", "rating"):
        if expected.get(key) != actual.get(key):
            out.append(Mismatch(key, expected.get(key), actual.get(key)))
    if not _name_matches(expected.get("name"), actual.get("name")):
        out.append(Mismatch("name", expected.get("name"), actual.get("name")))
    out.extend(
        _compare_base_effects(
            list(expected.get("base_effects", [])),  # type: ignore[arg-type]
            list(actual.get("base_effects", [])),  # type: ignore[arg-type]
        )
    )
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
        "hero": parsed.hero,
        "level": parsed.level,
        "rating": parsed.rating,
        "base_effects": [
            {"name": b.name, "value": b.value} for b in parsed.base_effects
        ],
        "extended_effects": [
            {"stat_id": e.stat_id, "tier": e.tier, "value": e.value}
            for e in parsed.extended_effects
        ],
    }


def _stat_catalog() -> list[str]:
    from app.data_loader import load_game_data, stat_catalog

    return stat_catalog(load_game_data())


def _is_ready(fixture_dir: Path) -> bool:
    """A fixture is "ready" only when both files are present.

    Folders with just `expected.json` (transcribed but no capture yet) or just
    `screenshot.png` (captured but no ground truth yet) are still in flight —
    the test gate skips them rather than failing, so the user can land
    transcriptions and captures in any order.
    """
    return (fixture_dir / "screenshot.png").is_file() and (
        fixture_dir / "expected.json"
    ).is_file()


@pytest.fixture(scope="module")
def fixtures_present() -> list[Path]:
    ready = [fx for fx in _fixtures() if _is_ready(fx)]
    if not ready:
        pytest.skip(
            "No fully-populated OCR fixtures (need both screenshot.png and "
            "expected.json). Capture per PHASE2_OCR_INPUTS.md to enable this gate."
        )
    return ready


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
    """Each fixture must parse with no field mismatches.

    Folders missing either `screenshot.png` or `expected.json` are skipped
    (not failed) so the suite stays green while batches of fixtures land
    incrementally — the user transcribes ground truth and captures the
    matching screenshot in separate sessions.
    """
    pytest.importorskip("pytesseract")  # skip per-test if tesseract isn't installed

    screenshot = fixture_dir / "screenshot.png"
    expected_path = fixture_dir / "expected.json"
    if not screenshot.is_file() or not expected_path.is_file():
        missing = [
            p.name for p in (screenshot, expected_path) if not p.is_file()
        ]
        pytest.skip(f"{fixture_dir.name} not ready (missing {', '.join(missing)})")

    from app.ocr.pipeline import parse_gear_screenshot

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
