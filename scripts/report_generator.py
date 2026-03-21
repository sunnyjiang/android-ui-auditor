"""
Phase 5: Report Generator

Generates JSON audit report + standalone HTML visualization.

Accepts:
  - AuditReport from Phase 6 orchestrator

Returns:
  - Saves {output_dir}/audit_report.json
  - Saves {output_dir}/audit_report.html

Dependencies: plotly (for HTML export)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import AuditReport, CategoryScore, ImprovementItem


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    report: AuditReport,
    output_dir: Optional[str] = None,
) -> tuple[str, str]:
    """
    Generate JSON and HTML reports from an AuditReport.

    Parameters
    ----------
    report : AuditReport
        Complete audit report from VisionAndroidUIAuditor.
    output_dir : str, optional
        Directory to save reports. If None, uses ./audit_output.

    Returns
    -------
    tuple[str, str]
        Paths to (json_path, html_path)
    """
    if output_dir is None:
        output_dir = "./audit_output"

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_path = out_path / "audit_report.json"
    html_path = out_path / "audit_report.html"

    # Write JSON
    json_data = report.to_dict()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    # Write HTML
    html_content = _build_html_report(report)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(json_path), str(html_path)


# ---------------------------------------------------------------------------
# HTML report builder
# ---------------------------------------------------------------------------

def _build_html_report(report: AuditReport) -> str:
    """Build a complete standalone HTML report with Plotly.js from CDN."""

    # Score color
    def score_color(s: int) -> str:
        if s >= 90:
            return "#22c55e"
        elif s >= 70:
            return "#84cc16"
        elif s >= 50:
            return "#eab308"
        elif s >= 30:
            return "#f97316"
        return "#ef4444"

    def score_bar(s: int) -> str:
        c = score_color(s)
        return f'<div style="background:{c};height:24px;width:{s}%;border-radius:4px;display:inline-block;min-width:40px;text-align:center;color:white;font-weight:bold;line-height:24px;">{s}</div>'

    # Category scores HTML
    scores_html = ""
    for cs in report.category_scores:
        bar = score_bar(cs.score)
        status_icon = "✓" if cs.score >= 70 else "✗"
        scores_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #333;">{status_icon}</td>
          <td style="padding:8px;border-bottom:1px solid #333;">{cs.dimension}</td>
          <td style="padding:8px;border-bottom:1px solid #333;">{bar}</td>
        </tr>"""

    # Improvement plan HTML
    improvements_html = ""
    if report.improvement_plan:
        priority_colors = {"high": "#ef4444", "medium": "#f97316", "low": "#eab308"}
        for imp in report.improvement_plan:
            pcolor = priority_colors.get(imp.priority, "#888")
            improvements_html += f"""
        <div style="margin-bottom:16px;padding:12px;background:#1a1a2e;border-radius:8px;border-left:4px solid {pcolor};">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="background:{pcolor};color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;">{imp.priority.upper()}</span>
            <strong style="color:#e2e8f0;">{imp.dimension}</strong>
          </div>
          <div style="color:#f87171;font-size:14px;margin-bottom:4px;">⚠ {imp.issue}</div>
          <div style="color:#86efac;font-size:14px;">→ {imp.suggestion}</div>
          <div style="margin-top:6px;font-size:12px;color:#64748b;">
            Affected: {', '.join(imp.affected_elements[:3]) if imp.affected_elements else 'N/A'} ·
            Expected gain: +{imp.expected_score_gain}
          </div>
        </div>"""
    else:
        improvements_html = '<div style="color:#22c55e;font-size:16px;padding:16px;">✓ All dimensions score 70 or above — no critical improvements needed!</div>'

    # Grid heatmap HTML
    heatmap_html = _build_heatmap_html(report)

    # Zone comparison HTML
    zone_html = ""
    if report.zone_comparison.functional_zones:
        for zc in report.zone_comparison.functional_zones:
            zone_html += f"""
        <div style="display:flex;gap:16px;padding:8px 0;border-bottom:1px solid #262640;">
          <div style="color:#94a3b8;min-width:120px;">{zc.zone_id}</div>
          <div style="color:#e2e8f0;">Density: <strong>{zc.density:.4f}</strong></div>
          <div style="color:#e2e8f0;">Whitespace: <strong>{zc.whitespace_ratio:.2f}</strong></div>
          <div style="color:#e2e8f0;">Visual Weight: <strong>{zc.visual_weight:.2f}</strong></div>
        </div>"""

    # Element inspector HTML (list of elements with properties)
    elements_html = ""
    if report.element_analysis:
        for ea in report.element_analysis[:50]:  # limit to 50 for readability
            p = ea.properties
            elements_html += f"""
        <div style="margin-bottom:12px;padding:10px;background:#1e1e32;border-radius:6px;cursor:pointer;"
             onclick="this.classList.toggle('expanded')">
          <div style="display:flex;justify-content:space-between;color:#e2e8f0;font-weight:bold;">
            <span>{ea.element_id}</span>
            <span style="color:#94a3b8;font-weight:normal;">{p.element_type}</span>
          </div>
          <div class="element-details" style="display:none;margin-top:8px;font-size:13px;color:#94a3b8;grid-template-columns:1fr 1fr;gap:4px;">
            <div>BG: <span style="color:#e2e8f0;">{p.background_hex}</span></div>
            <div>FG: <span style="color:#e2e8f0;">{p.foreground_hex}</span></div>
            <div>Font: <span style="color:#e2e8f0;">{p.font_family}</span></div>
            <div>Size: <span style="color:#e2e8f0;">{p.font_size_sp}sp</span></div>
            <div>Contrast: <span style="color:#e2e8f0;">{p.contrast_ratio:.1f}</span> ({p.wcag_level or 'N/A'})</div>
            <div>Touch: <span style="color:#e2e8f0;">{p.touch_target_dp}dp</span></div>
            <div>Padding: <span style="color:#e2e8f0;">{p.padding_top:.0f},{p.padding_right:.0f},{p.padding_bottom:.0f},{p.padding_left:.0f}</span></div>
            <div>Radius: <span style="color:#e2e8f0;">{p.border_radius_dp}dp</span></div>
          </div>
        </div>"""

    # Compliance badge
    compliance_colors = {
        "完全符合": "#22c55e",
        "大部分符合": "#84cc16",
        "部分符合": "#eab308",
        "较少符合": "#f97316",
        "不符合": "#ef4444",
    }
    compliance_color = compliance_colors.get(report.compliance_status, "#888")

    overall_color = score_color(report.overall_score)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Android UI Audit Report</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f1a; color: #e2e8f0; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  h1 {{ color: #f1f5f9; font-size: 28px; margin-bottom: 8px; }}
  h2 {{ color: #e2e8f0; font-size: 20px; margin: 32px 0 16px; border-bottom: 1px solid #2d2d4a; padding-bottom: 8px; }}
  h3 {{ color: #cbd5e1; font-size: 16px; margin: 16px 0 8px; }}

  /* Header */
  .report-header {{ background: linear-gradient(135deg, #1e1e32 0%, #16213e 100%); border-radius: 12px; padding: 24px; margin-bottom: 24px; display: flex; gap: 32px; align-items: center; flex-wrap: wrap; }}
  .screenshot-thumb {{ width: 200px; height: auto; border-radius: 8px; object-fit: contain; background: #000; }}
  .header-stats {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  .stat-box {{ text-align: center; }}
  .stat-value {{ font-size: 48px; font-weight: bold; color: {overall_color}; line-height: 1; }}
  .stat-label {{ font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }}
  .compliance-badge {{ display: inline-block; padding: 6px 16px; border-radius: 20px; font-size: 16px; font-weight: bold; color: {compliance_color}; border: 2px solid {compliance_color}; margin-top: 8px; }}

  /* Section cards */
  .section {{ background: #1a1a2e; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}

  /* Scores table */
  table {{ width: 100%; border-collapse: collapse; }}
  table th {{ text-align: left; padding: 10px 8px; color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #2d2d4a; }}
  .score-cell {{ width: 300px; }}

  /* Heatmap */
  .heatmap-container {{ width: 100%; overflow-x: auto; }}

  /* Element list */
  .element-details {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
  }}
  .element-list {{ max-height: 500px; overflow-y: auto; }}
  .element-list::-webkit-scrollbar {{ width: 6px; }}
  .element-list::-webkit-scrollbar-thumb {{ background: #2d2d4a; border-radius: 3px; }}

  /* Zone rows */
  .zone-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 12px; background: #16213e; border-radius: 8px; margin-bottom: 8px; }}
  .zone-stat {{ text-align: center; }}
  .zone-stat .value {{ font-size: 20px; font-weight: bold; color: #22c55e; }}
  .zone-stat .label {{ font-size: 11px; color: #64748b; text-transform: uppercase; }}

  /* Flagged rows/cols */
  .flagged {{ color: #f97316; font-weight: bold; }}
  .ok {{ color: #22c55e; }}

  /* Toggle details */
  .element-details {{ margin-top: 8px; }}
  .expanded .element-details {{ display: grid !important; }}

  /* Grid layout for heatmap */
  .heatmap-grid {{ display: grid; grid-template-columns: repeat({report.grid_size[1]}, 1fr); gap: 2px; margin-top: 12px; }}
  .heatmap-cell {{ padding: 8px 4px; text-align: center; border-radius: 4px; font-size: 11px; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="report-header">
    <img src="file://{report.screenshot_path}" class="screenshot-thumb" alt="Screenshot"
         onerror="this.style.display='none'">
    <div>
      <h1>Android UI Audit Report</h1>
      <div style="color:#94a3b8;font-size:14px;margin-bottom:12px;">
        {report.screenshot_path}<br>
        {report.evaluation_timestamp} · {report.image_width}×{report.image_height}px · Grid {report.grid_size[0]}×{report.grid_size[1]}
      </div>
      <div class="header-stats">
        <div class="stat-box">
          <div class="stat-value">{report.overall_score}</div>
          <div class="stat-label">Overall Score</div>
        </div>
        <div class="stat-box">
          <div class="compliance-badge">{report.compliance_status}</div>
          <div class="stat-label">Compliance Status</div>
        </div>
        <div class="stat-box">
          <div class="stat-value" style="font-size:32px;color:#94a3b8;">{len(report.element_analysis)}</div>
          <div class="stat-label">Elements Analyzed</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Category Scores -->
  <div class="section">
    <h2>📊 Category Scores</h2>
    <table>
      <thead>
        <tr>
          <th style="width:40px;">Status</th>
          <th>Dimension</th>
          <th class="score-cell">Score</th>
        </tr>
      </thead>
      <tbody>{scores_html}
      </tbody>
    </table>
  </div>

  <!-- Improvement Plan -->
  <div class="section">
    <h2>💡 Improvement Plan</h2>
    {improvements_html}
  </div>

  <!-- Grid Heatmap -->
  <div class="section">
    <h2>🗺️ Grid Heatmap</h2>
    <div class="heatmap-container">
      <div class="heatmap-grid">
        {"".join([
          f'<div class="heatmap-cell" style="background:{_heatmap_bg(c.element_density, c.whitespace_ratio)};color:#fff;">'
          f'[{c.row},{c.col}]<br>{int(c.element_density*100)}%<br>'
          f'<span style="font-size:10px;">{"🔥" if c.color_temperature=="warm" else "❄️" if c.color_temperature=="cool" else "⚪"} '
          f'{int(c.whitespace_ratio*100)}%WS</span></div>'
          for c in report.zone_comparison.grid_heatmap
        ])}
      </div>
    </div>
    <div style="margin-top:12px;font-size:13px;color:#64748b;">
      🔥 warm · ❄️ cool · ⚪ neutral · WS = Whitespace Ratio · % = Element Density
    </div>
  </div>

  <!-- Zone Contrasts -->
  <div class="section">
    <h2>🔍 Functional Zone Analysis</h2>
    <div class="zone-row">
      {"".join([
        f'<div class="zone-stat">'
        f'<div class="value">{zc.density:.4f}</div>'
        f'<div class="label">{zc.zone_id.replace("zone_","")}<br>Density</div></div>'
        for zc in report.zone_comparison.functional_zones
      ])}
    </div>
    <div style="margin-top:12px;">{zone_html}</div>
  </div>

  <!-- Row & Column Comparisons -->
  <div class="section">
    <h2>📏 Row & Column Comparisons</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
      <div>
        <h3>Horizontal Rows</h3>
        {"".join([
          f'<div style="padding:6px 0;border-bottom:1px solid #262640;" class="{"flagged" if r.flagged else "ok"}">'
          f'Row {r.row_id}: height_var={r.height_variance:.3f} width_var={r.width_variance:.3f} '
          f'{"⚠️ FLAGGED" if r.flagged else "✓"}</div>'
          for r in report.zone_comparison.horizontal_rows
        ]) if report.zone_comparison.horizontal_rows else '<div style="color:#64748b;">No row data</div>'}
      </div>
      <div>
        <h3>Vertical Columns</h3>
        {"".join([
          f'<div style="padding:6px 0;border-bottom:1px solid #262640;" class="{"flagged" if c.flagged else "ok"}">'
          f'Col {c.col_id}: width_var={c.width_variance:.3f} gap_irreg={c.gap_irregularity:.3f} '
          f'{"⚠️ FLAGGED" if c.flagged else "✓"}</div>'
          for c in report.zone_comparison.vertical_columns
        ]) if report.zone_comparison.vertical_columns else '<div style="color:#64748b;">No column data</div>'}
      </div>
    </div>
  </div>

  <!-- Element Inspector -->
  <div class="section">
    <h2>🔎 Element Inspector</h2>
    <p style="color:#64748b;font-size:13px;margin-bottom:12px;">点击元素展开详情 (Showing first 50 elements)</p>
    <div class="element-list">{elements_html}
    </div>
  </div>

</div>
<script>
// Auto-expand first 3 elements
document.querySelectorAll('.element-list > div').forEach((el, i) => {{
  if (i < 3) el.classList.add('expanded');
}});
</script>
</body>
</html>"""
    return html


def _heatmap_bg(density: float, whitespace: float) -> str:
    """Compute heatmap cell background color."""
    # High density = warm/orange, low = cool/blue
    # Adjust by whitespace
    if density > 0.15:
        return "rgba(239,68,68,0.7)"  # red for dense
    elif density > 0.08:
        return "rgba(249,115,22,0.7)"  # orange
    elif density > 0.03:
        return "rgba(234,179,8,0.7)"  # yellow
    elif whitespace > 0.7:
        return "rgba(59,130,246,0.5)"  # blue for whitespace-heavy
    else:
        return "rgba(100,116,139,0.5)"  # gray for moderate


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def save_report(
    report: AuditReport,
    output_dir: Optional[str] = None,
) -> tuple[str, str]:
    """
    Alias for generate_report for backward compatibility.
    """
    return generate_report(report, output_dir)


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 5: Report Generator")
    parser.add_argument("json", help="Path to audit_report.json")
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory")
    args = parser.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        import json
        data = json.load(f)

    # Reconstruct AuditReport from JSON (basic reconstruction)
    from models import AuditReport
    # For testing purposes, just generate HTML from the JSON structure
    print(f"[report_generator] JSON report loaded, generating HTML...")

    # Write a minimal HTML just to test the HTML builder
    out_dir = args.output_dir or "./audit_output"
    import os
    os.makedirs(out_dir, exist_ok=True)

    html_path = os.path.join(out_dir, "audit_report.html")
    print(f"[report_generator] HTML report would be saved to: {html_path}")
    print("[report_generator] For full test, run vision_analyzer.py end-to-end")
