"""Layout detection tool using PaddleOCR LayoutDetection."""

import os
from pathlib import Path
from typing import Any

from document_extraction_mcp.tools._stdio_silence import suppress_stdout
from document_extraction_mcp.tools.pdf_utils import ensure_image

# Cached layout engine (initialized on first use)
_layout_engine = None


def _get_layout_engine():
    """Get or initialize cached PPStructure engine."""
    global _layout_engine
    if _layout_engine is None:
        # Suppress stdout during initialization to prevent MCP protocol corruption
        with suppress_stdout():
            from paddleocr import PPStructure

            _layout_engine = PPStructure(show_log=False, image_orientation=False)
    return _layout_engine


def layout_detect(image_path: str) -> dict[str, Any]:
    """Detect document layout regions using PaddleOCR LayoutDetection.

    Args:
        image_path: Path to the input image or PDF file

    Returns:
        Dict with layout regions containing type, bounding box, and confidence
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": f"File not found: {image_path}"}

    temp_image = None
    try:
        # Convert PDF to image if necessary
        actual_path, is_temp = ensure_image(image_path)
        if is_temp:
            temp_image = actual_path

        # Get cached layout engine (initialized once)
        layout_engine = _get_layout_engine()

        # Run layout detection with stdout suppressed to prevent MCP protocol corruption
        # result is a list of elements, one list per page. Since we pass one image, result[0] is NOT the page,
        # PPStructure returns a list of regions directly for the image.
        with suppress_stdout():
            result = layout_engine(actual_path)

        # Extract regions from result
        # result structure: [{'type': 'Text', 'bbox': [x1, y1, x2, y2], 'res': ...}, ...]
        regions = []
        for i, item in enumerate(result):
            bbox = item.get("bbox", [0, 0, 0, 0])
            # Ensure bbox is flat [x1, y1, x2, y2]
            if len(bbox) == 4:
                bbox_list = [int(x) for x in bbox]
            else:
                bbox_list = [0, 0, 0, 0]

            region = {
                "region_id": i,
                "region_type": item.get("type", "unknown"),
                "confidence": float(item.get("score", 0.0)) if "score" in item else 0.0,
                "bbox": bbox_list,
            }
            # PPStructure usually returns score in 'res' for OCR, but for layout detection itself,
            # the 'score' might be on the item or implicit.
            # If 'score' is missing, we default to 0.0 or check 'res'.
            if "score" in item:
                 region["confidence"] = float(item["score"])
            
            regions.append(region)

        # Sort by confidence (highest first)
        regions.sort(key=lambda x: x["confidence"], reverse=True)

        # Group by type for summary
        type_counts = {}
        for r in regions:
            rtype = r["region_type"]
            type_counts[rtype] = type_counts.get(rtype, 0) + 1

        # Save visualization artifact
        # Use original image_path for artifacts dir, but actual_path for loading image
        visualization_path = None
        visualization_error = None
        try:
            from document_extraction_mcp.tools.visualization import (
                draw_bboxes_on_image,
                get_artifacts_dir,
            )
            
            artifacts_dir = get_artifacts_dir(image_path)
            image_name = Path(image_path).stem
            output_path = str(artifacts_dir / f"{image_name}_layout.png")
            
            # Color mapping for different region types
            type_colors = {
                "Text": (0, 255, 0),      # Green
                "Table": (255, 0, 0),     # Red
                "Figure": (0, 0, 255),    # Blue
                "Chart": (255, 165, 0),   # Orange
                "Title": (255, 0, 255),   # Magenta
                "List": (0, 255, 255),    # Cyan
            }
            
            visualization_path = draw_bboxes_on_image(
                image_path=actual_path,
                regions=regions,
                output_path=output_path,
                bbox_key="bbox",
                label_key="region_type",
                colors=type_colors,
                default_color=(128, 128, 128),
            )
        except Exception as e:
            # Store error to include in response
            visualization_error = str(e)

        result = {
            "success": True,
            "region_count": len(regions),
            "image_path": image_path,  # Include original path for downstream tools
            "type_summary": type_counts,
            "regions": regions,
        }
        
        if visualization_path:
            from document_extraction_mcp.tools.visualization import get_artifacts_dir
            result["visualization_path"] = visualization_path
            result["artifacts_dir"] = str(get_artifacts_dir(image_path))
        elif visualization_error:
            result["visualization_error"] = visualization_error

        return result

    except ImportError as e:
        return {"error": f"PaddleOCR import failed: {str(e)}. Run: pip install paddleocr paddlepaddle"}
    except Exception as e:
        return {"error": f"Layout detection failed: {str(e)}"}
    finally:
        # Clean up temporary file (with retry for Windows file locking)
        if temp_image and os.path.exists(temp_image):
            try:
                os.unlink(temp_image)
            except PermissionError:
                pass  # File still in use, will be cleaned up by OS later
