"""Fuzzy stat-name normalization against the datamined catalog.

Tesseract output for "Precision Damage" frequently lands as "Precision Oamage" or
"Precis1on Damage". The catalog from `data/game/gear_stats.json` is small (a few
dozen entries), so a rapidfuzz WRatio search is fast and accurate.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

# Score below this is treated as "no match" (caller surfaces to the user).
DEFAULT_THRESHOLD = 75.0


def normalize_stat(
    raw: str,
    catalog: list[str],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[str, float]:
    """Match `raw` against `catalog`. Returns (best_match, score_0_to_100).

    If the score is below `threshold`, returns (raw, score) — the caller decides
    whether to surface the low-confidence match for human review.
    """
    if not raw or not catalog:
        return raw, 0.0
    result = process.extractOne(raw, catalog, scorer=fuzz.WRatio)
    if result is None:
        return raw, 0.0
    match, score, _ = result
    if score < threshold:
        return raw, float(score)
    return match, float(score)


def normalize_many(
    raws: list[str],
    catalog: list[str],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[tuple[str, float]]:
    return [normalize_stat(r, catalog, threshold=threshold) for r in raws]
