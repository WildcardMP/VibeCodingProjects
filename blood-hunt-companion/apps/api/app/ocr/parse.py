"""Pure-Python regex helpers for OCR post-processing.

Zero external dependencies — these are unit-testable without Tesseract or OpenCV.
"""

from __future__ import annotations

import re
from typing import Literal

TierLetter = Literal["S", "A", "B", "C", "D"]

# Match "+8300%", "-12.5%", "1,250%", optionally surrounded by whitespace.
# Tolerates Tesseract substituting "O" for "0" by allowing a stray O after digits;
# we replace before re-parsing.
_PERCENT_RE = re.compile(r"([+-]?\d{1,6}(?:[.,]\d+)?)\s*%")
_LEVEL_RE = re.compile(r"L(?:e?v(?:el)?)?\s*\.?\s*(\d{1,3})", re.IGNORECASE)
_RAW_NUMBER_RE = re.compile(r"([+-]?\d{1,6}(?:[.,]\d+)?)")
_RATING_RE = re.compile(r"\b(\d{3,5})\b")
# Tier brackets: in-game uses full-width 【 】 (U+3010 / U+3011); some screenshots
# may render as ASCII [ ]. Strip both before matching the letter.
_TIER_BRACKET_RE = re.compile(r"[【】\[\]\(\)<>{}|/\\\s.,:;_\-]+")

# Common Tesseract confusions for digits in this UI font.
# Note: deliberately exclude `l` → `1` because it would corrupt "lv" / "level".
# Excluded `I` → `1` because it would corrupt the start of names. We only fix `O`/`o`.
_DIGIT_FIXUPS = str.maketrans({"O": "0", "o": "0"})


def _fix_digits_only(s: str) -> str:
    """Apply digit fixups *only* in tokens that are clearly numeric — i.e. tokens
    where digits already dominate the alphanumeric content. This avoids turning
    "Precision" into "Prec1s10n" while still rescuing "830O%" → "8300%".
    """
    out = []
    for token in re.split(r"(\s+)", s):
        if not token.strip():
            out.append(token)
            continue
        # Count alphanumerics only; ignore +/-/./%/, etc.
        alnum = [c for c in token if c.isalnum()]
        if not alnum:
            out.append(token)
            continue
        digits = sum(c.isdigit() for c in alnum)
        # If at least one digit and ≥50% of alphanumerics are digits, it's a numeric token.
        if digits >= 1 and digits * 2 >= len(alnum):
            out.append(token.translate(_DIGIT_FIXUPS))
        else:
            out.append(token)
    return "".join(out)


def parse_percent(raw: str) -> float | None:
    """Extract the first percentage value from `raw`. Returns the *unitless number*
    (e.g. "+8300%" → 8300.0). Returns None if no percentage found.
    """
    if not raw:
        return None
    cleaned = _fix_digits_only(raw)
    m = _PERCENT_RE.search(cleaned)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_level(raw: str) -> int | None:
    """Extract a level integer from text like "Lv 60", "lv.55", "L60"."""
    if not raw:
        return None
    cleaned = _fix_digits_only(raw)
    m = _LEVEL_RE.search(cleaned)
    if m:
        try:
            v = int(m.group(1))
        except ValueError:
            return None
        return v if 1 <= v <= 60 else None
    # Fallback: a bare 1–60 number alone in the field.
    m2 = _RAW_NUMBER_RE.search(cleaned)
    if not m2:
        return None
    try:
        v = int(float(m2.group(1).replace(",", ".")))
    except ValueError:
        return None
    return v if 1 <= v <= 60 else None


def parse_rating(raw: str) -> int | None:
    """Extract the tooltip overall rating, e.g. "7086" → 7086.

    The rating appears as a 3- to 5-digit integer near the top of the card,
    sometimes with stray punctuation or color-code artefacts. We pick the first
    plausible integer.
    """
    if not raw:
        return None
    cleaned = _fix_digits_only(raw)
    m = _RATING_RE.search(cleaned)
    if m is None:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_tier_letter(raw: str) -> TierLetter | None:
    """Pick a single S/A/B/C/D letter from arbitrary OCR output.

    Handles the in-game full-width brackets `【S】` (U+3010 / U+3011) and ASCII
    `[S]` indifferently — both bracket families and adjacent punctuation are
    stripped before scanning for the first valid letter. Returns None when no
    candidate letter survives the strip.
    """
    if not raw:
        return None
    cleaned = _TIER_BRACKET_RE.sub("", raw).upper()
    for ch in cleaned:
        if ch in {"S", "A", "B", "C", "D"}:
            return ch  # type: ignore[return-value]
    return None


def extract_stat_name(raw: str) -> str:
    """Strip numeric values and trailing punctuation, leaving just the stat-name text.

    Tesseract typically outputs "Precision Damage +8300%" for an extended-effect row;
    we want "Precision Damage" so the fuzzy matcher can find it in the catalog.
    """
    if not raw:
        return ""
    # Drop the percent value and the number that precedes it.
    s = _PERCENT_RE.sub("", raw)
    # Drop any remaining trailing numbers.
    s = _RAW_NUMBER_RE.sub("", s)
    # Collapse whitespace and strip stray punctuation.
    s = re.sub(r"[+\-:.,]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
