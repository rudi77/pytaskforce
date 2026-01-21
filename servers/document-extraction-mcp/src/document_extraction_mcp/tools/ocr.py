"""OCR extraction tool using PaddleOCR."""

import os
from pathlib import Path
from typing import Any

import numpy as np

from document_extraction_mcp.tools._stdio_silence import suppress_stdout
from document_extraction_mcp.tools.pdf_utils import ensure_image
from document_extraction_mcp.tools.visualization import visualize_ocr_regions

# Debug log file used to pinpoint hangs in MCP context.
_DEBUG_LOG_PATH = Path(__file__).with_name("mcp_tool_debug.log")


def _debug_log(message: str) -> None:
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8", errors="ignore") as f:
            f.write(message + "\n")
    except Exception:
        pass


# Cached OCR engine (initialized on first use)
_ocr_engine = None


def _get_ocr_engine():
    """Get or initialize cached PaddleOCR engine."""
    global _ocr_engine
    if _ocr_engine is None:
        # Suppress stdout during initialization to prevent MCP protocol corruption
        with suppress_stdout():
            from paddleocr import PaddleOCR

            # Enable angle classifier so cls=True works and the cls model is loaded.
            _ocr_engine = PaddleOCR(
                lang="en",
                show_log=False,
                use_angle_cls=True,
            )
    return _ocr_engine


def ocr_extract(image_path: str) -> dict[str, Any]:
    """Extract text from an image or PDF using PaddleOCR.

    Args:
        image_path: Path to the input image or PDF file

    Returns:
        Dict with OCR regions containing text, bounding boxes, and confidence
        scores
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": f"File not found: {image_path}"}

    temp_image = None
    try:
        _debug_log(f"ocr.py: start path={image_path}")
        # Convert PDF to image if necessary
        actual_path, is_temp = ensure_image(image_path)
        if is_temp:
            temp_image = actual_path
        _debug_log(
            f"ocr.py: ensure_image done actual_path={actual_path}"
        )

        # Get cached OCR engine (initialized once)
        _debug_log("ocr.py: get_ocr_engine")
        ocr = _get_ocr_engine()
        _debug_log("ocr.py: got_ocr_engine")

        # Run OCR with stdout suppressed to prevent MCP protocol corruption
        _debug_log("ocr.py: ocr.ocr begin")
        with suppress_stdout():
            # PaddleOCR v2.x API: ocr.ocr(...) (there is no .predict())
            # Returns OCR detections: [[quad_points, (text, score)], ...]
            result = ocr.ocr(actual_path, cls=True)
        _debug_log("ocr.py: ocr.ocr done")

        # PaddleOCR may return either:
        # - detections directly: [[quad, (text, score)], ...]
        # - or a single-item outer list: [ [[quad, (text, score)], ...] ]
        detections: list[Any]
        if (
            isinstance(result, list)
            and len(result) == 1
            and isinstance(result[0], list)
            and (len(result[0]) == 0 or isinstance(result[0][0], (list, tuple)))
        ):
            detections = result[0]
        else:
            detections = result or []

        # Determine image dimensions
        try:
            from PIL import Image

            with Image.open(actual_path) as img:
                image_width, image_height = img.size
        except Exception:
            image_width = 0
            image_height = 0

        # Structure the results
        regions = []
        for i, det in enumerate(detections):
            try:
                polygon, (text, score) = det
            except Exception:
                # Unexpected format; skip
                continue

            # Convert 4-point polygon to [x1, y1, x2, y2] format
            box_array = np.array(polygon).astype(int)
            if box_array.ndim != 2 or box_array.shape[1] != 2:
                continue

            x_coords = box_array[:, 0]
            y_coords = box_array[:, 1]
            bbox_xyxy = [
                int(x_coords.min()),
                int(y_coords.min()),
                int(x_coords.max()),
                int(y_coords.max()),
            ]

            regions.append(
                {
                    "index": i,
                    "text": text,
                    "confidence": float(score),
                    "bbox": bbox_xyxy,
                    "polygon": box_array.tolist(),
                }
            )

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
            output_path = str(artifacts_dir / f"{image_name}_ocr.png")
            
            # Create regions with text snippets as labels (truncated)
            regions_with_labels = []
            for i, region in enumerate(regions):
                text = region.get("text", "")
                # Truncate long text for display
                if len(text) > 30:
                    text = text[:27] + "..."
                regions_with_labels.append({
                    **region,
                    "_label": f"{i}: {text}" if text else str(i),
                })
            
            visualization_path = draw_bboxes_on_image(
                image_path=actual_path,
                regions=regions_with_labels,
                output_path=output_path,
                bbox_key="bbox",
                label_key="_label",
                default_color=(0, 255, 0),  # Green
            )
        except Exception as e:
            # Store error to include in response
            visualization_error = str(e)

        result = {
            "success": True,
            "region_count": len(regions),
            "image_path": image_path,  # Include original path for downstream tools
            "image_width": image_width,
            "image_height": image_height,
            "regions": regions,
        }
        
        if visualization_path:
            from document_extraction_mcp.tools.visualization import get_artifacts_dir
            result["visualization_path"] = visualization_path
            result["artifacts_dir"] = str(get_artifacts_dir(image_path))
        elif visualization_error:
            result["visualization_error"] = visualization_error

        return result

    except ImportError:
        return {
            "error": "PaddleOCR not installed. Run: pip install paddleocr paddlepaddle"
        }
    except Exception as e:
        return {"error": f"OCR extraction failed: {str(e)}"}
    finally:
        # Clean up temporary file (with retry for Windows file locking)
        if temp_image and os.path.exists(temp_image):
            try:
                os.unlink(temp_image)
            except PermissionError:
                pass  # File still in use, will be cleaned up by OS later
