"""Calibration-free OCR orchestrator: full-screen screenshot → ParsedGear.

Pipeline (per 2026-04-27 architectural pivot, see PROJECT.md §9 Phase 2):

    Stage 1 — `detect.detect_tooltip`        : locate the tooltip card on screen.
    Stage 2 — `anchors.compute_anchors`      : proportional regions inside the card.
    Stage 3 — `anchors.segment_rows`         : whitespace-based row segmentation.
    Stage 4 — `_extract_row` (this module)   : OCR each row, fuzzy-match label,
                                                template-match tier.
    Stage 5 — `_extract_top` (this module)   : item name, rarity, level, slot.
    Stage 6 — `_assemble` (this module)      : build ParsedGear + field_confidences.

Position-based stat identification is gone. **Stat identity comes from the
fuzzy-matched OCR text**, so a stat that's row-1 in one screenshot and row-3
in another lands at the right `stat_id` either way.

This module is the only one that imports `pytesseract`; tests for upstream
modules (fuzzy, parse, templates, detect, anchors) don't need Tesseract on PATH.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import settings
from ..schemas.common import GearSlot, Rarity, TierLetter
from ..schemas.gear import ExtendedEffect, ParsedGear
from .anchors import CardAnchors, Region, compute_anchors, crop, segment_rows
from .debug import dump_image
from .detect import DetectedCard, TooltipNotFound, crop_card, detect_tooltip
from .fuzzy import normalize_stat
from .parse import extract_stat_name, parse_level, parse_percent
from .preprocess import preprocess_for_tesseract
from .rarity import classify_rarity_by_color
from .templates import match_slot, match_tier

log = logging.getLogger(__name__)

# Tesseract page-segmentation configs.
_NUM_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789+-.,%Lvl "
_TEXT_CONFIG = "--psm 7"
_TIER_CONFIG = "--psm 10 -c tessedit_char_whitelist=SABCD"

# Confidence below this threshold is flagged for user review (CLAUDE.md §3.6).
_REVIEW_THRESHOLD = 0.7

# Confidence values for tier dual strategy (DATA_PIPELINE §2.7).
_TIER_CONF_BOTH_AGREE = 1.0
_TIER_CONF_SINGLE = 0.65
_TIER_CONF_NONE = 0.0

# Fallback slot when nothing identifies one (template match miss + no heuristic
# hit on the base effect). Frontend will flag low confidence.
_DEFAULT_SLOT: GearSlot = "armor"


# ---------------------------------------------------------------------------
# Asset directories (template PNGs the user supplies)
# ---------------------------------------------------------------------------
def _assets_dir() -> Path:
    return settings().game_data_dir / "_assets"


def _tier_templates_dir() -> Path:
    return _assets_dir() / "tier_badges"


def _slot_templates_dir() -> Path:
    return _assets_dir() / "slot_icons"


# ---------------------------------------------------------------------------
# Internal data classes
# ---------------------------------------------------------------------------
@dataclass
class ExtractedRow:
    """One extended-effect row after OCR + matching. Stage 4 output."""

    stat_name: str
    value: float
    tier: TierLetter
    raw_text: str
    confidence: dict[str, float] = field(default_factory=dict)

    def overall(self) -> float:
        """The row is only as trustworthy as its weakest field (CLAUDE.md §3.6)."""
        return min(self.confidence.values()) if self.confidence else 0.0


@dataclass
class TopOfCard:
    """Stage 5 output — top-band fields with per-field confidence."""

    name: str | None
    rarity: Rarity
    level: int
    slot: GearSlot
    base_effect: str
    base_value: float
    field_confidences: dict[str, float]


# ---------------------------------------------------------------------------
# Tesseract helpers
# ---------------------------------------------------------------------------
def _tesseract_cmd_set() -> None:
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


# ---------------------------------------------------------------------------
# Tier reconciliation (Tesseract + template match)
# ---------------------------------------------------------------------------
def _classify_tier_letter(text: str) -> TierLetter | None:
    """Pick a single S/A/B/C/D letter from Tesseract output."""
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

    - Both methods agree → confidence 1.0.
    - Only one method has a hit → confidence 0.65 (yellow band).
    - Methods disagree → trust the template match, confidence 0.65.
    - Neither → (None, 0.0); caller defaults the row tier and flags red.
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


# ---------------------------------------------------------------------------
# Slot resolution (template match + base-effect heuristic)
# ---------------------------------------------------------------------------
# Heuristic mapping used when slot template matching has no hit. Maps a base
# effect's stat name to the slot that most commonly hosts it (RESEARCH.md §3).
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
    return _BASE_TO_SLOT.get(base_effect, _DEFAULT_SLOT)


def resolve_slot(
    card_bgr: Any,
    anchors: CardAnchors,
    base_effect: str,
    *,
    templates_dir: Path | None = None,
) -> tuple[GearSlot, float]:
    """Pick the slot using the strongest available signal.

    1. Template match against `slot_icons/*.png` on the slot-icon anchor.
       Confidence = match score (0.55..1.0).
    2. Base-effect heuristic. Confidence = 0.5 (yellow/red boundary; the
       heuristic is genuinely uncertain).
    """
    sdir = templates_dir if templates_dir is not None else _slot_templates_dir()
    slot_crop = crop(card_bgr, anchors.slot_icon)
    match = match_slot(slot_crop, sdir)
    if match is not None:
        return match
    return _heuristic_slot(base_effect), 0.5


# ---------------------------------------------------------------------------
# Stage 4 — row content extraction
# ---------------------------------------------------------------------------
def _extract_row(
    extended_bgr: Any,
    row_y: tuple[int, int],
    stat_catalog: list[str],
    *,
    tier_templates: Path | None = None,
) -> ExtractedRow | None:
    """Extract stat label + value + tier from one row of the extended-effects block.

    Returns None when the row OCR is empty (treat as no extended effect).
    """
    import numpy as np

    arr = np.asarray(extended_bgr)
    region_w = arr.shape[1]
    y0, y1 = row_y
    row_img = arr[y0:y1, :]
    if row_img.size == 0:
        return None

    # Left ~70% holds the stat label + value; right ~30% holds the tier badge.
    text_w = int(round(region_w * 0.7))
    text_img = row_img[:, :text_w]
    tier_img = row_img[:, text_w:]

    text_raw = _ocr(preprocess_for_tesseract(text_img), _TEXT_CONFIG)
    if not text_raw.strip():
        return None
    stat_raw = extract_stat_name(text_raw)
    stat_name, stat_score = normalize_stat(stat_raw, stat_catalog)
    value = parse_percent(text_raw) or 0.0

    tier_text_raw = _ocr(preprocess_for_tesseract(tier_img), _TIER_CONFIG)
    tier_letter, tier_conf = resolve_tier(
        tier_img, tier_text_raw, templates_dir=tier_templates
    )
    tier_value: TierLetter = tier_letter if tier_letter is not None else "D"

    return ExtractedRow(
        stat_name=stat_name,
        value=value,
        tier=tier_value,
        raw_text=text_raw,
        confidence={
            "stat_name": min(stat_score / 100.0, 1.0),
            "tier": tier_conf,
            "value": 1.0 if value > 0 else 0.5,
        },
    )


# ---------------------------------------------------------------------------
# Stage 5 — top-of-card extraction
# ---------------------------------------------------------------------------
def _extract_top(
    card_bgr: Any,
    anchors: CardAnchors,
    stat_catalog: list[str],
    *,
    detection_confidence: float,
    slot_templates: Path | None = None,
) -> TopOfCard:
    name_raw = _ocr(preprocess_for_tesseract(crop(card_bgr, anchors.name)), _TEXT_CONFIG)
    name = name_raw.strip() or None
    name_conf = 0.85 if name else 0.0

    rarity = classify_rarity_by_color(crop(card_bgr, anchors.rarity_badge))
    rarity_conf = 0.9  # color match is usually unambiguous

    level_raw = _ocr(preprocess_for_tesseract(crop(card_bgr, anchors.level)), _NUM_CONFIG)
    level = parse_level(level_raw) or 1
    level_conf = 0.9 if parse_level(level_raw) is not None else 0.4

    base_raw = _ocr(
        preprocess_for_tesseract(crop(card_bgr, anchors.base_effect)), _TEXT_CONFIG
    )
    base_name_raw = extract_stat_name(base_raw)
    base_effect, base_score = normalize_stat(base_name_raw, stat_catalog)
    base_value = parse_percent(base_raw) or 0.0
    base_conf = min(base_score / 100.0, 1.0)

    slot, slot_conf = resolve_slot(
        card_bgr, anchors, base_effect, templates_dir=slot_templates
    )

    confidences = {
        "name": name_conf,
        "rarity": rarity_conf,
        "level": level_conf,
        "slot": slot_conf,
        "base_effect": base_conf,
        "base_value": base_conf,  # value confidence shares the row OCR's score
        "detection": detection_confidence,
    }

    return TopOfCard(
        name=name,
        rarity=rarity,
        level=level,
        slot=slot,
        base_effect=base_effect,
        base_value=base_value,
        field_confidences=confidences,
    )


# ---------------------------------------------------------------------------
# Stage 6 — assembly
# ---------------------------------------------------------------------------
def _assemble(
    image_path: str,
    hero_id: str | None,
    top: TopOfCard,
    rows: list[ExtractedRow],
) -> ParsedGear:
    extended = [
        ExtendedEffect(
            stat_id=r.stat_name,
            tier=r.tier,
            value=r.value,
            raw_text=r.raw_text,
            confidence=r.overall(),
        )
        for r in rows
    ]
    # Overall confidence = mean of every per-field score we have, plus per-row
    # overalls. Geometric mean would penalise any single weak field harder, but
    # the simple mean tracks how the frontend's three-band coloring will read.
    all_scores = list(top.field_confidences.values()) + [r.overall() for r in rows]
    overall = sum(all_scores) / len(all_scores) if all_scores else 0.0

    return ParsedGear(
        name=top.name,
        slot=top.slot,
        hero_id=hero_id,
        rarity=top.rarity,
        level=top.level,
        base_effect=top.base_effect,
        base_value=top.base_value,
        extended_effects=extended,
        overall_confidence=overall,
        field_confidences=top.field_confidences,
        source_screenshot=str(Path(image_path).resolve()),
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def parse_gear_screenshot(
    image_path: str,
    stat_catalog: list[str],
    *,
    hero_id: str | None = None,
    tier_templates_dir: Path | None = None,
    slot_templates_dir: Path | None = None,
) -> ParsedGear:
    """Parse a full-screen screenshot containing a gear tooltip.

    Args:
        image_path: filesystem path to the screenshot.
        stat_catalog: list of canonical stat display names from `gear_stats.json`.
        hero_id: optional pre-known hero id; passed through to the result so the
            simulator and roll-evaluator can use hero-specific scoring.
        tier_templates_dir: override for tier-badge PNGs (defaults to
            `data/game/_assets/tier_badges/`).
        slot_templates_dir: override for slot-icon PNGs (defaults to
            `data/game/_assets/slot_icons/`).

    Returns:
        A `ParsedGear` with `field_confidences` populated. Per-row confidences
        live on each `ExtendedEffect`.

    Raises:
        TooltipNotFound: if Stage 1 cannot locate a tooltip on the screenshot.
            The `/api/gear/ingest` endpoint translates this to HTTP 422.
    """
    img = _read_image(image_path)

    card = detect_tooltip(img)  # Stage 1 — raises TooltipNotFound on miss
    card_bgr = crop_card(img, card)
    dump_image("pipeline", "card_crop", card_bgr)

    anchors = compute_anchors(card_bgr)  # Stage 2
    extended_region = crop(card_bgr, anchors.extended_effects)
    row_bands = segment_rows(extended_region)  # Stage 3

    top = _extract_top(  # Stage 5
        card_bgr,
        anchors,
        stat_catalog,
        detection_confidence=card.confidence,
        slot_templates=slot_templates_dir,
    )

    rows: list[ExtractedRow] = []  # Stage 4
    for band in row_bands:
        row = _extract_row(
            extended_region,
            band,
            stat_catalog,
            tier_templates=tier_templates_dir,
        )
        if row is not None:
            rows.append(row)

    parsed = _assemble(image_path, hero_id, top, rows)  # Stage 6
    log.info(
        "parsed gear: name=%s slot=%s rarity=%s level=%d base=%s ext=%d overall=%.2f",
        parsed.name, parsed.slot, parsed.rarity, parsed.level,
        parsed.base_effect, len(parsed.extended_effects), parsed.overall_confidence,
    )
    return parsed


# ---------------------------------------------------------------------------
# Helpers exposed for tests
# ---------------------------------------------------------------------------
def fields_below_review_threshold(parsed: ParsedGear) -> list[str]:
    """Return field names whose confidence is below the review threshold.

    The frontend uses this to decide which fields to flag yellow/red. Tests use
    it to verify the threshold logic without coupling to the UI.
    """
    flagged = [
        name
        for name, conf in parsed.field_confidences.items()
        if conf < _REVIEW_THRESHOLD
    ]
    flagged.extend(
        f"extended_effects[{i}]"
        for i, e in enumerate(parsed.extended_effects)
        if e.confidence < _REVIEW_THRESHOLD
    )
    return flagged


# Re-exports for backwards compatibility with downstream tests.
__all__ = [
    "DetectedCard",
    "ExtractedRow",
    "Region",
    "TooltipNotFound",
    "TopOfCard",
    "fields_below_review_threshold",
    "parse_gear_screenshot",
    "resolve_slot",
    "resolve_tier",
]
