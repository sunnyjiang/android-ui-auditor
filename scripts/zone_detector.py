"""
Phase 1: Zone Detector

Accepts an image path, returns:
  - Grid zones (N×M partition with per-cell stats)
  - Functional zones (StatusBar / AppBar / ContentArea / NavBar)
  - UI element bounding boxes with estimated types

Dependencies: opencv-python, numpy, pillow
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import Optional

from models import (
    ElementBox,
    ElementType,
    FunctionalZone,
    FunctionalZones,
    GridZone,
    ZoneDetectionResult,
    ZoneType,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Android standard proportions (fraction of image height)
_STATUS_BAR_RATIO = 0.05      # top ~5%
_NAV_BAR_RATIO = 0.08         # bottom ~8%
_APP_BAR_RATIO = 0.07         # ~7% below status bar

# Element detection thresholds
_MIN_ELEMENT_AREA = 100       # px² — ignore smaller contours
_MAX_ELEMENT_AREA = 500_000  # px² — ignore full-screen elements
_ELEMENT_ASPECT_BUTTON = 1.5  # w/h ratio threshold for button vs text
_ICON_MAX_SIZE = 80           # px — icons shouldn't be larger than this
_TEXT_ASPECT = 0.3            # h/w ratio threshold for text (tall thin)
_CARD_MIN_ASPECT = 1.2        # w/h ratio for card — at least wider than tall

# Grid
_DEFAULT_GRID = (3, 4)        # rows × cols


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_zones(
    image_path: str,
    grid_size: tuple[int, int] = _DEFAULT_GRID,
    debug_image: bool = False,
) -> ZoneDetectionResult:
    """
    Run the full Phase 1 pipeline on a screenshot.

    Parameters
    ----------
    image_path : str
        Path to the PNG or JPG screenshot.
    grid_size : tuple[int, int]
        Number of (rows, cols) for the grid overlay. Default (3, 4).
    debug_image : bool
        If True, saves a debug image with detected boxes drawn on it
        next to the original file.

    Returns
    -------
    ZoneDetectionResult
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Load image
    img_bgr = cv2.imread(str(path))
    if img_bgr is None:
        raise ValueError(f"Could not read image: {image_path}")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    # ── Grid zones ──────────────────────────────────────────────────────────
    grid_zones = _compute_grid_zones(img_rgb, grid_size)

    # ── Functional zones ─────────────────────────────────────────────────────
    functional_zones = _detect_functional_zones(img_rgb, w, h)

    # ── Element bounding boxes ───────────────────────────────────────────────
    element_boxes = _detect_element_boxes(img_bgr, functional_zones)

    # Count elements per grid cell
    for gz in grid_zones:
        gz.element_count = _count_elements_in_cell(element_boxes, gz)

    result = ZoneDetectionResult(
        image_path=str(path.resolve()),
        image_width=w,
        image_height=h,
        grid_size=grid_size,
        grid_zones=grid_zones,
        functional_zones=functional_zones,
        element_boxes=element_boxes,
    )

    # ── Debug output ──────────────────────────────────────────────────────────
    if debug_image:
        _save_debug_image(img_rgb, element_boxes, functional_zones, grid_zones, path)

    return result


# ---------------------------------------------------------------------------
# 1. Grid zones
# ---------------------------------------------------------------------------

def _compute_grid_zones(
    img_rgb: np.ndarray,
    grid_size: tuple[int, int],
) -> list[GridZone]:
    rows, cols = grid_size
    h, w = img_rgb.shape[:2]
    cell_h = h // rows
    cell_w = w // cols

    zones = []
    for row in range(rows):
        for col in range(cols):
            x = col * cell_w
            y = row * cell_h
            # Last row/col get the remainder so there are no gaps
            cell_h_actual = cell_h if row < rows - 1 else h - row * cell_h
            cell_w_actual = cell_w if col < cols - 1 else w - col * cell_w

            cell = img_rgb[y : y + cell_h_actual, x : x + cell_w_actual]

            # Dominant color via KMeans (k=3)
            dominant = _dominant_color(cell)

            # Whitespace ratio: fraction of pixels close to white
            white_ratio = _whitespace_ratio(cell)

            zones.append(
                GridZone(
                    id=f"grid_{row}_{col}",
                    row=row,
                    col=col,
                    x=x,
                    y=y,
                    w=cell_w_actual,
                    h=cell_h_actual,
                    element_count=0,  # filled in after element detection
                    dominant_color=dominant,
                    whitespace_ratio=white_ratio,
                )
            )
    return zones


def _dominant_color(cell: np.ndarray) -> str:
    """Return the most common color in the cell as a hex string."""
    pixels = cell.reshape(-1, 3)
    # Use a simple color binning: quantize to 8 levels per channel
    quantized = (pixels // 32) * 32
    # Find the most frequent unique color
    unique, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = unique[np.argmax(counts)]
    return f"#{int(dominant[0]):02x}{int(dominant[1]):02x}{int(dominant[2]):02x}"


def _whitespace_ratio(cell: np.ndarray) -> float:
    """
    Fraction of pixels that are near-white (assume background).
    A pixel is considered 'white' if all RGB channels > 200.
    """
    white = np.all(cell > 200, axis=-1)
    return float(np.mean(white))


# ---------------------------------------------------------------------------
# 2. Functional zones
# ---------------------------------------------------------------------------

def _detect_functional_zones(
    img_rgb: np.ndarray,
    w: int,
    h: int,
) -> FunctionalZones:
    """Identify StatusBar, AppBar, ContentArea, NavBar by layout heuristics."""

    status_bar_h = max(int(h * _STATUS_BAR_RATIO), 1)
    app_bar_h = max(int(h * _APP_BAR_RATIO), 1)
    nav_bar_h = max(int(h * _NAV_BAR_RATIO), 1)

    # StatusBar: very top strip
    status_bar = FunctionalZone(
        zone_type=ZoneType.STATUS_BAR,
        x=0,
        y=0,
        w=w,
        h=status_bar_h,
    )

    # AppBar: immediately below status bar
    app_bar_y = status_bar_h
    app_bar = FunctionalZone(
        zone_type=ZoneType.APP_BAR,
        x=0,
        y=app_bar_y,
        w=w,
        h=app_bar_h,
    )

    # ContentArea: between app bar and nav bar
    content_y = app_bar_y + app_bar_h
    content_h = h - nav_bar_h - content_y
    content_area = FunctionalZone(
        zone_type=ZoneType.CONTENT_AREA,
        x=0,
        y=content_y,
        w=w,
        h=max(content_h, 1),
    )

    # NavBar: bottom strip
    nav_bar = FunctionalZone(
        zone_type=ZoneType.NAV_BAR,
        x=0,
        y=h - nav_bar_h,
        w=w,
        h=nav_bar_h,
    )

    return FunctionalZones(
        status_bar=status_bar,
        app_bar=app_bar,
        content_area=content_area,
        nav_bar=nav_bar,
    )


# ---------------------------------------------------------------------------
# 3. Element bounding boxes
# ---------------------------------------------------------------------------

def _detect_element_boxes(
    img_bgr: np.ndarray,
    zones: FunctionalZones,
) -> list[ElementBox]:
    """
    Detect UI element bounding boxes using OpenCV contour analysis.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Canny edge detection
    edges = cv2.Canny(blurred, threshold1=50, threshold2=150)

    # Dilate to close gaps in edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=2)

    # Find contours
    contours, hierarchy = cv2.findContours(
        edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    # Hierarchy: [Next, Previous, First_Child, Parent]
    if hierarchy is None:
        return []

    boxes: list[ElementBox] = []
    content_area = zones.content_area

    for idx, contour in enumerate(contours):
        x, y, cw, ch = cv2.boundingRect(contour)
        area = cw * ch

        # Filter by area
        if area < _MIN_ELEMENT_AREA or area > _MAX_ELEMENT_AREA:
            continue

        # Skip if outside content area (we mostly care about content)
        # But allow elements in app bar too
        if content_area is not None:
            cx, cy = x + cw // 2, y + ch // 2
            if not (
                (0 <= cx < content_area.w)
                and (0 <= cy < content_area.h + content_area.y)
            ):
                # Allow if in app bar
                app_bar = zones.app_bar
                if app_bar is None or not (
                    (0 <= cx < app_bar.w)
                    and (0 <= cy < app_bar.h + app_bar.y)
                ):
                    continue

        # Classify element type based on geometry
        element_type = _classify_element(cw, ch, area, idx, contours)

        # Build the element box
        box = ElementBox(
            element_id=f"element_{len(boxes)}",
            x=x,
            y=y,
            w=cw,
            h=ch,
            element_type=element_type,
            confidence=0.7,  # default confidence, refined later by Vision
        )
        boxes.append(box)

    # De-duplicate overlapping boxes (prefer larger ones)
    boxes = _deduplicate_boxes(boxes)

    return boxes


def _classify_element(
    w: int, h: int, area: int, idx: int, contours: list
) -> ElementType:
    """
    Classify a contour as one of the ElementType enum values
    based purely on geometric properties.
    """
    aspect = w / max(h, 1)   # width / height
    tall_thin = h / max(w, 1)  # height / width

    # Icon: small (within icon size limit), roughly square or circular
    if w <= _ICON_MAX_SIZE and h <= _ICON_MAX_SIZE and area > 200:
        if 0.5 <= aspect <= 2.0:
            return ElementType.ICON

    # Text: tall and thin
    if tall_thin > 3.0 and h > 20:
        return ElementType.TEXT

    # Button: wider than tall, solid-looking
    if aspect > _ELEMENT_ASPECT_BUTTON and h < 100:
        return ElementType.BUTTON

    # Card: large and roughly rectangular
    if w > 100 and h > 50 and aspect > _CARD_MIN_ASPECT:
        return ElementType.CARD

    # Switch: square-ish and small
    if w < 80 and h < 50 and 0.5 <= aspect <= 2.0:
        return ElementType.SWITCH

    return ElementType.UNKNOWN


def _deduplicate_boxes(boxes: list[ElementBox]) -> list[ElementBox]:
    """
    Remove boxes that are fully contained within another (nested elements).
    Keep the larger (parent) box.
    """
    if not boxes:
        return boxes

    # Sort by area descending
    sorted_boxes = sorted(boxes, key=lambda b: b.area, reverse=True)
    result: list[ElementBox] = []

    for box in sorted_boxes:
        # Check if this box is contained in any already-accepted box
        contained = False
        for accepted in result:
            if (
                box.x >= accepted.x
                and box.y >= accepted.y
                and (box.x + box.w) <= (accepted.x + accepted.w)
                and (box.y + box.h) <= (accepted.y + accepted.h)
            ):
                contained = True
                break
        if not contained:
            result.append(box)

    # Re-assign element IDs in order
    for i, box in enumerate(result):
        box.element_id = f"element_{i}"

    return result


def _count_elements_in_cell(boxes: list[ElementBox], cell: GridZone) -> int:
    """Count how many element boxes overlap with a grid cell."""
    count = 0
    for box in boxes:
        # Check bounding-box overlap
        ox = max(0, min(box.x + box.w, cell.x + cell.w) - max(box.x, cell.x))
        oy = max(0, min(box.y + box.h, cell.y + cell.h) - max(box.y, cell.y))
        if ox > 0 and oy > 0:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

def _save_debug_image(
    img_rgb: np.ndarray,
    boxes: list[ElementBox],
    zones: FunctionalZones,
    grid_zones: list[GridZone],
    original_path: Path,
) -> None:
    """Draw detected boxes and zone boundaries, save as _debug.png next to original."""
    # Uses only cv2 for drawing — no matplotlib dependency.

    img_draw = img_rgb.copy()
    h, w = img_rgb.shape[:2]

    # Draw grid zone boundaries
    rows = max(gz.row for gz in grid_zones) + 1
    cols = max(gz.col for gz in grid_zones) + 1
    cell_h = h // rows
    cell_w = w // cols

    for gz in grid_zones:
        color = (
            int(gz.dominant_color[1:3], 16),
            int(gz.dominant_color[3:5], 16),
            int(gz.dominant_color[5:7], 16),
        )
        cv2.rectangle(img_draw, (gz.x, gz.y), (gz.x + gz.w, gz.y + gz.h), color, 1)

    # Draw functional zone boundaries
    zone_colors = {
        ZoneType.STATUS_BAR: (100, 100, 255),
        ZoneType.APP_BAR: (255, 180, 100),
        ZoneType.CONTENT_AREA: (100, 200, 100),
        ZoneType.NAV_BAR: (255, 100, 100),
    }
    for zone_attr in ["status_bar", "app_bar", "content_area", "nav_bar"]:
        zone = getattr(zones, zone_attr, None)
        if zone is None:
            continue
        color = zone_colors.get(zone.zone_type, (200, 200, 200))
        cv2.rectangle(
            img_draw,
            (zone.x, zone.y),
            (zone.x + zone.w, zone.y + zone.h),
            color,
            2,
        )

    # Draw element boxes
    type_colors = {
        ElementType.ICON: (255, 200, 0),
        ElementType.BUTTON: (0, 200, 255),
        ElementType.TEXT: (150, 150, 150),
        ElementType.CARD: (0, 255, 150),
        ElementType.SWITCH: (200, 0, 200),
        ElementType.UNKNOWN: (100, 100, 100),
    }
    for box in boxes:
        color = type_colors.get(box.element_type, (100, 100, 100))
        cv2.rectangle(
            img_draw,
            (box.x, box.y),
            (box.x + box.w, box.y + box.h),
            color,
            2,
        )
        cv2.putText(
            img_draw,
            box.element_type.value[:4],
            (box.x + 2, box.y + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
        )

    debug_path = original_path.parent / f"{original_path.stem}_debug.png"
    cv2.imwrite(str(debug_path), cv2.cvtColor(img_draw, cv2.COLOR_RGB2BGR))
    print(f"[zone_detector] Debug image saved to: {debug_path}")


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 1: Zone Detector")
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument(
        "--grid",
        type=str,
        default="3,4",
        help="Grid size as rows,cols (e.g. 3,4)",
    )
    parser.add_argument("--debug", action="store_true", help="Save debug image")
    args = parser.parse_args()

    rows, cols = map(int, args.grid.split(","))
    result = detect_zones(args.image, grid_size=(rows, cols), debug_image=args.debug)

    print(f"\n=== Zone Detection Result ===")
    print(f"Image: {result.image_path} ({result.image_width}×{result.image_height})")
    print(f"Grid: {result.grid_size[0]}×{result.grid_size[1]} = {len(result.grid_zones)} cells")
    print(f"Elements detected: {len(result.element_boxes)}")

    print("\n--- Functional Zones ---")
    for zone_attr in ["status_bar", "app_bar", "content_area", "nav_bar"]:
        zone = getattr(result.functional_zones, zone_attr, None)
        if zone:
            print(f"  {zone.zone_type.value:20s}  y={zone.y:4d}  h={zone.h:4d}  w={zone.w}")

    print("\n--- Element Boxes (first 20) ---")
    for box in result.element_boxes[:20]:
        print(f"  {box.element_id:12s}  type={box.element_type.value:10s}  "
              f"x={box.x:4d}  y={box.y:4d}  w={box.w:4d}  h={box.h:4d}")

    if len(result.element_boxes) > 20:
        print(f"  ... and {len(result.element_boxes) - 20} more")
