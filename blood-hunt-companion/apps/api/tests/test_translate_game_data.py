"""Translator tests using the bundled sample FModel exports."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

# tools/ is at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools import translate_game_data as tgd  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "raw_exports"


@pytest.fixture
def staged(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    out.mkdir()
    # Stage the .sample.json files under the names the translator expects.
    rename = {
        "DT_HeroAbilities.sample.json": "DT_HeroAbilities.json",
        "DT_GearStats.sample.json": "DT_GearStats.json",
        "DT_ArcanaScrolls.sample.json": "DT_ArcanaScrolls.json",
    }
    for sample_name, real_name in rename.items():
        shutil.copy(FIXTURES / sample_name, raw / real_name)
    return raw, out


def test_run_writes_translated_json(staged: tuple[Path, Path]) -> None:
    raw, out = staged
    rc = tgd.run(raw_dir=raw, out_dir=out, strict=False)
    assert rc == 0
    assert (out / "heroes.json").exists()
    assert (out / "gear_stats.json").exists()
    assert (out / "arcana.json").exists()
    assert (out / "version.json").exists()


def test_translate_heroes_groups_abilities(staged: tuple[Path, Path]) -> None:
    raw, out = staged
    tgd.run(raw_dir=raw, out_dir=out)
    data = json.loads((out / "heroes.json").read_text())
    ids = {h["id"] for h in data}
    assert {"squirrel_girl", "moon_knight"} <= ids
    sg = next(h for h in data if h["id"] == "squirrel_girl")
    assert sg["display_name"] == "Squirrel Girl"
    assert any(a["id"] == "burst_acorn" for a in sg["abilities"])
    burst = next(a for a in sg["abilities"] if a["id"] == "burst_acorn")
    assert burst["base_damage"] == 80.0
    assert burst["cooldown"] == 6.0
    assert {s["stat"] for s in burst["scaling"]} == {"Precision Damage", "Total Output Boost"}


def test_translate_gear_stats_keeps_tier_ranges(staged: tuple[Path, Path]) -> None:
    raw, out = staged
    tgd.run(raw_dir=raw, out_dir=out)
    data = json.loads((out / "gear_stats.json").read_text())
    pd = next(s for s in data if s["stat_id"] == "Precision Damage")
    tiers = {t["tier"]: t for t in pd["tiers"]}
    assert tiers["S"]["min"] == 4000
    assert tiers["S"]["max"] == 8500


def test_translate_arcana(staged: tuple[Path, Path]) -> None:
    raw, out = staged
    tgd.run(raw_dir=raw, out_dir=out)
    data = json.loads((out / "arcana.json").read_text())
    ids = {a["id"] for a in data}
    assert "scroll_of_conquest" in ids
    conquest = next(a for a in data if a["id"] == "scroll_of_conquest")
    assert conquest["tier"] == "legendary"
    assert conquest["effects"][0]["stat"] == "Total Damage Bonus"
    assert conquest["effects"][0]["value"] == 0.30


def test_missing_files_skip_gracefully(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    rc = tgd.run(raw_dir=raw, out_dir=out, strict=False)
    assert rc == 0  # missing files are warnings, not errors, in non-strict mode
    assert (out / "version.json").exists()
