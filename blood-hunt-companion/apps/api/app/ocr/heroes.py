"""Canonical hero roster used by OCR for the HERO field.

The list mirrors `data/game/heroes.seed.json` (the same six heroes shipped by
the game in Blood Hunt; see RESEARCH.md §2.1). It's hard-coded here so the OCR
pipeline can fuzzy-match a hero display name without booting the JSON loader —
hero names are stable across patches, so duplicating them once is cheaper than
threading the catalog through every call site.

If a future patch adds a hero, append the (slug, display_name) pair below and
add the same entry to `heroes.seed.json`.
"""

from __future__ import annotations

# (slug, display_name) — slug stays in `data/game/heroes.seed.json` and is what
# the rest of the codebase joins on; display_name is what OCR reads off the
# tooltip's HERO field.
_HEROES: tuple[tuple[str, str], ...] = (
    ("squirrel_girl", "Squirrel Girl"),
    ("moon_knight", "Moon Knight"),
    ("jeff_the_land_shark", "Jeff the Land Shark"),
    ("thor", "Thor"),
    ("the_punisher", "The Punisher"),
    ("blade", "Blade"),
)

HERO_DISPLAY_NAMES: tuple[str, ...] = tuple(name for _, name in _HEROES)
HERO_SLUGS: tuple[str, ...] = tuple(slug for slug, _ in _HEROES)

_BY_DISPLAY_NAME: dict[str, str] = {name: slug for slug, name in _HEROES}
_BY_SLUG: dict[str, str] = {slug: name for slug, name in _HEROES}


def slug_for_hero(display_name: str) -> str | None:
    """Return the canonical slug for a hero display name, or None if unknown."""
    return _BY_DISPLAY_NAME.get(display_name)


def display_name_for_slug(slug: str) -> str | None:
    """Return the canonical display name for a hero slug, or None if unknown."""
    return _BY_SLUG.get(slug)
