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
- `claude_model: str` — Claude model to use (default: "claude-3-5-sonnet-latest")

**`brand_guidelines` schema (optional):**
```python
brand_guidelines = {
    "color": {
        "primary": "#3F51B5",
        "secondary": "#009688",
        "accent": "#FF9800",
        "background": "#FFFFFF",
        "text": "#212121"
    },
    "typography": {
        "font_family": "Roboto",
        "font_size": {"small": 12, "normal": 14, "medium": 16, "large": 20}
    },
    "spacing": {"base": 8, "small": 4, "medium": 8, "large": 16},
    "touch_target": 48  # dp minimum
}
```

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
| Category | Properties | Feasibility |
|----------|-----------|-------------|
| **Basic** | type, id, z_index, parent_zone | Guaranteed |
| **Position** | x, y, width, height, anchor (left/center/right, top/middle/bottom) | Guaranteed |
| **Color** | background_hex, foreground_hex, accent_hex, opacity | Guaranteed |
| **Typography** | font_family, font_size_sp, font_weight, line_height, letter_spacing, text_content | Guaranteed |
| **Spacing** | padding_dp (top/right/bottom/left), margin_dp, gap_to_siblings | Guaranteed |
| **Decoration** | border_radius_dp, border_width_dp, border_color | Guaranteed |
| **Accessibility** | contrast_ratio, wcag_level (A/AA/AAA), touch_target_dp, screen_reader_support | Guaranteed |
| **Shadow (best effort)** | box_shadow (offset_x, offset_y, blur_radius, spread, color) | Best estimate via shadow detection |
| **Gradient (best effort)** | gradient type, dominant colors, direction | Best estimate via color distribution analysis |
| **Light direction (best effort)** | shadow_direction, highlight_side | Best estimate via shape/lighting cues |

> **Note:** Animation-related properties (`duration_ms`, `easing`) cannot be extracted from a static screenshot and are out of scope. `gradient` and `shadow` are marked best effort because they require inference from visual cues rather than explicit measurement.

### 3.4 Evaluation Categories (13 dimensions)

Each category is scored 0–100. Scores are computed from element-level property checks, then averaged across all elements.

| Category | Key Checks | Scoring Rubric |
|----------|-----------|----------------|
| **Consistency** | Color hex variance across same-type elements; font_size/weight variance; spacing (padding/margin) deviation from 8dp grid | Variance < 5% → 90–100; < 15% → 70–89; < 30% → 50–69; > 30% → 0–49 |
| **Accessibility** | Contrast ratio ≥ 4.5:1 (AA) → pass; ≥ 7:1 (AAA) → excellent; touch target ≥ 48dp → pass | ≥ 90% elements pass WCAG AA → 90–100; ≥ 80% → 70–89; ≥ 60% → 50–69; < 60% → 0–49 |
| **Aesthetics** | Visual weight distribution balance; whitespace ratio (ideal 20–40%); dominant color harmony via temperature analysis | Balanced weight + ideal whitespace → 90–100; minor imbalance → 70–89; significant imbalance → 50–69; chaotic → 0–49 |
| **Performance** | Total element count; nesting depth (ideal ≤ 4 levels); bounding box overlap ratio | < 50 elements, depth ≤ 4 → 90–100; < 80, depth ≤ 6 → 70–89; < 120 → 50–69; > 120 → 0–49 |
| **Usability** | Touch target ≥ 48dp; interactive elements have visible feedback; spacing between targets ≥ 8dp | 100% targets pass → 90–100; ≥ 85% → 70–89; ≥ 70% → 50–69; < 70% → 0–49 |
| **Brand Consistency** | Primary/secondary/accent color delta from brand guidelines ≤ 10%; font family match | Delta ≤ 5% → 90–100; ≤ 10% → 70–89; ≤ 20% → 50–69; > 20% → 0–49 |
| **Responsive Design** | Content within safe area (status bar, nav bar not overlapped); text not clipped | All content in safe area → 90–100; minor overflow → 70–89; significant → 50–69; clipped → 0–49 |
| **Navigation** | AppBar present; nav bar icons visible and consistent; back navigation element exists | All present → 90–100; 1 missing → 70–89; 2 missing → 50–69; > 2 → 0–49 |
| **Information Architecture** | Logical grouping of related items; section headers present; no orphan items | Well-grouped with headers → 90–100; mostly grouped → 70–89; some orphans → 50–69; chaotic → 0–49 |
| **Interaction Design** | All interactive elements have touch targets; state indicators (selected/disabled) visible | 100% → 90–100; ≥ 85% → 70–89; ≥ 70% → 50–69; < 70% → 0–49 |
| **Discovery** | Key actions not hidden; no content requiring scroll to be visible at first glance; search/filter present if > 10 items | All critical content visible → 90–100; mostly visible → 70–89; some hidden → 50–69; key content hidden → 0–49 |
| **Operability** | Input fields ≥ 44dp height; scroll indicator present if content overflows; no overlapping touch targets | All pass → 90–100; ≥ 85% → 70–89; ≥ 70% → 50–69; < 70% → 0–49 |
| **Emotional Design** | Color palette mood (warm/cool/neutral); visual complexity (element density vs whitespace); icon style consistency | Cohesive palette + balanced complexity → 90–100; mostly cohesive → 70–89; mixed → 50–69; jarring → 0–49 |

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

**`compliance_status` values:**
| Value | Criteria |
|-------|----------|
| `完全符合` | overall_score ≥ 90 |
| `大部分符合` | overall_score ≥ 75 |
| `部分符合` | overall_score ≥ 60 |
| `较少符合` | overall_score ≥ 40 |
| `不符合` | overall_score < 40 |

**`improvement_plan` item schema:**
```json
{
  "dimension": "Accessibility",
  "priority": "high",       // "high" | "medium" | "low"
  "issue": "文字与背景对比度不足，当前为 3.2:1，低于 WCAG AA 要求的 4.5:1",
  "suggestion": "将文字颜色从 #757575 调整为 #616161 或更深色",
  "affected_elements": ["wifi_item", "mobile_network_item"],
  "expected_score_gain": 8
}
```

```json
{
  "evaluation_timestamp": "2026-03-21T...",
  "screenshot_path": "/path/to/screenshot.png",
  "overall_score": 85,
  "compliance_status": "大部分符合",
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
  "improvement_plan": [
    {
      "dimension": "Accessibility",
      "priority": "high",
      "issue": "文字与背景对比度不足",
      "suggestion": "加深文字颜色",
      "affected_elements": ["wifi_item"],
      "expected_score_gain": 8
    }
  ]
}
```

### 3.7 HTML Report
- Standalone HTML file with interactive visualizations (no server required)
- **Visualization library:** Plotly.js (CDN) — bar charts, heatmaps, scatter plots
- Grid heatmap with color-coded zones
- Bar chart for category scores
- Element property inspector on click
- Zone comparison tables
- Dark/light theme support

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

| Phase | 内容 |
|-------|------|
| **Phase 1** | `zone_detector.py` — Grid + functional zone detection with OpenCV |
| **Phase 2** | `vision_client.py` — Claude Vision API wrapper, element property extraction |
| **Phase 3** | `evaluator.py` — 13-dimension scoring engine |
| **Phase 4** | `zone_comparator.py` — Horizontal/vertical/heatmap comparison |
| **Phase 5** | `report_generator.py` — JSON + HTML report with Plotly visualizations |
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
        """Phase 1: zone detection only (grid + functional zones), no vision analysis."""
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
pillow>=10.0.0
pandas>=2.0.0
pydantic>=2.0.0
numpy>=1.24.0
requests>=2.31.0
plotly>=5.18.0   # For HTML report visualization (Kaleido for static export)
kaleido>=0.2.1   # Plotly static image export
```

> **Note:** Ultralytics/YOLO is excluded from Phase 1 scope. Zone detection uses OpenCV contour detection + edge analysis. YOLO may be revisited as a future extension.

---

## 8. Out of Scope (Future Extensions)

The following are explicitly **out of scope** for the current implementation:

- **YOLO model** — Using a custom-trained UI element detector. Phase 1 uses OpenCV contour detection + Claude Vision for element detection. YOLO can be revisited as a future optimization.
- **Multi-screen flow** — Analyzing transitions between screens (not just single screenshot). Single screenshot is the unit of analysis.
- **Design system import** — Parsing Figma/Knockout file as brand guidelines input. Manual `brand_guidelines` dict is the input format.
- **Historical tracking** — Comparing screenshots over time to detect regression. Each run is a standalone snapshot.

---

## 9. Approved Design Decisions

| Decision | Choice |
|----------|--------|
| Input method | 直接图片路径，拍照即分析 |
| Vision tech | CV (OpenCV) + Claude Vision (Anthropic) 混合 |
| Multi-modal AI | Claude (Anthropic) |
| Analysis depth | 完整级（颜色/尺寸/文字/间距/装饰/无障碍，光影/渐变 best effort，动画除外） |
| Comparison modes | 全部（网格/功能区/同行/同列） |
| Output format | JSON + 交互式 HTML（Plotly.js）可视化报告 |
| HTML library | Plotly.js via CDN（无外部服务器依赖） |
