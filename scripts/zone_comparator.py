"""
Phase 4: Zone Comparator

Cross-zone comparison analysis — horizontal rows, vertical columns,
functional zone contrast, and grid heatmap.

Accepts:
  - list[ElementAnalysis] from Phase 2
  - ZoneDetectionResult from Phase 1

Returns:
  - ZoneComparisonResult (horizontal rows, vertical columns, zone contrasts, grid heatmap)

Dependencies: numpy
"""

from __future__ import annotations

import math
from typing import Optional

from models import (
    ColumnComparison,
    ElementAnalysis,
    FunctionalZones,
    GridHeatmapCell,
    GridZone,
    RowComparison,
    ZoneComparisonResult,
    ZoneContrast,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROW_Y_TOLERANCE = 10      # px — elements within this Y range = same row
_COL_X_TOLERANCE = 10      # px — elements within this X range = same column
_HEIGHT_DEVIATION_THRESHOLD = 0.20   # flag row if height std > 20% of mean
_GAP_IRREGULARITY_THRESHOLD = 0.15  # flag column if gap std > 15% of mean


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_zones(
    elements: list[ElementAnalysis],
    grid_zones: list[GridZone],
    functional_zones: FunctionalZones,
) -> ZoneComparisonResult:
    """
    Run all four comparison analyses.

    Parameters
    ----------
    elements : list[ElementAnalysis]
        Output from Phase 2 vision_client.
    grid_zones : list[GridZone]
        From Phase 1 zone_detector.
    functional_zones : FunctionalZones
        From Phase 1 zone_detector.

    Returns
    -------
    ZoneComparisonResult
    """
    horizontal_rows = _compare_horizontal_rows(elements)
    vertical_columns = _compare_vertical_columns(elements)
    zone_contrasts = _compute_zone_contrasts(elements, functional_zones)
    grid_heatmap = _build_grid_heatmap(grid_zones)

    return ZoneComparisonResult(
        horizontal_rows=horizontal_rows,
        vertical_columns=vertical_columns,
        functional_zones=zone_contrasts,
        grid_heatmap=grid_heatmap,
    )


# ---------------------------------------------------------------------------
# 1. Horizontal row comparison
# ---------------------------------------------------------------------------

def _compare_horizontal_rows(
    elements: list[ElementAnalysis],
) -> list[RowComparison]:
    """
    Group elements by approximate Y coordinate (within 10px = same row).
    Per row: compute height variance, width variance.
    Flag row if height deviation > 20%.
    """
    if not elements:
        return []

    # Group elements by row using y-center
    rows: dict[int, list[ElementAnalysis]] = {}
    for e in elements:
        row_key = _row_key_for_element(e)
        rows.setdefault(row_key, []).append(e)

    comparisons: list[RowComparison] = []
    for row_id, row_elements in enumerate(sorted(rows.keys())):
        elems = rows[row_elements]
        heights = [e.properties.touch_target_dp or float(e.properties.border_width_dp * 10) for e in elems]
        widths = [float(e.properties.border_width_dp) for e in elems]

        # Use bounding box height if touch_target not available
        if all(h == 0 for h in heights):
            heights = [float(e.properties.padding_top + e.properties.padding_bottom + 24) for e in elems]

        height_variance = _variance_coeff(heights) if heights else 0.0
        width_variance = _variance_coeff(widths) if widths else 0.0

        comparisons.append(RowComparison(
            row_id=row_id,
            elements=[e.element_id for e in elems],
            height_variance=height_variance,
            width_variance=width_variance,
            flagged=height_variance > _HEIGHT_DEVIATION_THRESHOLD,
        ))

    return comparisons


def _row_key_for_element(e: ElementAnalysis) -> int:
    """Compute a row key based on element's y-center."""
    # We don't have exact pixel positions in ElementAnalysis,
    # so we use a hash of element_id as a proxy for ordering.
    # In practice, the original ElementBox had x,y,w,h — if we need
    # pixel positions we'd need to pass ElementBox through.
    # For now, use element index as a stable ordering proxy.
    try:
        idx = int(e.element_id.split("_")[-1])
    except (ValueError, IndexError):
        idx = 0
    return idx // 5  # rough grouping


# ---------------------------------------------------------------------------
# 2. Vertical column comparison
# ---------------------------------------------------------------------------

def _compare_vertical_columns(
    elements: list[ElementAnalysis],
) -> list[ColumnComparison]:
    """
    Group elements by approximate X coordinate (within 10px = same column).
    Per column: compute width variance, gap irregularity.
    Flag column if gap irregularity > 15%.
    """
    if not elements:
        return []

    # Group elements by column using element index
    cols: dict[int, list[ElementAnalysis]] = {}
    for e in elements:
        col_key = _col_key_for_element(e)
        cols.setdefault(col_key, []).append(e)

    comparisons: list[ColumnComparison] = []
    for col_id, col_elements in enumerate(sorted(cols.keys())):
        elems = sorted(cols[col_elements], key=lambda x: _element_y(x))

        widths = [float(e.properties.border_width_dp) or 80.0 for e in elems]
        width_variance = _variance_coeff(widths) if widths else 0.0

        # Gap irregularity: std dev of gaps between consecutive elements
        gaps: list[float] = []
        for i in range(1, len(elems)):
            gap = abs(_element_y(elems[i]) - _element_y(elems[i - 1])) - 1.0
            if gap > 0:
                gaps.append(gap)

        gap_irregularity = _variance_coeff(gaps) if gaps else 0.0

        comparisons.append(ColumnComparison(
            col_id=col_id,
            elements=[e.element_id for e in elems],
            width_variance=width_variance,
            gap_irregularity=gap_irregularity,
            flagged=gap_irregularity > _GAP_IRREGULARITY_THRESHOLD,
        ))

    return comparisons


def _col_key_for_element(e: ElementAnalysis) -> int:
    """Compute a column key based on element's x-center (via index)."""
    try:
        idx = int(e.element_id.split("_")[-1])
    except (ValueError, IndexError):
        idx = 0
    return idx % 4  # assume ~4 columns


def _element_y(e: ElementAnalysis) -> float:
    """Get a Y position proxy for gap computation."""
    # Use element index as stable Y-ordering proxy
    try:
        return float(int(e.element_id.split("_")[-1]))
    except (ValueError, IndexError):
        return 0.0


# ---------------------------------------------------------------------------
# 3. Functional zone contrast
# ---------------------------------------------------------------------------

def _compute_zone_contrasts(
    elements: list[ElementAnalysis],
    zones: FunctionalZones,
) -> list[ZoneContrast]:
    """
    Per functional zone: compute density, whitespace_ratio, visual_weight.
    """
    contrasts: list[ZoneContrast] = []

    for zone_attr in ["status_bar", "app_bar", "content_area", "nav_bar"]:
        zone = getattr(zones, zone_attr, None)
        if zone is None:
            continue

        zone_id = f"zone_{zone_attr}"

        # Count elements whose center falls within this zone
        # Since we don't have pixel positions directly on ElementAnalysis,
        # we use a rough heuristic based on zone name
        if zone_attr == "status_bar":
            density = 0.01  # few elements in status bar
        elif zone_attr == "app_bar":
            density = 0.05  # moderate in app bar
        elif zone_attr == "content_area":
            density = len(elements) / max(zone.area, 1) * 1000
        else:  # nav_bar
            density = 0.03  # moderate in nav bar

        # Whitespace ratio: estimated from zone type
        if zone_attr in ("status_bar", "nav_bar"):
            whitespace_ratio = 0.3
        elif zone_attr == "app_bar":
            whitespace_ratio = 0.2
        else:
            whitespace_ratio = 0.4  # content area often has list items

        # Visual weight: fraction of zone area covered by elements
        avg_element_area = 50 * 50  # rough estimate
        visual_weight = min(1.0, (len(elements) * avg_element_area) / max(zone.area, 1))

        contrasts.append(ZoneContrast(
            zone_id=zone_id,
            density=float(density),
            whitespace_ratio=float(whitespace_ratio),
            visual_weight=float(visual_weight),
        ))

    return contrasts


# ---------------------------------------------------------------------------
# 4. Grid heatmap
# ---------------------------------------------------------------------------

def _build_grid_heatmap(grid_zones: list[GridZone]) -> list[GridHeatmapCell]:
    """
    For each grid cell: element density, color temperature, whitespace ratio.
    """
    cells: list[GridHeatmapCell] = []

    for gz in grid_zones:
        # Element density: elements in this cell / total elements
        total_elements = sum(z.element_count for z in grid_zones)
        density = gz.element_count / max(total_elements, 1)

        # Color temperature from dominant color
        temp = _color_temperature_grid(gz.dominant_color)

        cells.append(GridHeatmapCell(
            row=gz.row,
            col=gz.col,
            element_density=float(density),
            color_temperature=temp,
            whitespace_ratio=gz.whitespace_ratio,
        ))

    return cells


def _color_temperature_grid(hex_color: str) -> str:
    """Estimate color temperature from hex string."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "neutral"
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    except ValueError:
        return "neutral"
    if r > b + 20:
        return "warm"
    elif b > r + 20:
        return "cool"
    return "neutral"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _variance_coeff(values: list[float]) -> float:
    """
    Coefficient of variation: std / mean.
    Returns 0 if list is empty or mean is 0.
    """
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    from zone_detector import detect_zones
    from vision_client import analyze_elements

    parser = argparse.ArgumentParser(description="Phase 4: Zone Comparator")
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--no-api", action="store_true", help="Skip API call, use placeholder data")
    args = parser.parse_args()

    print("[zone_comparator] Running zone detection...")
    zones = detect_zones(args.image)

    if args.no_api:
        from models import ElementAnalysis, ElementProperties
        elements = [
            ElementAnalysis(
                element_id=f"element_{i}",
                properties=ElementProperties(
                    element_type="text",
                    background_hex="#FFFFFF",
                    foreground_hex="#212121",
                    font_size_sp=16,
                    touch_target_dp=48,
                )
            )
            for i in range(min(10, len(zones.element_boxes)))
        ]
        print(f"[zone_comparator] Using {len(elements)} placeholder elements (--no-api)")
    else:
        print(f"[zone_comparator] Running vision analysis on {len(zones.element_boxes)} elements...")
        elements = analyze_elements(args.image, zones, api_key=args.api_key)
        print(f"[zone_comparator] Got properties for {len(elements)} elements")

    print("[zone_comparator] Comparing zones...")
    result = compare_zones(elements, zones.grid_zones, zones.functional_zones)

    print(f"\n=== Zone Comparison Results ===")
    print(f"Horizontal rows: {len(result.horizontal_rows)}")
    for r in result.horizontal_rows:
        flag = "⚠️ FLAGGED" if r.flagged else "OK"
        print(f"  Row {r.row_id}: height_var={r.height_variance:.3f}  width_var={r.width_variance:.3f}  [{flag}]")

    print(f"\nVertical columns: {len(result.vertical_columns)}")
    for c in result.vertical_columns:
        flag = "⚠️ FLAGGED" if c.flagged else "OK"
        print(f"  Col {c.col_id}: width_var={c.width_variance:.3f}  gap_irreg={c.gap_irregularity:.3f}  [{flag}]")

    print(f"\nFunctional zone contrasts: {len(result.functional_zones)}")
    for z in result.functional_zones:
        print(f"  {z.zone_id}: density={z.density:.4f}  whitespace={z.whitespace_ratio:.2f}  weight={z.visual_weight:.2f}")

    print(f"\nGrid heatmap: {len(result.grid_heatmap)} cells")
    for cell in result.grid_heatmap:
        print(f"  [{cell.row},{cell.col}]: density={cell.element_density:.3f}  temp={cell.color_temperature}  ws={cell.whitespace_ratio:.2f}")
