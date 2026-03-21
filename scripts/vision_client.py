"""
Phase 2: Vision Client

Wraps Anthropic Claude API for vision analysis of UI elements.

Accepts:
  - ZoneDetectionResult from Phase 1
  - Image path

Returns:
  - list[ElementAnalysis] — per-element visual properties

Dependencies: anthropic, pillow, requests
Environment: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import base64
import json
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import anthropic
from PIL import Image

from models import ElementAnalysis, ElementBox, ElementProperties, ZoneDetectionResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
_MAX_IMAGE_SIZE = (1024, 1024)      # Claude Vision max input
_MAX_PIXELS = 5 * 1024 * 1024      # 5M pixels — Claude limit
_MAX_BATCH = 8                       # elements per API call
_MAX_RETRIES = 3
_RETRY_DELAY = 5                     # seconds


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROPERTY_EXTRACTION_PROMPT = """\
You are an expert Android UI analyst. For each UI element in the image, extract its visual properties.
Return a JSON object with a single key "elements" mapping element IDs to property objects.

For each element, extract:
- type: one of "icon", "button", "text", "card", "image", "switch", "slider", "input", "navigation", "unknown"
- background_hex: hex color of the element's background (e.g. "#FFFFFF")
- foreground_hex: hex color of the primary text/icon (e.g. "#212121")
- accent_hex: hex color of any accent/brand color used (e.g. "#3F51B5")
- opacity: 0.0-1.0 transparency
- font_family: CSS font-family name (e.g. "Roboto", "Noto Sans SC") or "unknown"
- font_size_sp: font size in sp (e.g. 14, 16, 20) or 0 if not text
- font_weight: "thin", "normal", "medium", "bold", or "unknown"
- line_height: line-height multiplier (e.g. 1.5) or 0 if not text
- letter_spacing: letter-spacing in em or 0 if not text
- text_content: the visible text content or ""
- padding_top, padding_right, padding_bottom, padding_left: padding in dp (0 if not applicable)
- margin_top, margin_right, margin_bottom, margin_left: margin in dp (0 if not applicable)
- border_radius_dp: corner radius in dp (0 if none)
- border_width_dp: border width in dp (0 if none)
- border_color: hex color of border or ""
- box_shadow: brief description of shadow (e.g. "0 2dp blur 4dp offset #00000030") or ""
- gradient: brief description of gradient or "" if none
- blur_radius: blur radius in dp (0 if none)
- contrast_ratio: WCAG contrast ratio between foreground and background (e.g. 4.5) or 0
- wcag_level: "AAA", "AA", "A", or "" if contrast is insufficient
- touch_target_dp: height of touch target in dp (0 if not interactive)
- screen_reader_support: true if element has visible text or aria label, false otherwise
- shadow_direction: direction of main light source or "" (e.g. "top-left", "bottom-right")
- shadow_intensity: 0.0-1.0 opacity of shadow or 0
- highlight_direction: direction of highlight or ""
- specular_strength: 0.0-1.0 strength of specular highlight or 0
- anchor_x: "left", "center", or "right" — horizontal alignment
- anchor_y: "top", "middle", or "bottom" — vertical alignment

Return ONLY valid JSON like:
{
  "elements": {
    "element_0": { "type": "text", "background_hex": "#FFFFFF", ... },
    "element_1": { "type": "icon", "background_hex": "#F5F5F5", ... }
  }
}
"""


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class VisionClient:
    """
    Claude Vision API client for extracting visual properties from UI elements.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _ANTHROPIC_MODEL,
        max_batch: int = _MAX_BATCH,
    ):
        """
        Parameters
        ----------
        api_key : str, optional
            Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        model : str
            Claude model to use. Default: claude-3-5-sonnet-latest
        max_batch : int
            Max elements to send per API call.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Pass api_key or set the env var."
            )
        self.model = model
        self.max_batch = max_batch
        self._client = anthropic.Anthropic(api_key=self.api_key)
        self._cache: dict[str, ElementAnalysis] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_elements(
        self,
        image_path: str,
        zones: ZoneDetectionResult,
    ) -> list[ElementAnalysis]:
        """
        Analyze all detected elements via Claude Vision.

        Parameters
        ----------
        image_path : str
            Path to the screenshot.
        zones : ZoneDetectionResult
            Output from Phase 1 zone_detector.

        Returns
        -------
        list[ElementAnalysis]
            One entry per element box from zones.element_boxes.
        """
        # Load and resize image if needed
        img_pil = self._load_image(image_path)
        img_base64 = self._encode_image(img_pil)

        # Batch elements
        boxes = zones.element_boxes
        results: list[ElementAnalysis] = []

        for i in range(0, len(boxes), self.max_batch):
            batch = boxes[i : i + self.max_batch]
            retry_count = 0
            while retry_count < _MAX_RETRIES:
                try:
                    batch_results = self._analyze_batch(
                        img_base64, batch, zones.image_width, zones.image_height
                    )
                    results.extend(batch_results)
                    break
                except (anthropic.RateLimitError, anthropic.APIError) as exc:
                    retry_count += 1
                    if retry_count >= _MAX_RETRIES:
                        raise
                    wait = _RETRY_DELAY * retry_count
                    print(f"[vision_client] Retry {retry_count}/{_MAX_RETRIES} after {wait}s: {exc}")
                    time.sleep(wait)

        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_image(self, path: str) -> Image.Image:
        """Load image, resize if >5M pixels, convert to RGB."""
        img = Image.open(path).convert("RGB")
        w, h = img.size
        pixels = w * h
        if pixels > _MAX_PIXELS:
            scale = (_MAX_PIXELS / pixels) ** 0.5
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
        elif w > _MAX_IMAGE_SIZE[0] or h > _MAX_IMAGE_SIZE[1]:
            img.thumbnail(_MAX_IMAGE_SIZE, Image.LANCZOS)
        return img

    def _encode_image(self, img: Image.Image) -> str:
        """Encode image to base64 PNG string."""
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _analyze_batch(
        self,
        image_b64: str,
        boxes: list[ElementBox],
        img_w: int,
        img_h: int,
    ) -> list[ElementAnalysis]:
        """
        Send a batch of elements to Claude Vision and parse the response.
        """
        # Build a simple annotated image: draw crop markers for each element region
        # We include the full image and describe each bounding box in the prompt.
        box_descriptions = []
        for box in boxes:
            box_descriptions.append(
                f'  - {box.element_id}: x={box.x}, y={box.y}, '
                f'width={box.w}, height={box.h}, estimated_type={box.element_type.value}'
            )
        boxes_text = "\n".join(box_descriptions)

        prompt = (
            _PROPERTY_EXTRACTION_PROMPT
            + f"\n\nImage dimensions: {img_w}×{img_h} pixels.\n"
            + f"Detected element bounding boxes:\n{boxes_text}\n\n"
            + "For each element above, extract its visual properties from the image. "
            + "If you cannot determine a property, use null or a sensible default."
        )

        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        # Parse response — filter out thinking blocks, keep text blocks
        text_blocks = [
            b for b in response.content
            if hasattr(b, 'type') and b.type == 'text'
        ]
        if not text_blocks:
            raise ValueError(
                f"No text block in Claude response. Content types: "
                f"{[getattr(b, 'type', '?') for b in response.content]}"
            )
        response_text = text_blocks[0].text
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                # Try to find raw JSON object
                match = re.search(r"\{[\s\S]*\}", response_text)
                if match:
                    data = json.loads(match.group(0))
                else:
                    raise ValueError(f"Could not parse JSON from Claude response:\n{response_text[:500]}")

        elements_map = data.get("elements", {})

        # Build ElementAnalysis objects
        results: list[ElementAnalysis] = []
        for box in boxes:
            raw = elements_map.get(box.element_id, {})
            props = self._parse_properties(raw)
            results.append(ElementAnalysis(element_id=box.element_id, properties=props))

        return results

    def _parse_properties(self, raw: dict) -> ElementProperties:
        """Map a raw dict from Claude to an ElementProperties instance."""
        return ElementProperties(
            element_type=str(raw.get("type", "unknown")),
            background_hex=str(raw.get("background_hex", "#FFFFFF")),
            foreground_hex=str(raw.get("foreground_hex", "#000000")),
            accent_hex=str(raw.get("accent_hex", "#000000")),
            opacity=float(raw.get("opacity", 1.0)),
            font_family=str(raw.get("font_family", "unknown")),
            font_size_sp=float(raw.get("font_size_sp", 0.0)),
            font_weight=str(raw.get("font_weight", "normal")),
            line_height=float(raw.get("line_height", 0.0)),
            letter_spacing=float(raw.get("letter_spacing", 0.0)),
            text_content=str(raw.get("text_content", "")),
            padding_top=float(raw.get("padding_top", 0.0)),
            padding_right=float(raw.get("padding_right", 0.0)),
            padding_bottom=float(raw.get("padding_bottom", 0.0)),
            padding_left=float(raw.get("padding_left", 0.0)),
            margin_top=float(raw.get("margin_top", 0.0)),
            margin_right=float(raw.get("margin_right", 0.0)),
            margin_bottom=float(raw.get("margin_bottom", 0.0)),
            margin_left=float(raw.get("margin_left", 0.0)),
            border_radius_dp=float(raw.get("border_radius_dp", 0.0)),
            border_width_dp=float(raw.get("border_width_dp", 0.0)),
            border_color=str(raw.get("border_color", "#000000")),
            box_shadow=str(raw.get("box_shadow", "")),
            gradient=str(raw.get("gradient", "")),
            blur_radius=float(raw.get("blur_radius", 0.0)),
            contrast_ratio=float(raw.get("contrast_ratio", 0.0)),
            wcag_level=str(raw.get("wcag_level", "")),
            touch_target_dp=float(raw.get("touch_target_dp", 0.0)),
            screen_reader_support=bool(raw.get("screen_reader_support", False)),
            shadow_direction=str(raw.get("shadow_direction", "")),
            shadow_intensity=float(raw.get("shadow_intensity", 0.0)),
            highlight_direction=str(raw.get("highlight_direction", "")),
            specular_strength=float(raw.get("specular_strength", 0.0)),
            anchor_x=str(raw.get("anchor_x", "")),
            anchor_y=str(raw.get("anchor_y", "")),
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def analyze_elements(
    image_path: str,
    zones: ZoneDetectionResult,
    api_key: Optional[str] = None,
    model: str = _ANTHROPIC_MODEL,
) -> list[ElementAnalysis]:
    """
    Analyze all elements in a screenshot using Claude Vision.

    Parameters
    ----------
    image_path : str
        Path to the screenshot file.
    zones : ZoneDetectionResult
        Zone detection result from Phase 1.
    api_key : str, optional
        Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
    model : str
        Claude model to use.

    Returns
    -------
    list[ElementAnalysis]
    """
    client = VisionClient(api_key=api_key, model=model)
    return client.analyze_elements(image_path, zones)


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    from zone_detector import detect_zones

    parser = argparse.ArgumentParser(description="Phase 2: Claude Vision Element Analysis")
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default=_ANTHROPIC_MODEL,
        help=f"Claude model (default: {_ANTHROPIC_MODEL})",
    )
    args = parser.parse_args()

    print(f"[vision_client] Running zone detection first...")
    zones = detect_zones(args.image)
    print(f"[vision_client] {len(zones.element_boxes)} elements found, analyzing with Claude Vision...")

    try:
        results = analyze_elements(args.image, zones, api_key=args.api_key, model=args.model)
    except ValueError as e:
        print(f"[vision_client] ERROR: {e}")
        print("[vision_client] Make sure ANTHROPIC_API_KEY is set.")
        import sys
        sys.exit(1)

    print(f"\n=== Vision Analysis Results ({len(results)} elements) ===")
    for r in results:
        p = r.properties
        print(f"\n  {r.element_id}:")
        print(f"    type={p.element_type}  text={p.text_content[:40]!r}")
        print(f"    bg={p.background_hex}  fg={p.foreground_hex}  accent={p.accent_hex}")
        print(f"    font={p.font_family}  size={p.font_size_sp}sp  weight={p.font_weight}")
        print(f"    contrast={p.contrast_ratio}  wcag={p.wcag_level}  touch={p.touch_target_dp}dp")
        print(f"    padding=({p.padding_top},{p.padding_right},{p.padding_bottom},{p.padding_left})")
        print(f"    radius={p.border_radius_dp}dp  shadow={p.box_shadow[:40]!r}")
