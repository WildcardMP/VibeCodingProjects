"""Resolution-specific bounding-box calibration files.

A calibration file lives at `data/calibration/<width>x<height>_<ui_scale>.json` and
defines where each tooltip field sits on screen. Generated interactively by
`tools/ocr_calibration.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class ExtendedEffectRegion(BaseModel):
    stat: tuple[int, int, int, int]  # (x, y, w, h)
    tier: tuple[int, int, int, int]


class CalibrationRegions(BaseModel):
    card: tuple[int, int, int, int]
    name: tuple[int, int, int, int]
    rarity_badge: tuple[int, int, int, int]
    level: tuple[int, int, int, int]
    base_effect: tuple[int, int, int, int]
    extended_effects: list[ExtendedEffectRegion] = Field(default_factory=list, max_length=4)
    # Optional: where the slot icon sits, if the UI shows one.
    slot_icon: tuple[int, int, int, int] | None = None


class Calibration(BaseModel):
    resolution: tuple[int, int]
    ui_scale: float
    regions: CalibrationRegions


def calibration_filename(width: int, height: int, ui_scale: float) -> str:
    return f"{width}x{height}_{int(round(ui_scale * 100))}.json"


def load_calibration(directory: Path, width: int, height: int, ui_scale: float = 1.0) -> Calibration:
    """Load the calibration matching the given resolution + UI scale, raise if missing.

    The error message tells the user exactly how to create one — calibration is a
    one-time per-resolution step, so a clear pointer beats a stack trace.
    """
    fname = calibration_filename(width, height, ui_scale)
    path = directory / fname
    if not path.exists():
        raise FileNotFoundError(
            f"No calibration for {width}x{height} @ {ui_scale*100:.0f}% UI scale.\n"
            f"Run: python tools/ocr_calibration.py --screenshot <a sample tooltip>.png\n"
            f"This will write {path}."
        )
    return Calibration.model_validate_json(path.read_text("utf-8"))


def save_calibration(directory: Path, calib: Calibration) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    w, h = calib.resolution
    path = directory / calibration_filename(w, h, calib.ui_scale)
    path.write_text(json.dumps(calib.model_dump(), indent=2), "utf-8")
    return path
