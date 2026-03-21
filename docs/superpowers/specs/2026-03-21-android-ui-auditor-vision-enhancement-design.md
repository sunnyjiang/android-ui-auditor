# Android UI Auditor — Vision-Enhanced Design

**Date:** 2026-03-21
**Status:** Draft
**Version:** 1.0

---

## 1. Overview

**What:** Enhance the `android-ui-auditor` skill to accept a screenshot path as input, automatically extract UI elements via CV + Claude Vision, and generate a comprehensive multi-dimensional audit report with zone-based comparison.

**Why:** The current skill relies on manually constructed `ui_data` JSON, lacks real image analysis, and cannot perform visual property extraction (colors, sizes, shadows, gradients, etc.) or zone-based layout comparison.

---

## 2. Architecture

### 2.1 Processing Pipeline

```
[UI Screenshot]
    │
    ▼
[Step 1: CV Zone Detection]
    ├── Grid Zone: Divide into N×M grid (configurable, default 3×4)
    ├── Functional Zone: Identify StatusBar / AppBar / Content / NavBar
    └── Element Detection: Bounding boxes for icons, buttons, text, cards
    │
    ▼
[Step 2: Claude Vision Analysis]
    └── For each zone and detected element:
        ├── Extract visual properties (color, size, position, typography, etc.)
        ├── Evaluate against design principles
        └── Generate per-element and per-zone scores
    │
    ▼
[Step 3: Cross-Zone Comparison]
    ├── Horizontal row comparison: height/size consistency
    ├── Vertical column comparison: width/spacing consistency
    ├── Functional zone contrast: density, visual weight distribution
    └── Grid heatmap: element density, color density, whitespace ratio
    │
    ▼
[Step 4: Report Generation]
    ├── Overall score + compliance status
    ├── Per-dimension scores (13 categories)
    ├── Zone comparison results
    └── Actionable improvement suggestions
```

### 2.2 Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Image Processing | OpenCV + Ultralytics (YOLO) | Zone segmentation, element detection |
| Vision Analysis | Anthropic Claude API (Vision) | Per-element property extraction |
| Core Logic | Python 3.9+, pandas, pydantic | Data modeling, scoring engine |
| Report | JSON + HTML visualization | Structured output + interactive report |

---

## 3. Functionality Specification

### 3.1 Input

**Primary input:** Screenshot file path (PNG/JPG)

```python
# Usage
auditor = VisionAndroidUIAuditor(anthropic_api_key="sk-...")
report = auditor.analyze_screenshot("/path/to/screenshot.png")
```

**Optional parameters:**
- `grid_size: tuple[int, int]` — Grid division (default: (3, 4))
- `brand_guidelines: dict` — Custom brand color/typography rules
- `claude_model: str` — Claude model to use (default: "claude-3-5-sonnet-latest")

### 3.2 Zone Detection (Step 1)

#### Grid Zones
- Divide screenshot into N×M equal grid cells
- Per cell compute:
  - Element count (icon, button, text, card)
  - Average background color (dominant color)
  - Whitespace ratio (transparent/white area %)
  - Visual weight (sum of bounding box areas / cell area)

#### Functional Zones
Automatically detect these standard Android screen regions:
- **StatusBar** — Top system bar (time, battery, signal)
- **AppBar** — Title bar with optional search/action icons
- **ContentArea** — Main scrollable content
- **NavBar** — Bottom navigation (3-button or gesture)

#### UI Element Detection
Detect bounding boxes for:
- Icon (wifi, bluetooth, etc.)
- Button / Toggle
- Text label
- Card / Section divider
- Image / Logo

### 3.3 Vision Analysis (Step 2)

Each detected element and zone is analyzed via Claude Vision with the following properties:

#### Element Properties (Complete Level)
| Category | Properties |
|----------|-----------|
| **Basic** | type, id, z_index, parent_zone |
| **Position** | x, y, width, height, anchor (left/center/right, top/middle/bottom) |
| **Color** | background_hex, foreground_hex, accent_hex, opacity |
| **Typography** | font_family, font_size_sp, font_weight, line_height, letter_spacing, text_content |
| **Spacing** | padding_dp (top/right/bottom/left), margin_dp, gap_to_siblings |
| **Decoration** | border_radius_dp, border_width_dp, border_color, box_shadow (offset_x, offset_y, blur_radius, spread, color), gradient (type, colors, direction), blur_radius |
| **Accessibility** | contrast_ratio, wcag_level (A/AA/AAA), touch_target_dp, screen_reader_support |
| **Light & Shadow** | shadow_direction, shadow_intensity, highlight_direction, specular_strength |
| **Animation** | duration_ms, easing, interaction_feedback |

### 3.4 Evaluation Categories (13 dimensions)

| Category | Evaluation Focus |
|----------|-----------------|
| Consistency | Color system, typography, spacing, icon system, visual hierarchy |
| Accessibility | WCAG 2.1 compliance, color contrast, text readability, touch targets |
| Aesthetics | Visual balance, color harmony, hierarchy, whitespace usage |
| Performance | Element count, nesting depth, rendering complexity |
| Usability | Touch target size, interaction flow, feedback clarity |
| Brand Consistency | Custom brand guidelines compliance |
| Responsive Design | Screen density adaptation, safe area handling |
| Navigation | Bottom nav / top bar clarity, back flow |
| Information Architecture | Grouping logic, content prioritization |
| Interaction Design | Touch targets, gesture areas, state transitions |
| Discovery | Content findability, action visibility |
| Operability | Input field sizing, scroll behavior |
| Emotional Design | Color psychology, visual delight |

### 3.5 Cross-Zone Comparison (Step 3)

#### Horizontal Row Comparison
- Identify rows (by grid or functional zone)
- Compare element height uniformity across the row
- Flag if same-row elements have >20% height difference

#### Vertical Column Comparison
- Identify columns (by grid)
- Compare element width and horizontal spacing consistency
- Flag if same-column elements have irregular gaps

#### Functional Zone Contrast
- Content density: elements per zone area
- Visual weight distribution across zones
- Whitespace ratio per zone

#### Grid Heatmap
- Element density map (color-coded)
- Color temperature map (warm/cool dominant per cell)
- Whitespace ratio heatmap

### 3.6 Report Output

```json
{
  "evaluation_timestamp": "2026-03-21T...",
  "screenshot_path": "/path/to/screenshot.png",
  "overall_score": 85,
  "compliance_status": "部分符合",
  "zone_detection": {
    "grid_zones": [...],
    "functional_zones": {...}
  },
  "element_analysis": [...],
  "category_scores": {...},
  "zone_comparison": {
    "horizontal_rows": [...],
    "vertical_columns": [...],
    "functional_zones": {...},
    "grid_heatmap": {...}
  },
  "improvement_plan": [...]
}
```

### 3.7 HTML Report
- Standalone HTML file with interactive visualizations
- Grid heatmap with color-coded zones
- Bar chart for category scores
- Element property inspector on click
- Zone comparison tables

---

## 4. File Structure

```
android-ui-auditor/
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-03-21-android-ui-auditor-vision-enhancement-design.md
├── scripts/
│   ├── main.py                    # Existing auditor (keep as-is)
│   ├── vision_analyzer.py         # NEW: Vision analysis entry point
│   ├── zone_detector.py            # NEW: CV zone detection
│   ├── vision_client.py            # NEW: Claude Vision API wrapper
│   ├── evaluator.py                # NEW: Scoring engine (13 dimensions)
│   ├── zone_comparator.py          # NEW: Cross-zone comparison
│   └── report_generator.py         # NEW: JSON + HTML report output
├── skill.md
└── reference/
    └── README.md
```

---

## 5. Implementation Priority

| Phase |内容 |
|-------|------|
| **Phase 1** | `vision_client.py` — Claude Vision API integration, element property extraction |
| **Phase 2** | `zone_detector.py` — Grid + functional zone detection with OpenCV |
| **Phase 3** | `evaluator.py` — 13-dimension scoring engine |
| **Phase 4** | `zone_comparator.py` — Horizontal/vertical/heatmap comparison |
| **Phase 5** | `report_generator.py` — JSON + HTML report with visualizations |
| **Phase 6** | `vision_analyzer.py` — Orchestrates all phases into single `analyze_screenshot()` API |

---

## 6. API Design

```python
class VisionAndroidUIAuditor:
    def __init__(
        self,
        anthropic_api_key: str,
        claude_model: str = "claude-3-5-sonnet-latest",
        grid_size: tuple[int, int] = (3, 4),
        brand_guidelines: Optional[dict] = None
    ):
        ...

    def analyze_screenshot(
        self,
        image_path: str,
        output_dir: Optional[str] = None
    ) -> AuditReport:
        """
        Full pipeline: zone detection → vision analysis → comparison → report
        Returns AuditReport (pydantic model) and optionally saves HTML report.
        """
        ...

    def analyze_zones_only(
        self,
        image_path: str
    ) -> ZoneDetectionResult:
        """Phase 1 only: zone detection without vision analysis."""
        ...

    def analyze_elements(
        self,
        image_path: str,
        zones: ZoneDetectionResult
    ) -> list[ElementAnalysis]:
        """Phase 2: vision analysis of detected zones and elements."""
        ...
```

---

## 7. Dependencies

```
anthropic>=0.18.0
opencv-python>=4.9.0
ultralytics>=8.1.0   # YOLO for element detection (optional, fallback to Vision-only)
pillow>=10.0.0
pandas>=2.0.0
pydantic>=2.0.0
numpy>=1.24.0
requests>=2.31.0
```

---

## 8. Open Questions / Future Extensions

- **YOLO model** — Training a custom UI element detector vs using general-purpose detection. Consider RCNN vs YOLO trade-off.
- **Multi-screen flow** — Analyzing transitions between screens (not just single screenshot).
- **Design system import** — Parsing Figma/Knockout file as brand guidelines input.
- **Historical tracking** — Comparing screenshots over time to detect regression.

---

## 9. Approved Design Decisions

| Decision | Choice |
|----------|--------|
| Input method | 直接图片路径，拍照即分析 |
| Vision tech | CV (OpenCV/YOLO) + Claude Vision (Anthropic) 混合 |
| Multi-modal AI | Claude (Anthropic) |
| Analysis depth | 完整级（所有属性包括光影/渐变/动画） |
| Comparison modes | 全部（网格/功能区/同行/同列） |
| Output format | JSON + 交互式 HTML 可视化报告 |
