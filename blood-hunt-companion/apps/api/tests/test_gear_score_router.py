"""POST /api/gear/score endpoint integration tests.

Uses the real seed catalogs (`gear_stats.seed.json` + `heroes.seed.json`)
since the endpoint calls `data_loader.load_game_data()` directly, mirroring
how `routers/simulation.py` works. Tests assert on response shape + status
codes, not on exact score numerics (those live in `tests/services/test_roll_score.py`
where a synthetic GameData fixture nails them).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app


def _legendary_gear(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "slot": "armor",
        "rarity": "legendary",
        "level": 60,
        "rating": 7000,
        "base_effects": [{"name": "Health", "value": 2419}],
        "extended_effects": [
            {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
            {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
            {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
            {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
            {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
        ],
    }
    body.update(overrides)
    return body


def _payload(
    gear: dict[str, Any] | None = None,
    build: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gear": gear if gear is not None else _legendary_gear(),
        "build": build if build is not None else {},
    }


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------
def test_score_minimal_legendary_returns_200_with_parseable_result() -> None:
    with TestClient(app) as client:
        r = client.post("/api/gear/score", json=_payload())
    assert r.status_code == 200
    body = r.json()
    # Shape sanity — every required field present.
    for key in (
        "score", "threshold", "forge_action", "percentile",
        "breakdown", "stat_weights_used", "uncatalogued_stats", "explanation",
    ):
        assert key in body
    # 5 effects in → 5 breakdown rows out.
    assert len(body["breakdown"]) == 5
    # Default build (no hero) → {Total Output Boost: 1.0}
    assert body["stat_weights_used"] == {"Total Output Boost": 1.0}
    # Perfect roll on the only weighted stat → 100/100 leaderboard_grade.
    assert body["score"] == 100.0
    assert body["threshold"] == "leaderboard_grade"
    assert body["forge_action"] == "lock"


def test_score_with_hero_id_only_derives_weights() -> None:
    """SG burst_acorn + squirrel_friends: TOB sum=2, Precision Damage=1."""
    with TestClient(app) as client:
        r = client.post(
            "/api/gear/score",
            json=_payload(build={"hero_id": "squirrel_girl"}),
        )
    assert r.status_code == 200
    weights = r.json()["stat_weights_used"]
    assert "Total Output Boost" in weights
    assert "Precision Damage" in weights
    # Sum to ~1.0 after normalization.
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_score_with_hero_and_ability_uses_just_that_ability() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/gear/score",
            json=_payload(build={
                "hero_id": "moon_knight",
                "ability_id": "ankh",
            }),
        )
    assert r.status_code == 200
    weights = r.json()["stat_weights_used"]
    # ankh scales on Total Output Boost + Boss Damage; both at 0.5 after norm.
    assert set(weights.keys()) == {"Total Output Boost", "Boss Damage"}


def test_score_explicit_stat_weights_echoed_in_response() -> None:
    explicit = {"Total Output Boost": 2.0, "Boss Damage": 0.5}
    with TestClient(app) as client:
        r = client.post(
            "/api/gear/score",
            json=_payload(build={
                "hero_id": "moon_knight",  # explicit overrides hero
                "stat_weights": explicit,
            }),
        )
    assert r.status_code == 200
    assert r.json()["stat_weights_used"] == explicit


# ---------------------------------------------------------------------------
# 422 error paths
# ---------------------------------------------------------------------------
def test_score_unknown_hero_id_returns_422() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/gear/score",
            json=_payload(build={"hero_id": "ghost_rider"}),
        )
    assert r.status_code == 422
    assert "ghost_rider" in r.json()["detail"]


def test_score_unknown_ability_for_valid_hero_returns_422() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/gear/score",
            json=_payload(build={
                "hero_id": "moon_knight",
                "ability_id": "imaginary_move",
            }),
        )
    assert r.status_code == 422
    assert "imaginary_move" in r.json()["detail"]


def test_score_legendary_with_no_extended_effects_returns_422() -> None:
    """Empty extended_effects on a legendary is a parsing artefact, not a roll."""
    with TestClient(app) as client:
        r = client.post(
            "/api/gear/score",
            json=_payload(gear=_legendary_gear(extended_effects=[])),
        )
    assert r.status_code == 422
    assert "extended effect" in r.json()["detail"].lower()


def test_score_normal_rarity_with_no_effects_is_legitimate() -> None:
    """Normal-rarity has 0 slots by design — must NOT 422."""
    normal = {
        "slot": "armor",
        "rarity": "normal",
        "level": 1,
        "rating": 100,
        "base_effects": [{"name": "Health", "value": 100}],
        "extended_effects": [],
    }
    with TestClient(app) as client:
        r = client.post("/api/gear/score", json=_payload(gear=normal))
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 0.0
    assert body["threshold"] == "trash"
    assert body["forge_action"] == "smelt"


# ---------------------------------------------------------------------------
# Uncatalogued-stats surface check
# ---------------------------------------------------------------------------
def test_score_surfaces_uncatalogued_stat_names() -> None:
    """An OCR'd stat name not in `gear_stats.seed.json` lands in `uncatalogued_stats`."""
    gear = _legendary_gear(extended_effects=[
        {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
        {"stat_id": "Some Future Stat From A Patch", "tier": "S", "value": 100},
        {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
        {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
        {"stat_id": "Total Output Boost", "tier": "S", "value": 8500},
    ])
    with TestClient(app) as client:
        r = client.post("/api/gear/score", json=_payload(gear=gear))
    assert r.status_code == 200
    body = r.json()
    assert "Some Future Stat From A Patch" in body["uncatalogued_stats"]
    # The uncatalogued row still appears in breakdown but with in_catalog=False
    mystery = next(
        b for b in body["breakdown"]
        if b["stat_id"] == "Some Future Stat From A Patch"
    )
    assert mystery["in_catalog"] is False
    assert mystery["normalized_contribution"] == 0.0


# ---------------------------------------------------------------------------
# Percentile placeholder shape
# ---------------------------------------------------------------------------
def test_score_percentile_is_within_valid_range() -> None:
    with TestClient(app) as client:
        r = client.post("/api/gear/score", json=_payload())
    body = r.json()
    assert 0.0 <= body["percentile"] <= 100.0
