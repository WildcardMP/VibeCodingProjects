#!/usr/bin/env python3
"""Interactive bounding-box calibrator for the OCR pipeline.

Usage:
    python tools/ocr_calibration.py --screenshot path/to/sample_tooltip.png
    python tools/ocr_calibration.py --screenshot ... --ui-scale 1.0

Workflow:
    A window opens showing the screenshot. For each labeled region, drag a
    rectangle around the corresponding area on the tooltip, then press SPACE/ENTER
    to confirm. ESC cancels the current region. Press 'q' at any prompt to abort.

    The order of prompts is fixed:
        card, name, rarity_badge, level, base_effect,
        ext1.stat, ext1.tier, ext2.stat, ext2.tier, ...

    The result is written to:
        data/calibration/<W>x<H>_<scale_pct>.json

This script is a thin wrapper over `cv2.selectROI`, which has been shipping with
OpenCV since 3.x — robust on Windows/macOS/Linux.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

# Local import after sys.path manipulation
from app.ocr.calibration import (  # noqa: E402
    Calibration,
    CalibrationRegions,
    ExtendedEffectRegion,
    save_calibration,
)


def _select(window: str, image: object, label: str) -> tuple[int, int, int, int]:
    import cv2

    print(f"  → Drag a rectangle around: {label}  (SPACE/ENTER to confirm, ESC to skip, q to quit)")
    rect = cv2.selectROI(window, image, showCrosshair=True, fromCenter=False)  # type: ignore[arg-type]
    x, y, w, h = (int(v) for v in rect)
    if w == 0 or h == 0:
        print(f"    (skipped {label})")
    else:
        print(f"    {label}: x={x} y={y} w={w} h={h}")
    return x, y, w, h


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True, help="Sample tooltip screenshot.")
    parser.add_argument("--ui-scale", type=float, default=1.0, help="In-game UI scale (e.g. 1.0).")
    parser.add_argument(
        "--num-extended",
        type=int,
        default=4,
        help="How many extended-effect rows to calibrate (legendary tooltip = 4).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "calibration",
        help="Where to write the calibration JSON.",
    )
    args = parser.parse_args(argv)

    if not args.screenshot.exists():
        print(f"Screenshot not found: {args.screenshot}", file=sys.stderr)
        return 2

    import cv2

    image = cv2.imread(str(args.screenshot))
    if image is None:
        print(f"OpenCV could not read: {args.screenshot}", file=sys.stderr)
        return 2
    height, width = image.shape[:2]
    window = "Calibrate (drag rectangle, ENTER to confirm, ESC to skip)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    print(f"Screenshot: {args.screenshot.name}  ({width}x{height})  UI scale: {args.ui_scale}")
    print("Calibrating regions in fixed order. Press 'q' at any prompt to abort.")

    try:
        card = _select(window, image, "card (entire tooltip outline)")
        name = _select(window, image, "name (item name text)")
        rarity_badge = _select(window, image, "rarity_badge (color swatch / border sample)")
        level = _select(window, image, "level (Lv N)")
        base_effect = _select(window, image, "base_effect (top stat row)")

        extended: list[ExtendedEffectRegion] = []
        for i in range(args.num_extended):
            stat = _select(window, image, f"ext{i+1}.stat (text portion)")
            if stat[2] == 0 or stat[3] == 0:
                print(f"  Stopping after {i} extended effects.")
                break
            tier = _select(window, image, f"ext{i+1}.tier (S/A/B/C/D badge)")
            extended.append(ExtendedEffectRegion(stat=stat, tier=tier))
    finally:
        cv2.destroyAllWindows()

    calib = Calibration(
        resolution=(width, height),
        ui_scale=args.ui_scale,
        regions=CalibrationRegions(
            card=card,
            name=name,
            rarity_badge=rarity_badge,
            level=level,
            base_effect=base_effect,
            extended_effects=extended,
        ),
    )
    out_path = save_calibration(args.out_dir, calib)
    print(f"\n  ✓ Wrote calibration to {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
