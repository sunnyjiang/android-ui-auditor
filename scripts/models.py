"""
Shared Pydantic data models for VisionAndroidUIAuditor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ElementType(Enum):
    ICON = "icon"
    BUTTON = "button"
    TEXT = "text"
    CARD = "card"
    IMAGE = "image"
    SWITCH = "switch"
    SLIDER = "slider"
    INPUT = "input"
    NAVIGATION = "navigation"
    SCREEN = "screen"
    UNKNOWN = "unknown"


class ZoneType(Enum):
    STATUS_BAR = "status_bar"
    APP_BAR = "app_bar"
    CONTENT_AREA = "content_area"
    NAV_BAR = "nav_bar"


# ---------------------------------------------------------------------------
# Grid Zone
# ---------------------------------------------------------------------------


@dataclass
class GridZone:
    """A single cell in the N×M grid overlay on the screenshot."""

    id: str               # e.g. "grid_0_0"
    row: int              # 0-indexed row
    col: int              # 0-indexed column
    x: int                # top-left pixel x
    y: int                # top-left pixel y
    w: int                # pixel width
    h: int                # pixel height
    element_count: int = 0
    dominant_color: str = "#000000"   # hex
    whitespace_ratio: float = 0.0      # 0.0 – 1.0


# ---------------------------------------------------------------------------
# Functional Zone
# ---------------------------------------------------------------------------


@dataclass
class FunctionalZone:
    """A semantically-identified screen region."""

    zone_type: ZoneType
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h


@dataclass
class FunctionalZones:
    """All four functional zones for a screenshot."""

    status_bar: Optional[FunctionalZone] = None
    app_bar: Optional[FunctionalZone] = None
    content_area: Optional[FunctionalZone] = None
    nav_bar: Optional[FunctionalZone] = None


# ---------------------------------------------------------------------------
# Element Box
# ---------------------------------------------------------------------------


@dataclass
class ElementBox:
    """
    A detected UI element with its bounding box and estimated type.
    Coordinates are absolute pixels from the top-left corner of the image.
    """

    element_id: str
    x: int
    y: int
    w: int
    h: int
    element_type: ElementType = ElementType.UNKNOWN
    confidence: float = 0.0  # 0.0 – 1.0, how confident the classifier is

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def cx(self) -> int:
        """Center x."""
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        """Center y."""
        return self.y + self.h // 2

    @property
    def aspect_ratio(self) -> float:
        """Width / height ratio."""
        return self.w / max(self.h, 1)


# ---------------------------------------------------------------------------
# Zone Detection Result (Phase 1 output)
# ---------------------------------------------------------------------------


@dataclass
class ZoneDetectionResult:
    """Output of Phase 1: zone detection."""

    image_path: str
    image_width: int
    image_height: int
    grid_size: tuple[int, int]          # (rows, cols)
    grid_zones: list[GridZone] = field(default_factory=list)
    functional_zones: FunctionalZones = field(default_factory=FunctionalZones)
    element_boxes: list[ElementBox] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Element Analysis (Phase 2 output — filled by Claude Vision)
# ---------------------------------------------------------------------------


@dataclass
class ElementProperties:
    """Complete visual properties of a UI element."""

    # Basic
    element_type: str = "unknown"
    z_index: int = 0
    parent_zone: str = ""

    # Position
    anchor_x: str = ""   # "left" | "center" | "right"
    anchor_y: str = ""   # "top" | "middle" | "bottom"

    # Color
    background_hex: str = "#FFFFFF"
    foreground_hex: str = "#000000"
    accent_hex: str = "#000000"
    opacity: float = 1.0

    # Typography
    font_family: str = "unknown"
    font_size_sp: float = 0.0
    font_weight: str = "normal"
    line_height: float = 1.5
    letter_spacing: float = 0.0
    text_content: str = ""

    # Spacing
    padding_top: float = 0.0
    padding_right: float = 0.0
    padding_bottom: float = 0.0
    padding_left: float = 0.0
    margin_top: float = 0.0
    margin_right: float = 0.0
    margin_bottom: float = 0.0
    margin_left: float = 0.0
    gap_to_siblings: float = 0.0

    # Decoration
    border_radius_dp: float = 0.0
    border_width_dp: float = 0.0
    border_color: str = "#000000"
    box_shadow: str = ""       # human-readable description or JSON string
    gradient: str = ""          # human-readable or JSON
    blur_radius: float = 0.0

    # Accessibility
    contrast_ratio: float = 0.0
    wcag_level: str = ""       # "A" | "AA" | "AAA" | ""
    touch_target_dp: float = 0.0
    screen_reader_support: bool = False

    # Light & shadow (best-effort)
    shadow_direction: str = ""
    shadow_intensity: float = 0.0
    highlight_direction: str = ""
    specular_strength: float = 0.0


@dataclass
class ElementAnalysis:
    """Phase 2 output: vision analysis for a single element."""

    element_id: str
    properties: ElementProperties = field(default_factory=ElementProperties)


# ---------------------------------------------------------------------------
# Evaluation (Phase 3 output)
# ---------------------------------------------------------------------------


@dataclass
class CategoryScore:
    dimension: str
    score: int           # 0 – 100
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ImprovementItem:
    """A single improvement suggestion in the audit report."""

    dimension: str
    priority: str         # "high" | "medium" | "low"
    issue: str
    suggestion: str
    affected_elements: list[str] = field(default_factory=list)
    expected_score_gain: int = 0  # 0 – 20, subjective estimate


# ---------------------------------------------------------------------------
# Zone Comparison (Phase 4 output)
# ---------------------------------------------------------------------------


@dataclass
class RowComparison:
    row_id: int
    elements: list[str]          # element_ids
    height_variance: float       # 0.0 – 1.0 (CV)
    width_variance: float
    flagged: bool


@dataclass
class ColumnComparison:
    col_id: int
    elements: list[str]
    width_variance: float
    gap_irregularity: float
    flagged: bool


@dataclass
class ZoneContrast:
    zone_id: str
    density: float               # elements per 1000 px²
    whitespace_ratio: float
    visual_weight: float         # 0.0 – 1.0


@dataclass
class GridHeatmapCell:
    row: int
    col: int
    element_density: float        # 0.0 – 1.0
    color_temperature: str        # "warm" | "cool" | "neutral"
    whitespace_ratio: float


# ---------------------------------------------------------------------------
# Audit Report (Phase 5 output, final output)
# ---------------------------------------------------------------------------


@dataclass
class ZoneComparisonResult:
    horizontal_rows: list[RowComparison] = field(default_factory=list)
    vertical_columns: list[ColumnComparison] = field(default_factory=list)
    functional_zones: list[ZoneContrast] = field(default_factory=list)
    grid_heatmap: list[GridHeatmapCell] = field(default_factory=list)


@dataclass
class AuditReport:
    """Final output of VisionAndroidUIAuditor.analyze_screenshot()."""

    evaluation_timestamp: str
    screenshot_path: str
    overall_score: int                      # 0 – 100
    compliance_status: str                   # "完全符合" | "大部分符合" | "部分符合" | "较少符合" | "不符合"
    image_width: int
    image_height: int
    grid_size: tuple[int, int]

    # Zone detection (Phase 1)
    zone_detection: ZoneDetectionResult = field(default_factory=ZoneDetectionResult)

    # Element analysis (Phase 2)
    element_analysis: list[ElementAnalysis] = field(default_factory=list)

    # Category scores (Phase 3)
    category_scores: list[CategoryScore] = field(default_factory=list)
    improvement_plan: list[ImprovementItem] = field(default_factory=list)

    # Zone comparison (Phase 4)
    zone_comparison: ZoneComparisonResult = field(default_factory=ZoneComparisonResult)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON output."""
        def _convert(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _convert(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [_convert(i) for i in obj]
            if isinstance(obj, tuple) and not isinstance(obj, ElementType):
                return list(obj)
            return obj

        out = _convert(self)
        # Convert enums to values
        out["compliance_status"] = self.compliance_status
        out["grid_size"] = list(self.grid_size)
        return out
