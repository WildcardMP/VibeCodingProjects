"""POST /api/simulate — Phase 3 F1 Damage Simulator endpoint.

Stateless: takes a `(hero_id, gear, traits, arcana, target)` tuple, returns
per-ability DPS + the aggregated `StatTotals`. No DB writes — the caller
is free to fire repeated requests for "what if I swap this piece" probes.

The router is purely transport: it loads the game-data catalog,
aggregates the build's stats, and hands off to `services.damage_calc`.
All business logic lives in `services/`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from ..data_loader import load_game_data
from ..schemas.simulation import SimulationRequest, SimulationResult
from ..services.damage_calc import find_hero, simulate
from ..services.stat_aggregator import aggregate_stats

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simulate", tags=["simulate"])


@router.post("", response_model=SimulationResult)
def run_simulation(req: SimulationRequest) -> SimulationResult:
    """Simulate a single (hero, build, target) combination.

    Returns 422 if `hero_id` doesn't match any hero in the game-data catalog
    — typically a frontend bug or a stale snapshot from before a patch.
    """
    data = load_game_data()
    hero = find_hero(data.heroes, req.hero_id)
    if hero is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown hero_id: {req.hero_id!r}",
        )

    stats = aggregate_stats(
        gear=req.gear,
        trait_alloc=req.trait_alloc,
        arcana_ids=req.arcana_ids,
        traits_catalog=data.traits,
        arcana_catalog=data.arcana,
    )
    result = simulate(hero, stats, req.target)
    log.info(
        "simulated hero=%s abilities=%d gear=%d traits=%d arcana=%d",
        hero.id, len(result.per_ability), len(req.gear),
        len(req.trait_alloc), len(req.arcana_ids),
    )
    return result
