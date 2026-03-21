"""
Phase 6: Vision Analyzer

Main entry point — orchestrates all phases and provides CLI.

Accepts a screenshot path, runs the full pipeline:
  Phase 1: Zone Detection (CV-based)
  Phase 2: Element Analysis (Claude Vision)
  Phase 3: Scoring (13 dimensions)
  Phase 4: Zone Comparison
  Phase 5: Report Generation

Outputs AuditReport (JSON + HTML).

Dependencies: anthropic, opencv-python, pillow, numpy
Environment: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import (
    AuditReport,
    CategoryScore,
    ElementAnalysis,
    FunctionalZones,
    GridZone,
    ImprovementItem,
    ZoneComparisonResult,
    ZoneDetectionResult,
    ZoneType,
)

# ---------------------------------------------------------------------------
# Optional imports — show helpful error if missing
# ---------------------------------------------------------------------------

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import anthropic
except ImportError:
    anthropic = None


# ---------------------------------------------------------------------------
# VisionAndroidUIAuditor
# ---------------------------------------------------------------------------

class VisionAndroidUIAuditor:
    """
    Orchestrates the full Android UI audit pipeline.

    Usage:
        auditor = VisionAndroidUIAuditor(anthropic_api_key="sk-...")
        report = auditor.analyze_screenshot("/path/to/screenshot.png")
    """

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        claude_model: str = "claude-3-5-sonnet-latest",
        grid_size: tuple[int, int] = (3, 4),
        brand_guidelines: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        anthropic_api_key : str, optional
            Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        claude_model : str
            Claude model for vision analysis. Default: claude-3-5-sonnet-latest
        grid_size : tuple[int, int]
            (rows, cols) for grid overlay. Default: (3, 4)
        brand_guidelines : dict, optional
            Custom brand rules for scoring.
        """
        self.api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = claude_model
        self.grid_size = grid_size
        self.brand_guidelines = brand_guidelines

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_screenshot(
        self,
        image_path: str,
        output_dir: Optional[str] = None,
    ) -> AuditReport:
        """
        Run the full audit pipeline on a screenshot.

        Parameters
        ----------
        image_path : str
            Path to the PNG/JPG screenshot.
        output_dir : str, optional
            Directory for output files. Creates ./audit_output if not set.

        Returns
        -------
        AuditReport
        """
        print(f"[vision_analyzer] Starting audit for: {image_path}")

        # Phase 1: Zone Detection
        print("[vision_analyzer] Phase 1: Zone Detection...")
        zone_result = self._detect_zones(image_path)

        # Phase 2: Element Analysis
        print("[vision_analyzer] Phase 2: Element Analysis (Claude Vision)...")
        elements = self._analyze_elements(image_path, zone_result)

        # Phase 3: Scoring
        print("[vision_analyzer] Phase 3: Scoring...")
        scores, improvements = self._evaluate(elements, zone_result)

        # Phase 4: Zone Comparison
        print("[vision_analyzer] Phase 4: Zone Comparison...")
        zone_comparison = self._compare_zones(elements, zone_result)

        # Build AuditReport
        overall = self._compute_overall(scores)
        compliance = self._compute_compliance(overall)

        report = AuditReport(
            evaluation_timestamp=datetime.now().isoformat(),
            screenshot_path=str(Path(image_path).resolve()),
            overall_score=overall,
            compliance_status=compliance,
            image_width=zone_result.image_width,
            image_height=zone_result.image_height,
            grid_size=self.grid_size,
            zone_detection=zone_result,
            element_analysis=elements,
            category_scores=scores,
            improvement_plan=improvements,
            zone_comparison=zone_comparison,
        )

        # Phase 5: Report Generation
        if output_dir is not None or True:  # always generate unless explicitly skipped
            print("[vision_analyzer] Phase 5: Report Generation...")
            from report_generator import generate_report
            out_dir = output_dir or "./audit_output"
            json_path, html_path = generate_report(report, out_dir)
            print(f"[vision_analyzer] Reports saved to:")
            print(f"  JSON: {json_path}")
            print(f"  HTML: {html_path}")

        return report

    def analyze_zones_only(self, image_path: str) -> ZoneDetectionResult:
        """
        Run only Phase 1 zone detection (no API calls).

        Returns
        -------
        ZoneDetectionResult
        """
        return self._detect_zones(image_path)

    def analyze_elements(
        self,
        image_path: str,
        zones: ZoneDetectionResult,
    ) -> list[ElementAnalysis]:
        """
        Run only Phase 2 element analysis.

        Requires ANTHROPIC_API_KEY or api_key set in __init__.

        Returns
        -------
        list[ElementAnalysis]
        """
        return self._analyze_elements(image_path, zones)

    # ------------------------------------------------------------------
    # Internal phase runners
    # ------------------------------------------------------------------

    def _detect_zones(self, image_path: str) -> ZoneDetectionResult:
        """Phase 1: Zone Detection using OpenCV."""
        if cv2 is None:
            raise ImportError(
                "opencv-python is required for zone detection. "
                "Install with: pip install opencv-python"
            )
        from zone_detector import detect_zones
        return detect_zones(image_path, grid_size=self.grid_size)

    def _analyze_elements(
        self,
        image_path: str,
        zones: ZoneDetectionResult,
    ) -> list[ElementAnalysis]:
        """Phase 2: Element Analysis using Claude Vision."""
        if anthropic is None:
            raise ImportError(
                "anthropic is required for element analysis. "
                "Install with: pip install anthropic"
            )
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Pass api_key to __init__ "
                "or set the ANTHROPIC_API_KEY environment variable."
            )
        from vision_client import analyze_elements
        return analyze_elements(
            image_path,
            zones,
            api_key=self.api_key,
            model=self.model,
        )

    def _evaluate(
        self,
        elements: list[ElementAnalysis],
        zone_result: ZoneDetectionResult,
    ) -> tuple[list[CategoryScore], list[ImprovementItem]]:
        """Phase 3: Scoring."""
        from evaluator import evaluate
        return evaluate(
            elements,
            zone_result.functional_zones,
            zone_result.grid_zones,
            brand_guidelines=self.brand_guidelines,
        )

    def _compare_zones(
        self,
        elements: list[ElementAnalysis],
        zone_result: ZoneDetectionResult,
    ) -> ZoneComparisonResult:
        """Phase 4: Zone Comparison."""
        from zone_comparator import compare_zones
        return compare_zones(
            elements,
            zone_result.grid_zones,
            zone_result.functional_zones,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_overall(self, scores: list[CategoryScore]) -> int:
        """Arithmetic mean of all 13 dimension scores, rounded."""
        if not scores:
            return 0
        total = sum(s.score for s in scores)
        return round(total / len(scores))

    def _compute_compliance(self, overall: int) -> str:
        """Map overall score to compliance status (Chinese)."""
        if overall >= 95:
            return "完全符合"
        elif overall >= 80:
            return "大部分符合"
        elif overall >= 60:
            return "部分符合"
        elif overall >= 40:
            return "较少符合"
        return "不符合"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="VisionAndroidUIAuditor — Full UI audit pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vision_analyzer.py screenshot.png
  python vision_analyzer.py screenshot.png --output ./my_report
  python vision_analyzer.py screenshot.png --api-key sk-... --grid 4,6
  python vision_analyzer.py screenshot.png --no-api   # uses placeholder data
        """
    )
    parser.add_argument("image", help="Path to screenshot (PNG or JPG)")
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default="claude-3-5-sonnet-latest",
        help="Claude model (default: claude-3-5-sonnet-latest)",
    )
    parser.add_argument(
        "--grid",
        default="3,4",
        help="Grid size as rows,cols (default: 3,4)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./audit_output",
        help="Output directory (default: ./audit_output)",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Skip Phase 2 (Claude Vision), use placeholder elements",
    )

    args = parser.parse_args()

    rows, cols = map(int, args.grid.split(","))
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")

    # Build auditor
    auditor = VisionAndroidUIAuditor(
        anthropic_api_key=api_key,
        claude_model=args.model,
        grid_size=(rows, cols),
    )

    # Run zone detection first (always needed, even with --no-api)
    print(f"[vision_analyzer] Running zone detection...")
    zone_result = auditor.analyze_zones_only(args.image)
    print(f"[vision_analyzer] Image: {zone_result.image_width}×{zone_result.image_height}px")
    print(f"[vision_analyzer] Grid: {rows}×{cols} = {len(zone_result.grid_zones)} cells")
    print(f"[vision_analyzer] Elements found: {len(zone_result.element_boxes)}")

    if args.no_api:
        # Build placeholder elements from zone boxes
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
                    contrast_ratio=12.5,
                )
            )
            for i in range(len(zone_result.element_boxes))
        ]
        print(f"[vision_analyzer] Using {len(elements)} placeholder elements (--no-api)")
    else:
        if not api_key:
            print("[vision_analyzer] ERROR: --api-key required or set ANTHROPIC_API_KEY")
            sys.exit(1)
        print(f"[vision_analyzer] Running Claude Vision analysis on {len(zone_result.element_boxes)} elements...")
        elements = auditor.analyze_elements(args.image, zone_result)
        print(f"[vision_analyzer] Got properties for {len(elements)} elements")

    # Phase 3: Scoring
    print("[vision_analyzer] Running scoring...")
    scores, improvements = auditor._evaluate(elements, zone_result)

    # Phase 4: Zone Comparison
    print("[vision_analyzer] Running zone comparison...")
    zone_comparison = auditor._compare_zones(elements, zone_result)

    # Build report
    overall = auditor._compute_overall(scores)
    compliance = auditor._compute_compliance(overall)

    report = AuditReport(
        evaluation_timestamp=datetime.now().isoformat(),
        screenshot_path=str(Path(args.image).resolve()),
        overall_score=overall,
        compliance_status=compliance,
        image_width=zone_result.image_width,
        image_height=zone_result.image_height,
        grid_size=(rows, cols),
        zone_detection=zone_result,
        element_analysis=elements,
        category_scores=scores,
        improvement_plan=improvements,
        zone_comparison=zone_comparison,
    )

    # Phase 5: Report Generation
    print("[vision_analyzer] Generating reports...")
    from report_generator import generate_report
    json_path, html_path = generate_report(report, args.output_dir)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Overall Score: {overall}  ({compliance})")
    print(f"{'='*60}")
    print("\nCategory Scores:")
    for s in scores:
        bar = "█" * (s.score // 10) + "░" * (10 - s.score // 10)
        status = "✓" if s.score >= 70 else "✗"
        print(f"  {status} {s.dimension:26s} {s.score:3d} {bar}")

    if improvements:
        print(f"\nImprovement Plan ({len(improvements)} items):")
        for imp in improvements:
            print(f"  [{imp.priority.upper():6s}] {imp.dimension}: {imp.issue}")

    print(f"\nReports:")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")


if __name__ == "__main__":
    main()
