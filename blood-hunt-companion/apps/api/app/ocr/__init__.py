"""OCR pipeline: screenshot → ParsedGear.

Modules:
    preprocess.py — OpenCV image cleanup before Tesseract.
    parse.py      — regex helpers (numeric values, level, percent).
    fuzzy.py      — rapidfuzz wrapper over the stat-name catalog.
    rarity.py     — color-based rarity classification.
    calibration.py— load resolution-specific bounding-box JSON.
    pipeline.py   — orchestrator that wires everything together.

The split exists so each piece is independently testable. Tesseract and OpenCV
are heavy native dependencies; we keep a thin abstraction that lets unit tests
mock them out.
"""

from .calibration import Calibration, load_calibration
from .fuzzy import normalize_stat
from .parse import parse_level, parse_percent
from .pipeline import parse_gear_screenshot
from .preprocess import preprocess_for_tesseract
from .rarity import classify_rarity_by_color

__all__ = [
    "Calibration",
    "classify_rarity_by_color",
    "load_calibration",
    "normalize_stat",
    "parse_gear_screenshot",
    "parse_level",
    "parse_percent",
    "preprocess_for_tesseract",
]
