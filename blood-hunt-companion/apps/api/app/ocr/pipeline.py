"""End-to-end OCR pipeline: a screenshot path → ParsedGear.

This module is the only one in `app.ocr` that imports Tesseract (`pytesseract`).
We import lazily so unit tests that hit `parse.py` / `fuzzy.py` / `rarity.py` don't
require Tesseract installed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING, Any

from ..config import settings
from ..schemas.common import GearSlot, Rarity, TierLetter
from ..schemas.gear import ExtendedEffect, ParsedGear
from .calibration import Calibration
from .fuzzy import normalize_stat
from .parse import extract_stat_name, parse_level, parse_percent
from .preprocess import crop, preprocess_for_tesseract
from .rarity import classify_rarity_by_color
from .templates import match_slot, match_tier

if TYPE_CHECKING:
    import numpy as np  # noqa: F401

log = logging.getLogger(__name__)


def _assets_dir() -> Path:
    """Root for user-supplied template assets (tier badges, slot icons)."""
    return settings().game_data_dir / "_assets"


def _tier_templates_dir() -> Path:
    return _assets_dir() / "tier_badges"


def _slot_templates_dir() -> Path:
    return _assets_dir() / "slot_icons"


# Confidence values for the dual tier-detection strategy. See DATA_PIPELINE §2.7.
# 0.65 keeps "single-method" inside the yellow band (≥0.6) defined in CLAUDE.md §3.6.
_TIER_CONF_BOTH_AGREE = 1.0
_TIER_CONF_SINGLE = 0.65
_TIER_CONF_NONE = 0.0


# Tesseract page-segmentation configs.
NUM_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789+-.,%Lvl "
TEXT_CONFIG = "--psm 7"
TIER_CONFIG = "--psm 10 -c tessedit_char_whitelist=SABCD"


def _tesseract_cmd_set() -> None:
    """Honour BHC_TESSERACT_CMD if set."""
    cmd = settings().tesseract_cmd
    if cmd:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd


def _ocr(img: Any, config: str) -> str:
    import pytesseract

    _tesseract_cmd_set()
    return str(pytesseract.image_to_string(img, config=config)).strip()


def _read_image(path: str) -> Any:
    import cv2

    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"OCR pipeline could not read image: {path}")
    return img


def _classify_tier_letter(text: str) -> TierLetter | None:
    """Pick a single S/A/B/C/D letter from Tesseract output.

    Tesseract on a single character with `--psm 10` often emits the letter alone,
    sometimes with a stray punctuation mark — strip and match.
    """
    if not text:
        return None
    cleaned = "".join(ch for ch in text if ch.isalpha()).upper()
    for ch in cleaned:
        if ch in {"S", "A", "B", "C", "D"}:
            return ch  # type: ignore[return-value]
    return None


def resolve_tier(
    tier_crop: Any,
    tesseract_text: str,
    *,
    templates_dir: Path | None = None,
) -> tuple[TierLetter | None, float]:
    """Reconcile Tesseract output with template-match output for a tier badge.

    Strategy (per DATA_PIPELINE.md §2.7):
        - Both methods agree → confidence 1.0
        - Only one method returned a letter → confidence 0.65 (yellow band)
        - Neither → (None, 0.0); caller must surface for manual correction
        - Methods disagree → trust the template match (more robust at small sizes)
          and report 0.65 confidence; the discrepancy is logged.

    `templates_dir` is the directory of `{S,A,B,C,D}.png`. When None, falls back
    to `<game_data_dir>/_assets/tier_badges/`. Missing directories degrade to
    Tesseract-only without raising.
    """
    tess_letter = _classify_tier_letter(tesseract_text)
    tdir = templates_dir if templates_dir is not None else _tier_templates_dir()
    tmpl_result = match_tier(tier_crop, tdir)
    tmpl_letter = tmpl_result[0] if tmpl_result else None

    if tess_letter is not None and tmpl_letter is not None:
        if tess_letter == tmpl_letter:
            return tess_letter, _TIER_CONF_BOTH_AGREE
        log.info(
            "tier disagreement: tesseract=%s template=%s — trusting template",
            tess_letter, tmpl_letter,
        )
        return tmpl_letter, _TIER_CONF_SINGLE
    if tmpl_letter is not None:
        return tmpl_letter, _TIER_CONF_SINGLE
    if tess_letter is not None:
        return tess_letter, _TIER_CONF_SINGLE
    return None, _TIER_CONF_NONE


def resolve_slot(
    img: Any,
    calibration: Calibration,
    base_effect: str,
    *,
    templates_dir: Path | None = None,
) -> tuple[GearSlot, float]:
    """Pick a slot for a gear piece using the strongest available signal.

    1. If the calibration has a `slot_icon` region AND template assets are present,
       run a template match — confidence = match score (0.55..1.0).
    2. Otherwise fall back to the base-effect heuristic — confidence 0.5
       (yellow/red boundary, since the heuristic is genuinely uncertain).
    """
    sdir = templates_dir if templates_dir is not None else _slot_templates_dir()
    if calibration.regions.slot_icon is not None:
        slot_crop = crop(img, calibration.regions.slot_icon)
        match = match_slot(slot_crop, sdir)
        if match is not None:
            return match
    return _heuristic_slot(base_effect), 0.5


def parse_gear_screenshot(
    image_path: str,
    calibration: Calibration,
    stat_catalog: list[str],
    *,
    hero_id: str | None = None,
) -> ParsedGear:
    """Parse a single tooltip screenshot into a `ParsedGear`.

    Args:
        image_path: filesystem path to the screenshot (PNG/JPG).
        calibration: bounding boxes for the user's resolution.
        stat_catalog: list of canonical stat display names from `gear_stats.json`.
        hero_id: optional — if the user already knows which hero this is for, pass it
                 through so the simulator can use hero-specific scoring.

    Returns a `ParsedGear` with per-field confidences. Caller is expected to surface
    low-confidence fields for human review before persisting.
    """
    img = _read_image(image_path)
    regs = calibration.regions

    # Rarity by color (most reliable signal we have).
    rarity: Rarity = classify_rarity_by_color(crop(img, regs.rarity_badge))

    # Level
    level_text = _ocr(preprocess_for_tesseract(crop(img, regs.level)), NUM_CONFIG)
    level = parse_level(level_text) or 1

    # Base effect (e.g. "Total Output Boost +1234%")
    base_text = _ocr(preprocess_for_tesseract(crop(img, regs.base_effect)), TEXT_CONFIG)
    base_name_raw = extract_stat_name(base_text)
    base_name, base_score = normalize_stat(base_name_raw, stat_catalog)
    base_value = parse_percent(base_text) or 0.0

    # Extended effects (1–4 rows depending on rarity)
    extended: list[ExtendedEffect] = []
    confidences: list[float] = [base_score / 100.0]
    for region in regs.extended_effects:
        stat_text = _ocr(preprocess_for_tesseract(crop(img, region.stat)), TEXT_CONFIG)
        if not stat_text.strip():
            continue
        tier_crop = crop(img, region.tier)
        tier_text = _ocr(preprocess_for_tesseract(tier_crop), TIER_CONFIG)
        stat_name_raw = extract_stat_name(stat_text)
        stat_name, score = normalize_stat(stat_name_raw, stat_catalog)
        tier_letter, tier_conf = resolve_tier(tier_crop, tier_text)
        # Conservative default when no signal at all — frontend will flag it red.
        tier_value: TierLetter = tier_letter if tier_letter is not None else "D"
        value = parse_percent(stat_text) or 0.0
        # Per-row confidence is the min of stat-name confidence and tier confidence:
        # the row is only as trustworthy as its weakest field.
        row_confidence = min(score / 100.0, tier_conf)
        ext = ExtendedEffect(
            stat_id=stat_name,
            tier=tier_value,
            value=value,
            raw_text=stat_text,
            confidence=row_confidence,
        )
        extended.append(ext)
        confidences.append(ext.confidence)

    overall = float(mean(confidences)) if confidences else 0.0

    # Slot resolution: slot-icon template match if calibrated and assets present;
    # otherwise fall back to a base-effect heuristic. Either way, the frontend lets
    # the user override before save.
    slot, _slot_conf = resolve_slot(img, calibration, base_name)

    parsed = ParsedGear(
        slot=slot,
        hero_id=hero_id,
        rarity=rarity,
        level=level,
        base_effect=base_name,
        base_value=base_value,
        extended_effects=extended,
        overall_confidence=overall,
        source_screenshot=str(Path(image_path).resolve()),
    )
    log.info(
        "Parsed gear: slot=%s rarity=%s level=%d base=%s ext=%d conf=%.2f",
        parsed.slot, parsed.rarity, parsed.level, parsed.base_effect,
        len(parsed.extended_effects), parsed.overall_confidence,
    )
    return parsed


# Crude slot inference used as a fallback when slot-icon template matching fails
# (e.g., the user hasn't supplied tier/slot template assets yet). Maps a base-effect
# stat name to the slot that most commonly hosts it per RESEARCH.md §3.
_BASE_TO_SLOT: dict[str, GearSlot] = {
    "Total Output Boost": "armor",
    "Total Damage Bonus": "armor",
    "Rune Cooldown Reduction": "armor",
    "HP": "armor",
    "Precision Damage": "weapon",
    "Precision Rate": "weapon",
    "Crit Damage": "weapon",
    "Ammo Capacity": "weapon",
    "Boss Damage": "accessory",
    "Close-Range Damage": "accessory",
    "Vulnerability Inflicted": "accessory",
    "Damage vs Healthy Enemies": "accessory",
}


def _heuristic_slot(base_effect: str) -> GearSlot:
    return _BASE_TO_SLOT.get(base_effect, "armor")
