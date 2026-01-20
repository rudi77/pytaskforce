"""OCR extraction tool using PaddleOCR."""

from pathlib import Path
from typing import Any

import numpy as np


def ocr_extract(image_path: str) -> dict[str, Any]:
    """Extract text from an image using PaddleOCR.

    Args:
        image_path: Path to the input image file

    Returns:
        Dict with OCR regions containing text, bounding boxes, and confidence scores
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": f"Image file not found: {image_path}"}

    try:
        # Lazy import to avoid loading PaddleOCR until needed
        from paddleocr import PaddleOCR

        # Initialize OCR engine (cached globally in server.py for reuse)
        ocr = PaddleOCR(lang="en", show_log=False)

        # Run OCR
        result = ocr.predict(str(path))
        page = result[0]

        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        boxes = page.get("rec_polys", [])

        # Get processed image dimensions
        processed_img = page.get("doc_preprocessor_res", {}).get("output_img")
        if processed_img is not None:
            image_height, image_width = processed_img.shape[:2]
        else:
            # Fallback: estimate from bounding boxes
            if boxes is not None and len(boxes) > 0:
                all_boxes = np.array(boxes)
                image_width = int(all_boxes[:, :, 0].max() * 1.1)
                image_height = int(all_boxes[:, :, 1].max() * 1.1)
            else:
                image_width = 0
                image_height = 0

        # Structure the results
        regions = []
        for i, (text, score, box) in enumerate(zip(texts, scores, boxes)):
            # Convert 4-point polygon to [x1, y1, x2, y2] format
            box_array = np.array(box).astype(int)
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

        return {
            "success": True,
            "region_count": len(regions),
            "image_width": image_width,
            "image_height": image_height,
            "regions": regions,
        }

    except ImportError:
        return {"error": "PaddleOCR not installed. Run: pip install paddleocr paddlepaddle"}
    except Exception as e:
        return {"error": f"OCR extraction failed: {str(e)}"}
