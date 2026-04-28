"""OCR pipeline: full-screen screenshot → ParsedGear.

The pipeline is **calibration-free** (per the 2026-04-27 architecture pivot).
The user takes a full-screen screenshot whenever a gear tooltip is on screen;
the pipeline auto-detects the tooltip card, anchors structural regions by
proportion, segments rows by whitespace, and identifies stats by their text
label rather than position.

Modules:
    preprocess.py — OpenCV image cleanup before Tesseract.
    parse.py      — regex helpers (numeric values, level, percent).
    fuzzy.py      — rapidfuzz wrapper over the stat-name catalog.
    rarity.py     — color-based rarity classification.
    templates.py  — template matching for tier badges and slot icons.
    detect.py     — Stage 1: locate the tooltip card on the full screenshot.
    anchors.py    — Stages 2 & 3: proportional anchor regions + row segmentation.
    debug.py      — annotated debug-image dumps, gated on BLOOD_HUNT_OCR_DEBUG.
    pipeline.py   — orchestrator that chains all six stages.

The split exists so each piece is independently testable. Tesseract and OpenCV
are heavy native dependencies; lazy imports keep unit tests cheap.
"""

from .anchors import CardAnchors, segment_rows
from .detect import DetectedCard, TooltipNotFound, detect_tooltip
from .fuzzy import normalize_stat
from .heroes import HERO_DISPLAY_NAMES, HERO_SLUGS, slug_for_hero
from .parse import parse_level, parse_percent, parse_rating, parse_tier_letter
from .pipeline import parse_gear_screenshot
from .preprocess import preprocess_for_tesseract
from .rarity import classify_rarity_by_color

__all__ = [
    "CardAnchors",
    "DetectedCard",
    "HERO_DISPLAY_NAMES",
    "HERO_SLUGS",
    "TooltipNotFound",
    "classify_rarity_by_color",
    "detect_tooltip",
    "normalize_stat",
    "parse_gear_screenshot",
    "parse_level",
    "parse_percent",
    "parse_rating",
    "parse_tier_letter",
    "preprocess_for_tesseract",
    "segment_rows",
    "slug_for_hero",
]
