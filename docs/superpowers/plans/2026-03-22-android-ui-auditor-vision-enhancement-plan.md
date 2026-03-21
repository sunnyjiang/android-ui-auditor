# Implementation Plan: Android UI Auditor — Vision Enhancement

**Date:** 2026-03-22
**Spec:** `2026-03-21-android-ui-auditor-vision-enhancement-design.md`
**Status:** Ready for Implementation

---

## Overview

Build a `VisionAndroidUIAuditor` class that accepts a screenshot path, performs CV-based zone detection, extracts element properties via Claude Vision, scores 13 design dimensions, compares zones, and outputs a JSON + HTML report.

**Estimated total files:** 6 new Python modules + 1 data model file
**Estimated dependencies:** anthropic, opencv-python, pillow, pandas, pydantic, numpy, requests, plotly, kaleido

---

## Phase Dependencies

```
Phase 1 (zone_detector.py)
       │
       ▼
Phase 2 (vision_client.py)     ← depends on ZoneDetectionResult from Phase 1
       │
       ▼
Phase 3 (evaluator.py)         ← depends on ElementAnalysis from Phase 2
       │
       ▼
Phase 4 (zone_comparator.py)    ← depends on ElementAnalysis from Phase 2 + scores from Phase 3
       │
       ▼
Phase 5 (report_generator.py)   ← depends on all above
       │
       ▼
Phase 6 (vision_analyzer.py)    ← orchestrates everything
```

---

## Phase 1: zone_detector.py

**Purpose:** Accept image path, return grid zones, functional zones, and element bounding boxes.

### 1.1 Grid Zones
- [ ] Read image with OpenCV, get dimensions (W × H)
- [ ] Divide into `grid_size` cells (default 3×4)
- [ ] Per cell compute: element count, dominant color (via KMeans or histogram), whitespace ratio (white pixel %)
- [ ] Return list of `GridZone(id, row, col, x, y, w, h, element_count, dominant_color, whitespace_ratio)`

### 1.2 Functional Zone Detection
- [ ] Detect StatusBar: top ~5% of image height, contains time/battery/signal pixels
- [ ] Detect AppBar: immediately below StatusBar, contains large bold text region or search icon
- [ ] Detect NavBar: bottom ~8% of image height, contains 3 circle/recent/home/back icons
- [ ] Detect ContentArea: area between AppBar and NavBar
- [ ] Return `FunctionalZones(status_bar, app_bar, content_area, nav_bar)` each with (x, y, w, h)

### 1.3 UI Element Detection (Bounding Boxes)
- [ ] Convert to grayscale, apply Canny edge detection
- [ ] Find contours, filter by area (remove tiny specks and full-screen)
- [ ] Classify contour types:
  - **Icon**: small (10×10 to 60×60 px), near-rectangular or circular, not containing text
  - **Button**: wider than tall (ratio > 1.5), solid fill
  - **Text**: tall thin bounding box, often grouped in lines
  - **Card**: large rectangle, aspect ratio ~16:9 to 4:3, has internal structure
- [ ] Assign unique `element_id` (e.g. `element_0`, `element_1`)
- [ ] Return `ZoneDetectionResult(grid_zones, functional_zones, element_boxes)`

### 1.4 Data Models
- [ ] Create `scripts/models.py` with Pydantic models:
  - `GridZone`, `FunctionalZone`, `ElementBox`, `ZoneDetectionResult`

### Acceptance Criteria
- Running `zone_detector.py` on the test screenshot produces non-overlapping bounding boxes covering all visible UI elements
- Grid zones partition the screen without overlap
- StatusBar, AppBar, ContentArea, NavBar are identified with reasonable accuracy on standard Android screenshots

---

## Phase 2: vision_client.py

**Purpose:** Wrap Anthropic Claude API for vision analysis. Takes image + zones + element boxes, returns per-element property dicts.

### 2.1 API Client
- [ ] Read `ANTHROPIC_API_KEY` from env or init param
- [ ] Build base64-encoded image payload from file path
- [ ] Send to Claude Vision with structured prompt requesting JSON output
- [ ] Parse response, handle rate limits and API errors gracefully
- [ ] Return `ElementAnalysis(element_id, properties: dict)` per element

### 2.2 Element Property Extraction Prompt
- [ ] Design prompt template asking Claude to return, per element:
  - type, background_hex, foreground_hex, opacity
  - font_family, font_size_sp, font_weight, text_content
  - padding (all 4 sides), border_radius, border_color
  - shadow (best effort), gradient (best effort)
  - contrast_ratio, wcag_level, touch_target_dp
- [ ] Send each element's cropped sub-image + bounding box context
- [ ] Parse and validate returned JSON, fill missing fields with `None` or `"unknown"`

### 2.3 Batch Processing
- [ ] Claude has image size limits; if image > 5MB, resize before sending
- [ ] Batch elements (max 10 per API call) to reduce API calls
- [ ] Cache results keyed by element_id to avoid re-analysis

### Acceptance Criteria
- `vision_client.py` on the test screenshot returns structured property dicts for ≥80% of detected elements
- Each property dict contains all fields from the Element Properties table (Section 3.3 of spec)

---

## Phase 3: evaluator.py

**Purpose:** Score all 13 dimensions from element properties + zone data.

### 3.1 Scoring Engine
- [ ] Implement per-dimension scoring functions per Section 3.4 rubric of the spec:
  - `score_consistency(elements) → int`
  - `score_accessibility(elements) → int`
  - `score_aesthetics(elements, zones) → int`
  - `score_performance(elements) → int`
  - `score_usability(elements) → int`
  - `score_brand(elements, brand_guidelines) → int`
  - `score_responsive(elements) → int`
  - `score_navigation(zones) → int`
  - `score_info_arch(zones) → int`
  - `score_interaction(elements) → int`
  - `score_discovery(zones) → int`
  - `score_operability(elements) → int`
  - `score_emotional(elements) → int`

### 3.2 Overall Score + Compliance
- [ ] Compute `overall_score = mean(all 13 dimension scores)`
- [ ] Map to `compliance_status` per Section 3.6 table

### 3.3 Improvement Plan Generation
- [ ] For each dimension with score < 70, generate an `ImprovementItem`
- [ ] `priority = "high"` if score < 50, `"medium"` if 50–59, `"low"` if 60–69
- [ ] `expected_score_gain` = subjective estimate (0–20)
- [ ] Group affected elements by issue type to avoid duplicate suggestions

### Acceptance Criteria
- Running evaluator on test screenshot produces scores that match manual inspection
- Improvement plan contains at most one suggestion per dimension (deduped)
- `overall_score` is the arithmetic mean of 13 dimensions

---

## Phase 4: zone_comparator.py

**Purpose:** Cross-zone comparison analysis.

### 4.1 Horizontal Row Comparison
- [ ] Group elements by approximate Y coordinate (within 10px = same row)
- [ ] Per row: compute height variance, width variance of elements
- [ ] Flag row if height deviation > 20%
- [ ] Return `RowComparison(row_id, elements, height_variance, width_variance, flagged)`

### 4.2 Vertical Column Comparison
- [ ] Group elements by approximate X coordinate (within 10px = same column)
- [ ] Per column: compute width variance, gap irregularity (std dev of inter-element gaps)
- [ ] Flag column if gap irregularity > 15%
- [ ] Return `ColumnComparison(col_id, elements, width_variance, gap_irregularity, flagged)`

### 4.3 Functional Zone Contrast
- [ ] Per functional zone: compute `density = element_count / zone_area`
- [ ] Per functional zone: compute `whitespace_ratio`
- [ ] Compute visual weight per zone (sum of element bounding box areas / zone area)
- [ ] Return `ZoneContrast(zone_id, density, whitespace_ratio, visual_weight)`

### 4.4 Grid Heatmap
- [ ] For each grid cell: compute heatmap values (element density, color temperature)
- [ ] Color temperature: classify dominant color as warm/cool/neutral via hue analysis
- [ ] Return `GridHeatmap(cells: list[dict])` with per-cell color-coded values

### Acceptance Criteria
- Horizontal comparison correctly identifies rows with >20% height variance
- Zone density computation matches manual calculation on test screenshot
- Heatmap cell count equals grid_rows × grid_cols

---

## Phase 5: report_generator.py

**Purpose:** Generate JSON report + standalone HTML visualization.

### 5.1 JSON Report
- [ ] Assemble all results into `AuditReport` Pydantic model
- [ ] Serialize to JSON with proper datetime formatting
- [ ] Save to `{output_dir}/audit_report.json`

### 5.2 HTML Report
- [ ] Load Plotly.js from CDN (no server needed)
- [ ] Build HTML with sections:
  - **Header**: screenshot thumbnail, overall score, compliance badge
  - **Category Scores**: horizontal bar chart (13 bars, color-coded by score range)
  - **Zone Comparison**: table of row/column flagged issues
  - **Grid Heatmap**: annotated heatmap using `plotly.figure_factory.create_annotated_heatmap`
  - **Element Inspector**: clickable list of elements showing properties on click
  - **Improvement Plan**: priority-sorted table with dimension/issue/suggestion
- [ ] Use dark theme CSS matching the design aesthetic
- [ ] Save to `{output_dir}/audit_report.html`

### Acceptance Criteria
- HTML report opens in browser with no external network requests (Plotly from CDN)
- All charts render with correct data from the test screenshot run
- Clicking an element in the element list shows its property card

---

## Phase 6: vision_analyzer.py

**Purpose:** Main entry point, orchestrates all phases.

### 6.1 VisionAndroidUIAuditor Class
- [ ] Implement `__init__` accepting: `anthropic_api_key`, `claude_model`, `grid_size`, `brand_guidelines`
- [ ] Implement `analyze_screenshot(image_path, output_dir=None) → AuditReport`
  - Call zone_detector → vision_client → evaluator → zone_comparator → report_generator
  - Return `AuditReport` (Pydantic model)
  - If `output_dir` set, save JSON + HTML there
- [ ] Implement `analyze_zones_only(image_path) → ZoneDetectionResult`
- [ ] Implement `analyze_elements(image_path, zones) → list[ElementAnalysis]`

### 6.2 Pydantic Models
- [ ] Define `AuditReport` model with all fields from Section 3.6
- [ ] Define `ImprovementItem` model with fields: dimension, priority, issue, suggestion, affected_elements, expected_score_gain

### 6.3 CLI Entry Point
- [ ] Add `if __name__ == "__main__"` block or separate `cli.py`:
  - Parse `--image` argument
  - Read `ANTHROPIC_API_KEY` from env
  - Call `auditor.analyze_screenshot(args.image, args.output)`
  - Print summary to stdout

### Acceptance Criteria
- `python vision_analyzer.py --image /path/to/screenshot.png --output ./report` produces both JSON and HTML
- `analyze_zones_only` runs without API key (no network calls)
- Running on test screenshot completes in <60s (excluding Claude API latency)

---

## File Structure (Final)

```
android-ui-auditor/scripts/
├── main.py              # Existing (unchanged)
├── models.py            # NEW: shared Pydantic data models
├── zone_detector.py     # NEW: Phase 1
├── vision_client.py     # NEW: Phase 2
├── evaluator.py         # NEW: Phase 3
├── zone_comparator.py   # NEW: Phase 4
├── report_generator.py  # NEW: Phase 5
└── vision_analyzer.py   # NEW: Phase 6 (main entry point)
```

---

## Testing Strategy

| Phase | Test |
|-------|------|
| Phase 1 | Run on test screenshot, verify bounding boxes visually (save debug image with boxes drawn) |
| Phase 2 | Verify ≥80% elements return non-null properties; check API key validity |
| Phase 3 | Manual score inspection matches evaluator output |
| Phase 4 | Visual verification of heatmap on test screenshot |
| Phase 5 | Open generated HTML in browser, verify all sections render |
| Phase 6 | Full pipeline end-to-end, verify JSON schema compliance |

---

## Implementation Order

1. `models.py` — shared types (GridZone, ElementBox, AuditReport, etc.)
2. `zone_detector.py` — Phase 1 (no dependencies)
3. `vision_client.py` — Phase 2 (needs ZoneDetectionResult type from models)
4. `evaluator.py` — Phase 3 (needs ElementAnalysis from models)
5. `zone_comparator.py` — Phase 4 (needs ElementAnalysis)
6. `report_generator.py` — Phase 5 (needs all above)
7. `vision_analyzer.py` — Phase 6 (orchestrates all)

---

## Out of Scope Reminder

Per the spec, these are explicitly NOT implemented:
- YOLO / custom element detection model
- Animation property extraction
- Multi-screen flow analysis
- Figma/design file import
- Historical regression tracking
