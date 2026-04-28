"""Gear CRUD endpoint tests.

A fresh tmp-file SQLite engine is built per test, the schema is created via
`Base.metadata.create_all` (alembic-equivalent — see test_alembic.py for the
real-migration path), and the FastAPI `get_session` dependency is overridden so
the in-memory app talks to the tmp DB instead of `data/personal.db`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.main import app
from app.models import Base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_sm(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, expire_on_commit=False, future=True)


@pytest.fixture
def client(db_sm: sessionmaker[Session]) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        s = db_sm()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _sample_payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "slot": "weapon",
        "hero": "Squirrel Girl",
        "hero_id": "squirrel_girl",
        "rarity": "legendary",
        "level": 60,
        "rating": 7086,
        "base_effects": [{"name": "Precision Damage", "value": 8300.0}],
        "extended_effects": [
            {
                "stat_id": "Total Output Boost",
                "tier": "S",
                "value": 4200.0,
                "raw_text": "Total Output Boost +4200%",
                "confidence": 0.92,
            }
        ],
        "overall_confidence": 0.85,
        "source_screenshot": "/tmp/x.png",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# POST /api/gear/manual
# ---------------------------------------------------------------------------
def test_create_gear_returns_201(client: TestClient) -> None:
    r = client.post("/api/gear/manual", json=_sample_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["id"] >= 1
    assert body["slot"] == "weapon"
    assert body["rarity"] == "legendary"
    assert len(body["extended_effects"]) == 1
    assert body["extended_effects"][0]["tier"] == "S"


def test_create_gear_rejects_bad_slot(client: TestClient) -> None:
    r = client.post("/api/gear/manual", json=_sample_payload(slot="chest"))
    assert r.status_code == 422


def test_create_gear_rejects_level_above_60(client: TestClient) -> None:
    r = client.post("/api/gear/manual", json=_sample_payload(level=70))
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/gear (list + filters)
# ---------------------------------------------------------------------------
def test_list_empty(client: TestClient) -> None:
    r = client.get("/api/gear")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_created_pieces(client: TestClient) -> None:
    client.post("/api/gear/manual", json=_sample_payload())
    client.post("/api/gear/manual", json=_sample_payload(hero_id="moon_knight"))
    r = client.get("/api/gear")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_filter_by_hero_id(client: TestClient) -> None:
    client.post("/api/gear/manual", json=_sample_payload(hero_id="squirrel_girl"))
    client.post("/api/gear/manual", json=_sample_payload(hero_id="moon_knight"))
    r = client.get("/api/gear", params={"hero_id": "moon_knight"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["hero_id"] == "moon_knight"


def test_filter_by_slot(client: TestClient) -> None:
    client.post("/api/gear/manual", json=_sample_payload(slot="weapon"))
    client.post(
        "/api/gear/manual",
        json=_sample_payload(
            slot="armor",
            base_effects=[{"name": "HP", "value": 1500.0}],
        ),
    )
    r = client.get("/api/gear", params={"slot": "armor"})
    assert len(r.json()) == 1
    assert r.json()[0]["slot"] == "armor"


def test_filter_by_rarity(client: TestClient) -> None:
    client.post("/api/gear/manual", json=_sample_payload(rarity="legendary"))
    client.post("/api/gear/manual", json=_sample_payload(rarity="epic"))
    r = client.get("/api/gear", params={"rarity": "epic"})
    assert len(r.json()) == 1


def test_filter_by_min_confidence(client: TestClient) -> None:
    client.post("/api/gear/manual", json=_sample_payload(overall_confidence=0.95))
    client.post("/api/gear/manual", json=_sample_payload(overall_confidence=0.4))
    r = client.get("/api/gear", params={"min_confidence": 0.8})
    body = r.json()
    assert len(body) == 1
    assert body[0]["overall_confidence"] == pytest.approx(0.95)


def test_filter_by_is_equipped(client: TestClient) -> None:
    p1 = client.post("/api/gear/manual", json=_sample_payload()).json()
    client.post("/api/gear/manual", json=_sample_payload())
    client.patch(f"/api/gear/{p1['id']}", json={"is_equipped": True})
    r = client.get("/api/gear", params={"is_equipped": True})
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == p1["id"]


def test_pagination_limit_and_offset(client: TestClient) -> None:
    for _ in range(3):
        client.post("/api/gear/manual", json=_sample_payload())
    page1 = client.get("/api/gear", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/api/gear", params={"limit": 2, "offset": 2}).json()
    assert len(page1) == 2
    assert len(page2) == 1


# ---------------------------------------------------------------------------
# GET /api/gear/{id}
# ---------------------------------------------------------------------------
def test_get_by_id(client: TestClient) -> None:
    created = client.post("/api/gear/manual", json=_sample_payload()).json()
    r = client.get(f"/api/gear/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_by_id_404(client: TestClient) -> None:
    assert client.get("/api/gear/999").status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/gear/{id}
# ---------------------------------------------------------------------------
def test_patch_partial_update_notes(client: TestClient) -> None:
    created = client.post("/api/gear/manual", json=_sample_payload()).json()
    r = client.patch(f"/api/gear/{created['id']}", json={"notes": "BiS for SG"})
    assert r.status_code == 200
    assert r.json()["notes"] == "BiS for SG"
    # Other fields untouched.
    assert r.json()["base_effects"][0]["name"] == "Precision Damage"


def test_patch_overall_confidence_maps_to_ocr_confidence_column(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/gear/manual", json=_sample_payload(overall_confidence=0.5)
    ).json()
    r = client.patch(f"/api/gear/{created['id']}", json={"overall_confidence": 0.99})
    assert r.status_code == 200
    assert r.json()["overall_confidence"] == pytest.approx(0.99)


def test_patch_replaces_extended_effects_list(client: TestClient) -> None:
    created = client.post("/api/gear/manual", json=_sample_payload()).json()
    new_effects = [
        {"stat_id": "Boss Damage", "tier": "A", "value": 1500.0, "confidence": 0.8},
        {"stat_id": "HP", "tier": "B", "value": 800.0, "confidence": 0.7},
    ]
    r = client.patch(
        f"/api/gear/{created['id']}", json={"extended_effects": new_effects}
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["extended_effects"]) == 2
    assert {e["stat_id"] for e in body["extended_effects"]} == {"Boss Damage", "HP"}


def test_patch_empty_body_noop(client: TestClient) -> None:
    created = client.post("/api/gear/manual", json=_sample_payload()).json()
    r = client.patch(f"/api/gear/{created['id']}", json={})
    assert r.status_code == 200
    assert r.json()["base_effects"][0]["name"] == "Precision Damage"


def test_patch_404(client: TestClient) -> None:
    assert client.patch("/api/gear/999", json={"notes": "x"}).status_code == 404


def test_patch_validation_rejects_bad_level(client: TestClient) -> None:
    created = client.post("/api/gear/manual", json=_sample_payload()).json()
    r = client.patch(f"/api/gear/{created['id']}", json={"level": 70})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/gear/{id}
# ---------------------------------------------------------------------------
def test_delete_returns_204(client: TestClient) -> None:
    created = client.post("/api/gear/manual", json=_sample_payload()).json()
    r = client.delete(f"/api/gear/{created['id']}")
    assert r.status_code == 204
    # Subsequent GET → 404.
    assert client.get(f"/api/gear/{created['id']}").status_code == 404


def test_delete_404(client: TestClient) -> None:
    assert client.delete("/api/gear/999").status_code == 404
