#!/usr/bin/env python3
"""Translate raw FModel exports → canonical JSON consumed by the app.

Workflow (DATA_PIPELINE.md §1.5–1.6):
    1. Open FModel, point it at the Marvel Rivals Paks folder, load the latest
       AES key + mappings.
    2. For each `DT_*` listed in DATA_PIPELINE.md §1.4, "Save Properties (.json)".
    3. Drop the resulting files into `data/game/_raw/` using the names below.
    4. Run this script (or `make extract`).

The translator is intentionally defensive — UE field names drift between patches
and FModel sometimes wraps tables in extra layers. Each translator walks the raw
structure with `_iter_rows`, picks the first key that matches a list of likely
candidates via `_pick`, and skips rows that look unparseable.

If a patch breaks a translator, the fix is almost always either (a) a renamed
field landing in the candidate list, or (b) a new wrapping layer landing in
`_iter_rows`. Don't rewrite the world.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution — works whether invoked from repo root or anywhere else.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "game" / "_raw"
OUT_DIR = REPO_ROOT / "data" / "game"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing FModel export: {path.relative_to(REPO_ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_rows(raw: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (row_name, row_dict) pairs from a raw FModel export.

    FModel "Save Properties" output is typically a list with one element whose
    `Rows` key is a dict {row_name: properties}. We tolerate three shapes:
        * `{"Rows": {...}}`
        * `[{"Rows": {...}}]`
        * `[{"Rows": {...}}, ...]` (multi-table dumps)
    """
    if isinstance(raw, list):
        for entry in raw:
            yield from _iter_rows(entry)
        return
    if not isinstance(raw, dict):
        return
    rows = raw.get("Rows") or raw.get("rows")
    if isinstance(rows, dict):
        for name, props in rows.items():
            if isinstance(props, dict):
                yield name, props


def _pick(row: dict[str, Any], *candidates: str, default: Any = None) -> Any:
    """Return the first present key from `candidates` in `row`, else `default`.

    Case-insensitive. Tolerates `Properties` or `Properties.<key>` wrappers that
    FModel sometimes emits.
    """
    haystack = dict(row)
    if isinstance(row.get("Properties"), dict):
        # Merge nested Properties (don't overwrite explicit top-level keys)
        for k, v in row["Properties"].items():
            haystack.setdefault(k, v)

    lower_lookup = {k.lower(): v for k, v in haystack.items()}
    for cand in candidates:
        if cand in haystack:
            return haystack[cand]
        if cand.lower() in lower_lookup:
            return lower_lookup[cand.lower()]
    return default


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return float(v)
        return float(v)
    except (TypeError, ValueError):
        return default


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def _coerce_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, dict):
        # FStructProperty / FName often look like {"AssetPathName": "...", "SubPathString": "..."}
        # or {"Name": "..."}. Pick the most useful field.
        for key in ("Name", "TagName", "RowName", "AssetPathName"):
            if key in v:
                return _coerce_str(v[key], default)
        return default
    return str(v)


# ---------------------------------------------------------------------------
# Per-table translators
# ---------------------------------------------------------------------------
def translate_heroes(raw: Any) -> list[dict[str, Any]]:
    """`DT_HeroAbilities` rows → grouped heroes with abilities.

    Expected per-row fields (any of the candidates is fine):
        HeroId / Hero / OwnerHero
        AbilityId / Ability / Id (row_name as fallback)
        DisplayName / Name
        BaseDamage / Damage / BaseValue
        Cooldown / CD
        Scaling: list of {StatId, Coefficient}
        Tags: list[str]
        CanPrecision, CanCrit: bool
    """
    by_hero: dict[str, dict[str, Any]] = {}
    for row_name, row in _iter_rows(raw):
        hero_id = _coerce_str(_pick(row, "HeroId", "Hero", "OwnerHero"))
        if not hero_id:
            continue
        ability = {
            "id": _coerce_str(_pick(row, "AbilityId", "Ability", "Id"), default=row_name),
            "name": _coerce_str(_pick(row, "DisplayName", "Name"), default=row_name),
            "tags": list(_pick(row, "Tags", default=[]) or []),
            "base_damage": _coerce_float(_pick(row, "BaseDamage", "Damage", "BaseValue")),
            "scaling": _translate_scaling(_pick(row, "Scaling", default=[]) or []),
            "cooldown": _coerce_float(_pick(row, "Cooldown", "CD")),
            "can_precision": bool(_pick(row, "CanPrecision", default=True)),
            "can_crit": bool(_pick(row, "CanCrit", default=True)),
        }
        hero = by_hero.setdefault(
            hero_id,
            {
                "id": hero_id,
                "display_name": _coerce_str(
                    _pick(row, "HeroDisplayName", "HeroName"), default=hero_id
                ),
                "abilities": [],
            },
        )
        hero["abilities"].append(ability)
    return sorted(by_hero.values(), key=lambda h: h["id"])


def _translate_scaling(rows: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "stat": _coerce_str(_pick(r, "StatId", "Stat")),
                "coefficient": _coerce_float(_pick(r, "Coefficient", "Coef", "Value")),
            }
        )
    return [s for s in out if s["stat"]]


def translate_traits(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row_name, row in _iter_rows(raw):
        node = {
            "hero_id": _coerce_str(_pick(row, "HeroId", "Hero", "OwnerHero")),
            "tree": _coerce_str(_pick(row, "Tree", "Branch"), default="shared"),
            "node_id": _coerce_str(_pick(row, "NodeId", "Id"), default=row_name),
            "display_name": _coerce_str(_pick(row, "DisplayName", "Name"), default=row_name),
            "max_points": _coerce_int(_pick(row, "MaxPoints", "MaxRanks"), default=1),
            "effects": _translate_trait_effects(_pick(row, "Effects", default=[]) or []),
            "prerequisites": [
                _coerce_str(p) for p in (_pick(row, "Prerequisites", "Requires", default=[]) or [])
            ],
        }
        if node["hero_id"] and node["node_id"]:
            out.append(node)
    return out


def _translate_trait_effects(rows: Iterable[Any]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "stat": _coerce_str(_pick(r, "StatId", "Stat")),
                "per_point": _coerce_float(_pick(r, "PerPoint", "Value", "PerRank")),
                "multiplicative": bool(_pick(r, "Multiplicative", default=False)),
            }
        )
    return [e for e in out if e["stat"]]


def translate_gear_stats(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row_name, row in _iter_rows(raw):
        tiers_raw = _pick(row, "Tiers", "TierRanges", default=[]) or []
        tiers = []
        for t in tiers_raw:
            if not isinstance(t, dict):
                continue
            tier_letter = _coerce_str(_pick(t, "Tier", "TierLetter"))
            if tier_letter not in {"S", "A", "B", "C", "D"}:
                continue
            tiers.append(
                {
                    "tier": tier_letter,
                    "min": _coerce_float(_pick(t, "Min", "MinValue")),
                    "max": _coerce_float(_pick(t, "Max", "MaxValue")),
                }
            )
        out.append(
            {
                "stat_id": _coerce_str(_pick(row, "StatId", "Id"), default=row_name),
                "display_name": _coerce_str(_pick(row, "DisplayName", "Name"), default=row_name),
                "applies_to_slots": [
                    _coerce_str(s)
                    for s in (_pick(row, "AppliesToSlots", "Slots", default=[]) or [])
                ],
                "tiers": tiers,
            }
        )
    return [s for s in out if s["stat_id"]]


def translate_arcana(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row_name, row in _iter_rows(raw):
        effects_raw = _pick(row, "Effects", default=[]) or []
        effects = []
        for e in effects_raw:
            if not isinstance(e, dict):
                continue
            effects.append(
                {
                    "stat": _coerce_str(_pick(e, "StatId", "Stat")),
                    "value": _coerce_float(_pick(e, "Value", "Amount")),
                    "multiplicative": bool(_pick(e, "Multiplicative", default=True)),
                }
            )
        out.append(
            {
                "id": _coerce_str(_pick(row, "Id", "ScrollId"), default=row_name),
                "name": _coerce_str(_pick(row, "Name", "DisplayName"), default=row_name),
                "tier": _coerce_str(_pick(row, "Tier", "Rarity"), default="normal"),
                "effects": [e for e in effects if e["stat"]],
                "description": _coerce_str(_pick(row, "Description", "Desc")),
            }
        )
    return out


def translate_forge_rules(raw: Any) -> dict[str, Any]:
    """Forge rules are a single small table — return the first row's properties verbatim."""
    rules: dict[str, Any] = {}
    for _, row in _iter_rows(raw):
        for key in ("LegendaryChance", "ShardCostPerRoll", "StackOf10Discount"):
            if key in row or key.lower() in {k.lower() for k in row}:
                rules[key] = _pick(row, key)
        break  # only first row
    return rules


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
TABLES: list[tuple[str, str, Any]] = [
    # (raw filename, output filename, translator)
    ("DT_HeroAbilities.json", "heroes.json", translate_heroes),
    ("DT_HeroTraits.json", "traits.json", translate_traits),
    ("DT_GearStats.json", "gear_stats.json", translate_gear_stats),
    ("DT_ArcanaScrolls.json", "arcana.json", translate_arcana),
    ("DT_ForgeRules.json", "forge_rules.json", translate_forge_rules),
]


def run(*, raw_dir: Path = RAW_DIR, out_dir: Path = OUT_DIR, strict: bool = False) -> int:
    """Translate every raw export. Returns exit code (0 = success)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    for raw_name, out_name, translator in TABLES:
        raw_path = raw_dir / raw_name
        out_path = out_dir / out_name
        if not raw_path.exists():
            msg = f"  ⚠ skipping {raw_name} — drop the FModel export into {raw_path}"
            print(msg)
            if strict:
                errors.append(msg)
            continue
        try:
            raw = _read_json(raw_path)
            translated = translator(raw)
            out_path.write_text(json.dumps(translated, indent=2, ensure_ascii=False), "utf-8")
            count = len(translated) if isinstance(translated, list) else 1
            print(f"  ✓ {raw_name} → {out_name} ({count} rows)")
        except Exception as exc:  # noqa: BLE001 — we want to keep going on per-table errors
            msg = f"  ✗ {raw_name} failed: {exc}"
            print(msg)
            errors.append(msg)

    # version stamp
    version_path = out_dir / "version.json"
    version_path.write_text(
        json.dumps(
            {
                "extracted_at": dt.datetime.now(dt.UTC).isoformat(),
                "translator_version": "0.1.0",
                "raw_files_present": sorted(p.name for p in raw_dir.glob("DT_*.json")),
            },
            indent=2,
        ),
        "utf-8",
    )

    if errors:
        print(f"\n{len(errors)} error(s):", *errors, sep="\n  ")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else "")
    parser.add_argument(
        "--raw-dir", type=Path, default=RAW_DIR, help="Directory of FModel .json exports."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=OUT_DIR, help="Where to write canonical JSON."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat missing raw files as errors."
    )
    args = parser.parse_args(argv)
    return run(raw_dir=args.raw_dir, out_dir=args.out_dir, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
