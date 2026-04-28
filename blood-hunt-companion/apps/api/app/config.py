"""Runtime configuration & path helpers.

The app is local-only — config is read from environment variables with sane defaults.
All paths are resolved relative to the repository root so the same code works whether
the API is launched from `apps/api/` or from a Makefile target at the repo root.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


def _repo_root() -> Path:
    """Walk up from this file until we find the repo root marker.

    The marker is the presence of both a `data/` and an `apps/` directory.
    """
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "data").is_dir() and (candidate / "apps").is_dir():
            return candidate
    # Fallback for unusual layouts (e.g. zipped distribution): use cwd.
    return Path.cwd()


class Settings(BaseModel):
    """Runtime settings. Override any field via env var with `BHC_` prefix."""

    repo_root: Path
    game_data_dir: Path
    game_raw_dir: Path
    calibration_dir: Path
    screenshots_dir: Path
    db_path: Path
    cors_origins: list[str]
    tesseract_cmd: str | None  # None = use PATH

    @classmethod
    def load(cls) -> Settings:
        root = Path(os.environ.get("BHC_REPO_ROOT", str(_repo_root())))
        return cls(
            repo_root=root,
            game_data_dir=root / "data" / "game",
            game_raw_dir=root / "data" / "game" / "_raw",
            calibration_dir=root / "data" / "calibration",
            screenshots_dir=root / "data" / "screenshots",
            db_path=Path(os.environ.get("BHC_DB_PATH", str(root / "data" / "personal.db"))),
            cors_origins=os.environ.get(
                "BHC_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(","),
            tesseract_cmd=os.environ.get("BHC_TESSERACT_CMD") or None,
        )


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings.load()
