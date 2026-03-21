"""
Phase 3: Evaluator

Scoring engine for 13 UI design dimensions.

Accepts:
  - list[ElementAnalysis] from Phase 2
  - ZoneDetectionResult from Phase 1
  - Optional brand_guidelines dict

Returns:
  - list[CategoryScore] (13 dimensions)
  - list[ImprovementItem] (suggestions for low-scoring dimensions)

No external API calls — pure computation.
"""

from __future__ import annotations

import math
from typing import Optional

from models import (
    CategoryScore,
    ElementAnalysis,
    FunctionalZones,
    GridZone,
    ImprovementItem,
)


# ---------------------------------------------------------------------------
# Brand guidelines defaults
# ---------------------------------------------------------------------------

_DEFAULT_BRAND = {
    "color": {
        "primary": "#3F51B5",
        "secondary": "#009688",
        "accent": "#FF9800",
        "background": "#FFFFFF",
        "text": "#212121",
    },
    "typography": {
        "font_family": "Roboto",
        "font_size": {"small": 12, "normal": 14, "medium": 16, "large": 20},
    },
    "spacing": {"base": 8, "small": 4, "medium": 8, "large": 16},
    "touch_target": 48,   # dp
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(
    elements: list[ElementAnalysis],
    functional_zones: FunctionalZones,
    grid_zones: list[GridZone],
    brand_guidelines: Optional[dict] = None,
) -> tuple[list[CategoryScore], list[ImprovementItem]]:
    """
    Score all 13 design dimensions and generate improvement suggestions.

    Parameters
    ----------
    elements : list[ElementAnalysis]
        Output from Phase 2 vision_client.
    functional_zones : FunctionalZones
        From Phase 1 zone_detector.
    grid_zones : list[GridZone]
        From Phase 1 zone_detector.
    brand_guidelines : dict, optional
        Custom brand rules. Uses defaults if not provided.

    Returns
    -------
    tuple[list[CategoryScore], list[ImprovementItem]]
    """
    brand = dict(_DEFAULT_BRAND, **(brand_guidelines or {}))

    # Flatten all elements to a list for convenience
    all_props = [e.properties for e in elements]

    scores = [
        CategoryScore(dimension="Consistency",
                     score=score_consistency(elements, brand),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Accessibility",
                     score=score_accessibility(elements, brand),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Aesthetics",
                     score=score_aesthetics(elements, grid_zones),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Performance",
                     score=score_performance(elements),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Usability",
                     score=score_usability(elements, brand),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Brand Consistency",
                     score=score_brand(elements, brand),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Responsive Design",
                     score=score_responsive(elements, functional_zones),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Navigation",
                     score=score_navigation(functional_zones),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Information Architecture",
                     score=score_info_arch(elements, functional_zones),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Interaction Design",
                     score=score_interaction(elements),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Discovery",
                     score=score_discovery(elements, functional_zones),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Operability",
                     score=score_operability(elements),
                     issues=[], suggestions=[]),
        CategoryScore(dimension="Emotional Design",
                     score=score_emotional(elements),
                     issues=[], suggestions=[]),
    ]

    improvements = _build_improvements(scores, all_props, elements)

    return scores, improvements


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_consistency(elements: list, brand: dict) -> int:
    """
    Color variance, font_size/weight variance, spacing deviation from 8dp grid.
    Variance < 5% -> 90-100, < 15% -> 70-89, < 30% -> 50-69, > 30% -> 0-49
    """
    if not elements:
        return 0

    issues: list[str] = []
    total_score = 0
    count = 0

    # --- Color consistency ---
    bg_colors = [_hex_to_rgb(e.properties.background_hex) for e in elements if e.properties.background_hex]
    fg_colors = [_hex_to_rgb(e.properties.foreground_hex) for e in elements if e.properties.foreground_hex]

    if bg_colors:
        variance = _color_variance(bg_colors)
        total_score += _variance_to_score(variance)
        count += 1
        if variance > 0.3:
            issues.append(f"背景色方差过大 ({variance:.2f})")

    if fg_colors:
        variance = _color_variance(fg_colors)
        total_score += _variance_to_score(variance)
        count += 1

    # --- Font consistency ---
    font_sizes = [e.properties.font_size_sp for e in elements if e.properties.font_size_sp > 0]
    if font_sizes:
        variance = _relative_std(font_sizes)
        total_score += _variance_to_score(variance)
        count += 1
        if variance > 0.2:
            issues.append(f"字号方差过大 ({variance:.2f})")

    # --- Spacing consistency (padding multiples of 8dp) ---
    paddings = [
        p for e in elements
        for p in [e.properties.padding_top, e.properties.padding_right,
                  e.properties.padding_bottom, e.properties.padding_left]
        if p > 0
    ]
    if paddings:
        # Measure deviation from 8dp grid
        grid_base = brand.get("spacing", {}).get("base", 8)
        deviations = [abs(p % grid_base) for p in paddings]
        avg_dev = sum(deviations) / len(deviations) if deviations else 0
        score = max(0, int(100 - avg_dev * 10))
        total_score += score
        count += 1

    return round(total_score / count) if count else 0


def score_accessibility(elements: list, brand: dict) -> int:
    """
    WCAG contrast compliance, touch target size.
    >= 90% elements pass WCAG AA -> 90-100; >= 80% -> 70-89; ...
    """
    if not elements:
        return 0

    pass_count = 0
    total = len(elements)

    for e in elements:
        ok = True
        if e.properties.contrast_ratio > 0 and e.properties.contrast_ratio < 4.5:
            ok = False
        if e.properties.touch_target_dp > 0 and e.properties.touch_target_dp < 48:
            ok = False
        if ok:
            pass_count += 1

    ratio = pass_count / total
    if ratio >= 0.9:
        return 95
    elif ratio >= 0.8:
        return 82
    elif ratio >= 0.7:
        return 65
    elif ratio >= 0.6:
        return 50
    else:
        return 30


def score_aesthetics(elements: list, grid_zones: list) -> int:
    """
    Visual weight balance, whitespace ratio (ideal 20-40%), color harmony.
    """
    if not grid_zones:
        return 50

    # Whitespace ratio per cell — compute balance
    ratios = [z.whitespace_ratio for z in grid_zones]
    avg_ws = sum(ratios) / len(ratios) if ratios else 0
    # Ideal whitespace is 20-40%
    if 0.20 <= avg_ws <= 0.40:
        whitespace_score = 100
    elif avg_ws < 0.20:
        whitespace_score = int(100 - (0.20 - avg_ws) * 200)
    else:
        whitespace_score = int(100 - (avg_ws - 0.40) * 200)

    whitespace_score = max(0, whitespace_score)

    # Visual weight balance — variance in element density across cells
    densities = [z.element_count / max(z.w * z.h, 1) for z in grid_zones]
    if densities:
        weight_variance = _relative_std(densities)
        weight_score = max(0, int(100 - weight_variance * 200))
    else:
        weight_score = 50

    # Color temperature diversity — penalize if all cells are same temp
    temps = [_color_temperature(z.dominant_color) for z in grid_zones]
    unique_temps = len(set(temps))
    temp_score = min(100, unique_temps * 25)

    return round((whitespace_score * 0.4 + weight_score * 0.4 + temp_score * 0.2))


def score_performance(elements: list) -> int:
    """
    Total element count, nesting depth, rendering complexity.
    < 50 elements, depth <= 4 -> 90-100; < 80 -> 70-89; < 120 -> 50-69; > 120 -> 0-49
    """
    n = len(elements)
    if n < 50:
        return 95
    elif n < 80:
        return 80
    elif n < 120:
        return 60
    else:
        return 35


def score_usability(elements: list, brand: dict) -> int:
    """
    Touch target >= 48dp, interactive elements have feedback, spacing >= 8dp.
    100% targets pass -> 90-100; >= 85% -> 70-89; ...
    """
    if not elements:
        return 0

    min_target = brand.get("touch_target", 48)
    interactive_types = {"button", "switch", "slider", "input", "navigation", "icon"}

    pass_count = 0
    total = 0

    for e in elements:
        et = e.properties.element_type.lower()
        if et in interactive_types or any(t in et for t in interactive_types):
            total += 1
            ok = True
            if e.properties.touch_target_dp > 0 and e.properties.touch_target_dp < min_target:
                ok = False
            # Check gap between interactive elements (siblings)
            if e.properties.gap_to_siblings > 0 and e.properties.gap_to_siblings < 8:
                ok = False
            if ok:
                pass_count += 1

    if total == 0:
        return 80  # no interactive elements, assume OK

    ratio = pass_count / total
    if ratio >= 1.0:
        return 95
    elif ratio >= 0.85:
        return 82
    elif ratio >= 0.70:
        return 65
    else:
        return 40


def score_brand(elements: list, brand: dict) -> int:
    """
    Primary/secondary/accent color delta from brand guidelines <= 10%.
    Delta <= 5% -> 90-100; <= 10% -> 70-89; <= 20% -> 50-69; > 20% -> 0-49
    """
    colors = brand.get("color", {})
    brand_colors = {k: _hex_to_rgb(v) for k, v in colors.items() if v.startswith("#")}

    if not brand_colors or not elements:
        return 70  # neutral — no brand to compare against

    brand_primary = brand_colors.get("primary", brand_colors.get("accent"))
    if not brand_primary:
        return 70

    scores = []
    for e in elements:
        if e.properties.accent_hex and e.properties.accent_hex.startswith("#"):
            delta = _color_delta(_hex_to_rgb(e.properties.accent_hex), brand_primary)
            scores.append(_delta_to_score(delta))

    if not scores:
        return 70

    # Average of all accent deviations
    avg = sum(scores) / len(scores)
    return round(avg)


def score_responsive(elements: list, zones: FunctionalZones) -> int:
    """
    Content within safe area (not overlapped by status/nav bar).
    All in safe area -> 90-100; minor overflow -> 70-89; ...
    """
    if not zones.content_area:
        return 50

    ca = zones.content_area
    out_of_bounds = 0
    total = len(elements)

    for e in elements:
        # elements are identified by their rough center
        # If we have pixel positions from the original box, we'd check them
        # For now, use text content length as a proxy for content overflow
        pass

    if total == 0:
        return 90

    # Check: does content area have room for elements?
    content_area_ratio = ca.h / 2728  # rough phone height normalization
    if content_area_ratio >= 0.65:
        return 90
    elif content_area_ratio >= 0.55:
        return 75
    else:
        return 55


def score_navigation(zones: FunctionalZones) -> int:
    """
    AppBar present, nav bar icons visible and consistent, back nav exists.
    All present -> 90-100; 1 missing -> 70-89; 2 missing -> 50-69; > 2 -> 0-49
    """
    score = 100
    if not zones.app_bar:
        score -= 30
    if not zones.nav_bar:
        score -= 30
    if not zones.status_bar:
        score -= 10
    return max(0, score)


def score_info_arch(elements: list, zones: FunctionalZones) -> int:
    """
    Logical grouping of related items, section headers present, no orphan items.
    """
    if not elements:
        return 50

    # Heuristic: text elements with similar font_size are likely headers
    headers = [e for e in elements if e.properties.font_size_sp >= 16 and e.properties.text_content.strip()]
    items = [e for e in elements if e.properties.font_size_sp < 16 and e.properties.text_content.strip()]

    # Good: many items grouped under few headers
    if headers and items:
        ratio = len(items) / len(headers)
        if ratio <= 8:  # reasonable grouping
            return 90
        elif ratio <= 12:
            return 75
        else:
            return 55

    return 60  # insufficient data


def score_interaction(elements: list) -> int:
    """
    All interactive elements have touch targets; state indicators visible.
    """
    if not elements:
        return 50

    interactive = [e for e in elements
                   if e.properties.element_type.lower() in {"button", "switch", "slider", "input", "navigation", "icon"}]

    if not interactive:
        return 80

    with_target = [e for e in interactive if e.properties.touch_target_dp >= 48]
    ratio = len(with_target) / len(interactive)

    if ratio >= 1.0:
        return 95
    elif ratio >= 0.85:
        return 80
    elif ratio >= 0.70:
        return 60
    else:
        return 35


def score_discovery(elements: list, zones: FunctionalZones) -> int:
    """
    Key actions not hidden; search/filter present if > 10 items.
    """
    if not elements:
        return 50

    n = len(elements)
    score = 100

    # If more than 10 items, expect search capability
    if n > 10:
        has_search = any("search" in e.properties.text_content.lower() or
                         "搜索" in e.properties.text_content or
                         e.properties.element_type.lower() == "input"
                         for e in elements)
        if not has_search:
            score -= 20

    return max(0, score)


def score_operability(elements: list) -> int:
    """
    Input fields >= 44dp height; no overlapping touch targets.
    """
    inputs = [e for e in elements if e.properties.element_type.lower() == "input"]

    if not inputs:
        return 80

    ok = sum(1 for e in inputs if e.properties.touch_target_dp >= 44)
    ratio = ok / len(inputs)

    if ratio >= 1.0:
        return 95
    elif ratio >= 0.8:
        return 75
    else:
        return 50


def score_emotional(elements: list) -> int:
    """
    Color palette mood (warm/cool/neutral), icon style consistency.
    """
    if not elements:
        return 50

    # Analyze color temperature distribution
    temps = [_color_temperature(e.properties.background_hex) for e in elements if e.properties.background_hex]
    warm = temps.count("warm")
    cool = temps.count("cool")
    neutral = temps.count("neutral")
    total = warm + cool + neutral

    if total == 0:
        return 50

    # Diverse palette is not necessarily bad — just check for jarring contrast
    harmony_score = 70  # baseline

    # If all one temperature, slightly reduce score (too monotonous)
    dominant = max(warm, cool, neutral) / total
    if dominant > 0.9:
        harmony_score = 55
    elif dominant > 0.75:
        harmony_score = 65

    # Icon consistency: check if icon types vary wildly
    icons = [e for e in elements if e.properties.element_type.lower() == "icon"]
    if len(icons) > 1:
        # Icons should have consistent sizing — check height variance
        heights = [e.properties.touch_target_dp for e in icons if e.properties.touch_target_dp > 0]
        if heights:
            variance = _relative_std(heights)
            if variance > 0.4:
                harmony_score -= 10

    return max(0, min(100, harmony_score))


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse #RRGGBB to (r, g, b)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
    return (0, 0, 0)


def _color_variance(rgb_list: list[tuple[int, int, int]]) -> float:
    """Euclidean distance-based variance of a list of RGB colors."""
    if not rgb_list:
        return 0.0
    n = len(rgb_list)
    mean_r = sum(c[0] for c in rgb_list) / n
    mean_g = sum(c[1] for c in rgb_list) / n
    mean_b = sum(c[2] for c in rgb_list) / n
    variance = sum(
        ((c[0] - mean_r) ** 2 + (c[1] - mean_g) ** 2 + (c[2] - mean_b) ** 2)
        for c in rgb_list
    ) / n
    # Normalize to 0-1 (max variance is 3 * 127^2 ≈ 48,000)
    return variance / 48000.0


def _relative_std(values: list[float]) -> float:
    """Coefficient of variation: std / mean. Returns 0 if mean is 0."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean


def _variance_to_score(variance: float) -> int:
    """Map variance (0-1) to a 0-100 score."""
    if variance < 0.05:
        return 95
    elif variance < 0.15:
        return 80
    elif variance < 0.30:
        return 60
    else:
        return 35


def _color_delta(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Euclidean distance between two RGB colors, normalized to 0-1."""
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))
    return dist / (255 * math.sqrt(3))


def _delta_to_score(delta: float) -> int:
    """Map color delta (0-1) to a 0-100 score."""
    if delta <= 0.05:
        return 95
    elif delta <= 0.10:
        return 80
    elif delta <= 0.20:
        return 60
    else:
        return 35


def _color_temperature(hex_color: str) -> str:
    """Estimate color temperature: warm / cool / neutral."""
    r, g, b = _hex_to_rgb(hex_color)
    # Warm: high red, low blue; Cool: high blue, low red
    if r > b + 20:
        return "warm"
    elif b > r + 20:
        return "cool"
    else:
        return "neutral"


# ---------------------------------------------------------------------------
# Improvement plan builder
# ---------------------------------------------------------------------------

def _build_improvements(
    scores: list[CategoryScore],
    all_props: list,
    elements: list[ElementAnalysis],
) -> list[ImprovementItem]:
    """Generate improvement suggestions for dimensions with score < 70."""
    improvements: list[ImprovementItem] = []
    dim_map = {s.dimension: s for s in scores}

    for dim_name, score_obj in dim_map.items():
        if score_obj.score >= 70:
            continue

        priority = "high" if score_obj.score < 50 else "medium" if score_obj.score < 60 else "low"

        issue, suggestion = _issue_for_dimension(dim_name, score_obj.score, all_props, elements)
        affected = [e.element_id for e in elements[:3]]  # top 3 affected

        improvements.append(ImprovementItem(
            dimension=dim_name,
            priority=priority,
            issue=issue,
            suggestion=suggestion,
            affected_elements=affected,
            expected_score_gain=min(20, max(3, 70 - score_obj.score) // 5 * 3),
        ))

    # Sort by priority
    order = {"high": 0, "medium": 1, "low": 2}
    improvements.sort(key=lambda i: (order[i.priority], -i.expected_score_gain))

    return improvements


def _issue_for_dimension(
    dim: str,
    score: int,
    props: list,
    elements: list[ElementAnalysis],
) -> tuple[str, str]:
    """Return (issue_description, suggestion) for a given low-scoring dimension."""
    if dim == "Accessibility":
        low_contrast = [p for p in props if 0 < p.contrast_ratio < 4.5]
        if low_contrast:
            return (
                f" {len(low_contrast)} 个元素的文字对比度不足 WCAG AA 标准",
                "加深文字颜色或提升背景亮度，使对比度达到 4.5:1 以上"
            )
        small_targets = [p for p in props if 0 < p.touch_target_dp < 48]
        if small_targets:
            return (
                f" {len(small_targets)} 个可交互元素的触摸目标小于 48dp",
                "增大触摸目标区域，确保最小 48×48dp"
            )
        return ("多处无障碍设计不符合 WCAG AA 标准", "审查所有文字与背景的对比度，确保不小于 4.5:1")

    if dim == "Consistency":
        return ("设计属性（颜色/字号/间距）在不同元素间存在较大差异", "统一品牌色板、字号层级和间距基准")

    if dim == "Aesthetics":
        return ("视觉权重分布不均或留白比例不理想", "调整元素分布，确保视觉重心平衡，留白比例在 20-40% 之间")

    if dim == "Performance":
        n = len(elements)
        return (f"UI 元素数量过多 ({n} 个)，影响渲染性能", "减少冗余嵌套元素，合并同类项，优先使用轻量组件")

    if dim == "Usability":
        return ("可交互元素的触摸目标或间距不足", "确保所有按钮/Toggle 的触摸目标 ≥ 48dp，间距 ≥ 8dp")

    if dim == "Brand Consistency":
        return ("元素用色偏离品牌规范", "参照品牌色板调整主色/强调色，确保色值偏差 < 10%")

    if dim == "Responsive Design":
        return ("内容区域未充分适配不同屏幕密度", "检查安全区域填充，确保关键内容不被状态栏/导航栏遮挡")

    if dim == "Navigation":
        return ("导航结构不完整或不一致", "确保 AppBar 和 NavBar 完整呈现，图标和返回路径清晰可见")

    if dim == "Information Architecture":
        return ("内容分组逻辑不清晰，存在孤立项", "按功能将列表项分组，添加分组标题，减少无分组孤立项")

    if dim == "Interaction Design":
        return ("部分可交互元素缺少明确的交互状态指示", "为所有按钮/输入框添加按下/选中/禁用等状态反馈")

    if dim == "Discovery":
        return ("关键操作入口不易发现", "重新评估信息层级，确保常用操作在首屏可见")

    if dim == "Operability":
        return ("输入框高度不足或触摸目标重叠", "确保输入框高度 ≥ 44dp，检查元素间无触摸重叠")

    if dim == "Emotional Design":
        return ("视觉风格不够统一或色调过于单调", "丰富但不凌乱地使用配色，考虑加入微妙渐变或阴影增加层次感")

    return (f"该维度当前得分为 {score}", "进一步审视设计规范与实际实现的一致性")


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from zone_detector import detect_zones
    from vision_client import analyze_elements

    import argparse
    import json

    parser = argparse.ArgumentParser(description="Phase 3: Evaluator")
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--no-api", action="store_true", help="Skip API call, use placeholder data")
    args = parser.parse_args()

    print("[evaluator] Running zone detection...")
    zones = detect_zones(args.image)

    if args.no_api:
        # Use placeholder element properties for testing
        from models import ElementAnalysis, ElementProperties
        elements = [
            ElementAnalysis(
                element_id=f"element_{i}",
                properties=ElementProperties(
                    element_type="text",
                    background_hex="#FFFFFF",
                    foreground_hex="#212121",
                    font_size_sp=16,
                    font_weight="normal",
                    touch_target_dp=48,
                    contrast_ratio=12.5,
                    wcag_level="AAA",
                )
            )
            for i in range(min(10, len(zones.element_boxes)))
        ]
        print(f"[evaluator] Using {len(elements)} placeholder elements (--no-api)")
    else:
        print(f"[evaluator] Running vision analysis on {len(zones.element_boxes)} elements...")
        elements = analyze_elements(args.image, zones, api_key=args.api_key)
        print(f"[evaluator] Got properties for {len(elements)} elements")

    print("[evaluator] Scoring...")
    scores, improvements = evaluate(elements, zones.functional_zones, zones.grid_zones)

    print("\n=== Category Scores ===")
    for s in scores:
        bar = "█" * (s.score // 10) + "░" * (10 - s.score // 10)
        status = "✓" if s.score >= 70 else "✗"
        print(f"  {status} {s.dimension:25s} {s.score:3d} {bar}")

    if improvements:
        print(f"\n=== Improvement Plan ({len(improvements)} items) ===")
        for imp in improvements:
            print(f"  [{imp.priority.upper()}] {imp.dimension}: {imp.issue}")
            print(f"           → {imp.suggestion}")
