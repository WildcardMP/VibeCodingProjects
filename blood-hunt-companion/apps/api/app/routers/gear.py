"""Gear CRUD + scoring endpoints.

The OCR ingest endpoint (`POST /api/gear/ingest`) lives in `main.py` because it
predates this router; it returns a `ParsedGear` *without* persisting. The flow is:

    1. POST /api/gear/ingest  → ParsedGear (review on frontend, edit if needed)
    2. POST /api/gear/manual  → persist (this router)
    3. GET  /api/gear         → list with filters
    4. GET  /api/gear/{id}    → single piece
    5. PATCH /api/gear/{id}   → edit fields
    6. DELETE /api/gear/{id}  → remove
    7. POST /api/gear/score   → Phase 4 F2 roll evaluator (stateless, no DB)

The router is purely transport — Pydantic ↔ ORM conversion lives on the model
for CRUD; scoring math lives in `services.roll_score`.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data_loader import load_game_data
from ..db import get_session
from ..models.gear import GearORM
from ..schemas.gear import BaseEffect, ExtendedEffect, GearPatch, GearPiece, ParsedGear
from ..schemas.roll_score import RollScoreRequest, RollScoreResult
from ..services.roll_score import (
    UnknownAbilityError,
    UnknownHeroError,
    compute_roll_score,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gear", tags=["gear"])

# Re-usable Annotated dependency — keeps each handler's signature short and
# satisfies ruff B008 (no function calls in argument defaults).
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/manual", response_model=GearPiece, status_code=status.HTTP_201_CREATED)
def create_gear(parsed: ParsedGear, session: SessionDep) -> GearPiece:
    """Persist a `ParsedGear` (post-OCR review or hand-entered) as a `GearPiece`."""
    orm = GearORM.from_parsed(parsed)
    session.add(orm)
    session.flush()  # populate orm.id without committing — the dep handles commit
    log.info("gear created id=%s slot=%s rarity=%s", orm.id, orm.slot, orm.rarity)
    return orm.to_pydantic()


@router.get("", response_model=list[GearPiece])
def list_gear(
    session: SessionDep,
    hero_id: Annotated[str | None, Query()] = None,
    slot: Annotated[str | None, Query()] = None,
    rarity: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    is_equipped: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GearPiece]:
    """List gear with optional filters. Defaults sort newest-first."""
    stmt = select(GearORM)
    if hero_id is not None:
        stmt = stmt.where(GearORM.hero_id == hero_id)
    if slot is not None:
        stmt = stmt.where(GearORM.slot == slot)
    if rarity is not None:
        stmt = stmt.where(GearORM.rarity == rarity)
    if min_confidence is not None:
        stmt = stmt.where(GearORM.ocr_confidence >= min_confidence)
    if is_equipped is not None:
        stmt = stmt.where(GearORM.is_equipped.is_(is_equipped))
    stmt = stmt.order_by(GearORM.parsed_at.desc()).limit(limit).offset(offset)
    rows = session.scalars(stmt).all()
    return [r.to_pydantic() for r in rows]


@router.get("/{gear_id}", response_model=GearPiece)
def get_gear(gear_id: int, session: SessionDep) -> GearPiece:
    orm = session.get(GearORM, gear_id)
    if orm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"gear {gear_id} not found")
    return orm.to_pydantic()


@router.patch("/{gear_id}", response_model=GearPiece)
def update_gear(gear_id: int, patch: GearPatch, session: SessionDep) -> GearPiece:
    """Partial update. Only fields present in the request body are applied.

    `extended_effects` (list) replaces the whole list when present — partial
    list edits aren't supported because identifying a specific extended-effect
    row across edits would require a stable key the schema doesn't have.
    """
    orm = session.get(GearORM, gear_id)
    if orm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"gear {gear_id} not found")

    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        return orm.to_pydantic()

    # JSON-backed list fields and the renamed confidence column need bespoke
    # handling; everything else is a 1:1 attribute set.
    if "extended_effects" in changes:
        effects_raw = changes.pop("extended_effects")
        effects = [ExtendedEffect.model_validate(e) for e in (effects_raw or [])]
        orm.extended_effects_json = json.dumps([e.model_dump(mode="json") for e in effects])
    if "base_effects" in changes:
        base_raw = changes.pop("base_effects")
        base = [BaseEffect.model_validate(e) for e in (base_raw or [])]
        orm.base_effects_json = json.dumps([e.model_dump(mode="json") for e in base])
    if "overall_confidence" in changes:
        orm.ocr_confidence = changes.pop("overall_confidence")

    for key, value in changes.items():
        setattr(orm, key, value)

    session.flush()
    log.info("gear updated id=%s fields=%s", gear_id, sorted(changes.keys()))
    return orm.to_pydantic()


@router.delete("/{gear_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gear(gear_id: int, session: SessionDep) -> None:
    orm = session.get(GearORM, gear_id)
    if orm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"gear {gear_id} not found")
    session.delete(orm)
    log.info("gear deleted id=%s", gear_id)


# ---------------------------------------------------------------------------
# POST /api/gear/score — Phase 4 F2 Gear Roll Evaluator (stateless)
# ---------------------------------------------------------------------------
@router.post("/score", response_model=RollScoreResult)
def score_gear(req: RollScoreRequest) -> RollScoreResult:
    """Score a single gear roll against a build context. Stateless — no DB.

    Returns 422 when:
    - ``BuildContext.hero_id`` doesn't match a hero in the catalog.
    - ``BuildContext.ability_id`` is provided but doesn't match any of that
      hero's abilities.
    - ``gear.extended_effects`` is empty AND ``gear.rarity != "normal"``.
      That's a parsing artefact, not a valid roll — normal-rarity pieces
      legitimately have zero rolls and score as ``trash`` / ``smelt``.
    """
    if req.gear.rarity != "normal" and not req.gear.extended_effects:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{req.gear.rarity!r} gear must have at least one extended effect",
        )

    data = load_game_data()
    try:
        result = compute_roll_score(req.gear, req.build, game_data=data)
    except UnknownHeroError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except UnknownAbilityError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    log.info(
        "scored gear: rarity=%s score=%.1f threshold=%s forge=%s "
        "rows=%d uncatalogued=%d",
        req.gear.rarity, result.score, result.threshold, result.forge_action,
        len(result.breakdown), len(result.uncatalogued_stats),
    )
    return result
