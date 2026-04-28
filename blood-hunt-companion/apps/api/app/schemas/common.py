"""Shared primitive types referenced by every other schema module.

Keep this file dependency-free — it must not import from peer schema modules to avoid
circular imports.
"""

from __future__ import annotations

from typing import Literal

# Five rarities, mirroring RESEARCH.md §3.1.
Rarity = Literal["common", "uncommon", "rare", "epic", "legendary"]

# Extended-effect tier letters from RESEARCH.md §3.2.
TierLetter = Literal["S", "A", "B", "C", "D"]

# Slot identifiers per RESEARCH.md §3: four slots per hero with independent inventories.
GearSlot = Literal["weapon", "armor", "accessory", "exclusive"]

# StatId is intentionally `str` (not a Literal) because the canonical catalog lives
# in datamined `gear_stats.json` — hard-coding a Literal would force a release every
# time NetEase ships a new stat. Validation happens at runtime via the catalog loader.
StatId = str
