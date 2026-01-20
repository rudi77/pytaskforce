"""Layout detection tool using PaddleOCR LayoutDetection."""

from pathlib import Path
from typing import Any


def layout_detect(image_path: str) -> dict[str, Any]:
    """Detect document layout regions using PaddleOCR LayoutDetection.

    Args:
        image_path: Path to the input image file

    Returns:
        Dict with layout regions containing type, bounding box, and confidence
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": f"Image file not found: {image_path}"}

    try:
        # Lazy import to avoid loading PaddleOCR until needed
        from paddleocr import LayoutDetection

        # Initialize layout detection engine
        layout_engine = LayoutDetection()

        # Run layout detection
        result = layout_engine.predict(str(path))

        # Extract regions from result
        layout_data = result[0]
        boxes = layout_data.get("boxes", [])

        regions = []
        for i, box in enumerate(boxes):
            region = {
                "region_id": i,
                "region_type": box.get("label", "unknown"),
                "confidence": float(box.get("score", 0.0)),
                "bbox": [int(x) for x in box.get("coordinate", [0, 0, 0, 0])],
            }
            regions.append(region)

        # Sort by confidence (highest first)
        regions.sort(key=lambda x: x["confidence"], reverse=True)

        # Group by type for summary
        type_counts = {}
        for r in regions:
            rtype = r["region_type"]
            type_counts[rtype] = type_counts.get(rtype, 0) + 1

        return {
            "success": True,
            "region_count": len(regions),
            "type_summary": type_counts,
            "regions": regions,
        }

    except ImportError:
        return {"error": "PaddleOCR not installed. Run: pip install paddleocr paddlepaddle"}
    except Exception as e:
        return {"error": f"Layout detection failed: {str(e)}"}
