"""Read canonical game data JSON files into typed Python objects.

Lookup is by id with cached lists so the FastAPI app reloads data only when files
change on disk (mtime tracking).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import settings
from .schemas.arcana import ArcanaScroll
from .schemas.hero import Hero
from .schemas.trait import TraitNode


@dataclass
class GameData:
    heroes: list[Hero]
    traits: list[TraitNode]
    gear_stats: list[dict[str, Any]]  # raw dicts; the catalog list is what OCR needs
    arcana: list[ArcanaScroll]
    forge_rules: dict[str, Any]
    version: dict[str, Any]
    loaded_at: datetime
    sources: dict[str, Path]  # filename -> path used


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _resolve(name: str, dir: Path) -> Path:
    """Prefer real translated data, fall back to bundled `*.seed.json`."""
    real = dir / name
    if real.exists():
        return real
    seed = dir / name.replace(".json", ".seed.json")
    return seed


def load_game_data() -> GameData:
    cfg = settings()
    d = cfg.game_data_dir

    heroes_p = _resolve("heroes.json", d)
    traits_p = _resolve("traits.json", d)
    stats_p = _resolve("gear_stats.json", d)
    arcana_p = _resolve("arcana.json", d)
    forge_p = _resolve("forge_rules.json", d)
    version_p = d / "version.json"

    heroes_raw = _read_json(heroes_p) or []
    traits_raw = _read_json(traits_p) or []
    stats_raw = _read_json(stats_p) or []
    arcana_raw = _read_json(arcana_p) or []
    forge_raw = _read_json(forge_p) or {}
    version_raw = _read_json(version_p) or {"extracted_at": None, "raw_files_present": []}

    return GameData(
        heroes=[Hero.model_validate(x) for x in heroes_raw],
        traits=[TraitNode.model_validate(x) for x in traits_raw],
        gear_stats=stats_raw,
        arcana=[ArcanaScroll.model_validate(x) for x in arcana_raw],
        forge_rules=forge_raw,
        version=version_raw,
        loaded_at=datetime.now(),
        sources={
            "heroes": heroes_p,
            "traits": traits_p,
            "gear_stats": stats_p,
            "arcana": arcana_p,
            "forge_rules": forge_p,
            "version": version_p,
        },
    )


def stat_catalog(data: GameData) -> list[str]:
    """Display names of all stats — used by the OCR fuzzy matcher."""
    return [s.get("display_name") or s.get("stat_id") or "" for s in data.gear_stats if s]
