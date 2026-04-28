from __future__ import annotations

from app.ocr.fuzzy import normalize_stat

CATALOG = [
    "Total Output Boost",
    "Total Damage Bonus",
    "Precision Damage",
    "Precision Rate",
    "Crit Damage",
    "Boss Damage",
    "Close-Range Damage",
    "Rune Cooldown Reduction",
    "HP",
]


def test_exact_match() -> None:
    name, score = normalize_stat("Precision Damage", CATALOG)
    assert name == "Precision Damage"
    assert score >= 99


def test_typo_one_char() -> None:
    name, score = normalize_stat("Precision Oamage", CATALOG)
    assert name == "Precision Damage"
    assert score >= 90


def test_typo_underscore() -> None:
    name, score = normalize_stat("Tota1 Output Boost", CATALOG)
    assert name == "Total Output Boost"
    assert score >= 80


def test_low_confidence_returns_raw() -> None:
    name, score = normalize_stat("ZZZZ Garbage", CATALOG, threshold=75.0)
    # Very low score → return raw input untouched.
    assert name == "ZZZZ Garbage"
    assert score < 75


def test_empty_inputs() -> None:
    assert normalize_stat("", CATALOG) == ("", 0.0)
    assert normalize_stat("Precision Damage", []) == ("Precision Damage", 0.0)
