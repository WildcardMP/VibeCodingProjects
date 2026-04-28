"""FastAPI entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000

CORS is locked to localhost; this app is never meant to be exposed to the network.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import settings
from .data_loader import load_game_data, stat_catalog
from .ocr.calibration import load_calibration
from .ocr.pipeline import parse_gear_screenshot
from .routers import gear as gear_router
from .schemas.gear import ParsedGear

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="Blood Hunt Companion API",
    version=__version__,
    description="Local-only backend for the Blood Hunt Companion app.",
)

cfg = settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistence routers. Migrations (`make migrate`) own schema creation; this
# module never touches `Base.metadata.create_all`.
app.include_router(gear_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "version": __version__, "time": datetime.now().isoformat()}


@app.get("/api/game/version")
def game_version() -> dict[str, object]:
    data = load_game_data()
    return {
        "version": data.version,
        "loaded_at": data.loaded_at.isoformat(),
        "counts": {
            "heroes": len(data.heroes),
            "traits": len(data.traits),
            "gear_stats": len(data.gear_stats),
            "arcana": len(data.arcana),
        },
        "sources": {k: str(v) for k, v in data.sources.items()},
    }


@app.get("/api/game/heroes")
def list_heroes() -> list[dict[str, object]]:
    data = load_game_data()
    return [h.model_dump() for h in data.heroes]


@app.get("/api/game/arcana")
def list_arcana() -> list[dict[str, object]]:
    data = load_game_data()
    return [a.model_dump() for a in data.arcana]


@app.get("/api/game/gear-stats")
def list_gear_stats() -> list[dict[str, object]]:
    data = load_game_data()
    return data.gear_stats


@app.post("/api/gear/ingest", response_model=ParsedGear)
async def ingest_gear(
    file: Annotated[UploadFile, File(...)],
    width: int = 3840,
    height: int = 2160,
    ui_scale: float = 1.0,
    hero_id: str | None = None,
) -> ParsedGear:
    """Accept a tooltip screenshot, run OCR, return the parsed gear (unsaved).

    The caller is expected to review the result on the frontend, edit any
    low-confidence fields, then POST to `/api/gear/manual` to persist.
    """
    if not file.filename:
        raise HTTPException(400, "file required")

    cfg.screenshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = cfg.screenshots_dir / f"{timestamp}_{Path(file.filename).name}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    try:
        calibration = load_calibration(cfg.calibration_dir, width, height, ui_scale)
    except FileNotFoundError as exc:
        raise HTTPException(412, str(exc)) from exc

    data = load_game_data()
    catalog = stat_catalog(data)
    if not catalog:
        raise HTTPException(
            412,
            "No gear-stat catalog available. Run FModel extraction (see DATA_PIPELINE.md) "
            "or remove this guard to use the bundled seed catalog.",
        )

    try:
        parsed = parse_gear_screenshot(str(dest), calibration, catalog, hero_id=hero_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("OCR failed for %s", dest)
        raise HTTPException(500, f"OCR failed: {exc}") from exc

    return parsed
