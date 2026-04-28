"""Gear CRUD endpoints.

The OCR ingest endpoint (`POST /api/gear/ingest`) lives in `main.py` because it
predates this router; it returns a `ParsedGear` *without* persisting. The flow is:

    1. POST /api/gear/ingest  → ParsedGear (review on frontend, edit if needed)
    2. POST /api/gear/manual  → persist (this router)
    3. GET  /api/gear         → list with filters
    4. GET  /api/gear/{id}    → single piece
    5. PATCH /api/gear/{id}   → edit fields
    6. DELETE /api/gear/{id}  → remove

The router is purely transport — Pydantic ↔ ORM conversion lives on the model.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models.gear import GearORM
from ..schemas.gear import ExtendedEffect, GearPatch, GearPiece, ParsedGear

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

    # `extended_effects` and `overall_confidence` map to differently-named columns;
    # everything else is a 1:1 attribute set.
    if "extended_effects" in changes:
        effects_raw = changes.pop("extended_effects")
        effects = [ExtendedEffect.model_validate(e) for e in (effects_raw or [])]
        orm.extended_effects_json = json.dumps([e.model_dump(mode="json") for e in effects])
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
