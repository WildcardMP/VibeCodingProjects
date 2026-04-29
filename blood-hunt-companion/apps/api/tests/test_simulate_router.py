"""POST /api/simulate endpoint tests.

Uses the bundled `*.seed.json` catalogs (Squirrel Girl + Moon Knight) as
the game data source — `data_loader.load_game_data()` falls back to seed
when no FModel exports are present.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app


def _payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "hero_id": "moon_knight",
        "gear": [],
        "trait_alloc": {},
        "arcana_ids": [],
        "target": {
            "is_boss": False,
            "is_close_range": False,
            "is_healthy": False,
            "vulnerability": 0.0,
        },
    }
    body.update(overrides)
    return body


def test_simulate_returns_per_ability_results() -> None:
    """A bare hero (no gear, no traits, no arcana) returns base-damage results."""
    with TestClient(app) as client:
        r = client.post("/api/simulate", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["hero_id"] == "moon_knight"
    assert len(body["per_ability"]) >= 1
    # Moon Knight has Ankh (base 100) + Moon Blade (base 90) per the seed.
    ability_ids = {a["ability_id"] for a in body["per_ability"]}
    assert "ankh" in ability_ids
    # Empty build → expected_hit equals base_damage for every ability
    for a in body["per_ability"]:
        assert a["expected_hit"] == a["base_damage"]


def test_simulate_with_legendary_armor_boosts_dps() -> None:
    """A single piece with +8300% Total Output Boost should ~84x every ability."""
    armor = {
        "slot": "armor",
        "rarity": "legendary",
        "level": 60,
        "rating": 7000,
        "base_effects": [{"name": "Health", "value": 2419}],
        "extended_effects": [
            {"stat_id": "Total Output Boost", "tier": "S", "value": 8300}
        ],
    }
    with TestClient(app) as client:
        baseline = client.post("/api/simulate", json=_payload()).json()
        boosted = client.post("/api/simulate", json=_payload(gear=[armor])).json()

    base_ankh = next(a for a in baseline["per_ability"] if a["ability_id"] == "ankh")
    boost_ankh = next(a for a in boosted["per_ability"] if a["ability_id"] == "ankh")
    # +8300% = +83 multiplier → 84x baseline
    assert boost_ankh["expected_hit"] == base_ankh["expected_hit"] * 84


def test_simulate_unknown_hero_returns_422() -> None:
    with TestClient(app) as client:
        r = client.post("/api/simulate", json=_payload(hero_id="ghost_rider"))
    assert r.status_code == 422
    assert "ghost_rider" in r.json()["detail"]


def test_simulate_target_context_situational_bonus() -> None:
    """`is_boss=True` activates the boss_damage stat from gear."""
    weapon = {
        "slot": "weapon",
        "rarity": "legendary",
        "level": 60,
        "rating": 7000,
        "base_effects": [{"name": "Precision Damage", "value": 1000}],
        "extended_effects": [
            {"stat_id": "Boss Damage", "tier": "S", "value": 1000}  # +1000% vs bosses
        ],
    }
    with TestClient(app) as client:
        no_boss = client.post(
            "/api/simulate", json=_payload(gear=[weapon])
        ).json()
        boss = client.post(
            "/api/simulate",
            json=_payload(gear=[weapon], target={"is_boss": True}),
        ).json()
    # Boss bonus only fires when target.is_boss=True
    no_boss_ankh = next(a for a in no_boss["per_ability"] if a["ability_id"] == "ankh")
    boss_ankh = next(a for a in boss["per_ability"] if a["ability_id"] == "ankh")
    assert boss_ankh["expected_hit"] > no_boss_ankh["expected_hit"]


def test_simulate_returns_stat_totals_breakdown() -> None:
    """The response echoes back the aggregated StatTotals so the frontend can
    render a stat-pool view without re-doing the math."""
    armor = {
        "slot": "armor",
        "rarity": "legendary",
        "level": 60,
        "rating": 7000,
        "base_effects": [
            {"name": "Health", "value": 2419},
            {"name": "Armor Value", "value": 438},
        ],
        "extended_effects": [],
    }
    with TestClient(app) as client:
        r = client.post("/api/simulate", json=_payload(gear=[armor]))
    body = r.json()
    assert body["stat_totals"]["health"] == 2419
    assert body["stat_totals"]["armor_value"] == 438


def test_simulate_with_arcana_scroll_of_conquest() -> None:
    """Bundled Scroll of Conquest contributes to total_damage_bonus."""
    with TestClient(app) as client:
        baseline = client.post("/api/simulate", json=_payload()).json()
        with_arcana = client.post(
            "/api/simulate",
            json=_payload(arcana_ids=["scroll_of_conquest"]),
        ).json()
    # arcana.seed.json: Scroll of Conquest → Total Damage Bonus +0.30 (multiplicative)
    # Aggregator stores the value as-is; formula divides by 100, so this is +0.003 — tiny.
    # The test just confirms the endpoint accepts the id and the totals reflect it.
    assert with_arcana["stat_totals"]["total_damage_bonus"] > baseline["stat_totals"]["total_damage_bonus"]
