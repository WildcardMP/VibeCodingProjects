"""Pure-Python OCR helpers — no Tesseract / OpenCV needed."""

from __future__ import annotations

import pytest

from app.ocr.parse import (
    extract_stat_name,
    parse_level,
    parse_percent,
    parse_rating,
    parse_tier_letter,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+8300%", 8300.0),
        ("Precision Damage +8300%", 8300.0),
        ("-12.5%", -12.5),
        ("1,250%", 1.250),  # comma-as-decimal locale variant
        ("Total Output Boost: 4,250%", 4.250),
        ("nothing here", None),
        ("", None),
        # Tesseract digit confusion: "830O%" (capital O for zero) → fixup → 8300
        ("830O%", 8300.0),
    ],
)
def test_parse_percent(raw: str, expected: float | None) -> None:
    assert parse_percent(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Lv 60", 60),
        ("lv.55", 55),
        ("L60", 60),
        ("Level 60", 60),
        ("Lv 0", None),   # out of range
        ("Lv 61", None),  # > 60 hero/gear cap
        ("Lv 99", None),
        ("", None),
    ],
)
def test_parse_level(raw: str, expected: int | None) -> None:
    assert parse_level(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Precision Damage +8300%", "Precision Damage"),
        ("Total Output Boost: 4250%", "Total Output Boost"),
        ("Boss Damage", "Boss Damage"),
        ("", ""),
    ],
)
def test_extract_stat_name(raw: str, expected: str) -> None:
    assert extract_stat_name(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("7086", 7086),
        ("Rating 7086", 7086),
        ("  4521  ", 4521),
        ("832", 832),  # 3-digit minimum still parses
        ("99", None),  # 2 digits — too short, looks like a level/level-frag
        ("nothing here", None),
        ("", None),
        # Tesseract digit fixup: "70O0" → 7000 then matches.
        ("70O0", 7000),
    ],
)
def test_parse_rating(raw: str, expected: int | None) -> None:
    assert parse_rating(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Bare letter — already matches.
        ("S", "S"),
        ("D", "D"),
        # In-game full-width brackets (U+3010 / U+3011).
        ("【S】", "S"),
        ("【A】", "A"),
        ("【B】", "B"),
        ("【C】", "C"),
        ("【D】", "D"),
        # ASCII brackets — fallback when the OCR pass strips full-width chars.
        ("[S]", "S"),
        ("[A]", "A"),
        # Surrounding noise the row-OCR sometimes captures.
        (" S. ", "S"),
        ("(S)", "S"),
        ("S/", "S"),
        ("|B|", "B"),
        # Lowercase tolerated.
        ("【s】", "S"),
        # Empty / unrecognized.
        ("", None),
        ("   ", None),
        ("Z", None),
        ("【】", None),
    ],
)
def test_parse_tier_letter(raw: str, expected: str | None) -> None:
    assert parse_tier_letter(raw) == expected
