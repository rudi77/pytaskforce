"""Image cropping tool."""

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from document_extraction_mcp.tools.pdf_utils import ensure_image


def crop_region(
    image_path: str,
    bbox: list[float],
    padding: int = 10,
) -> dict[str, Any]:
    """Crop a region from an image or PDF and return as base64.

    Args:
        image_path: Path to the input image or PDF file
        bbox: Bounding box as [x1, y1, x2, y2]
        padding: Padding around the region in pixels

    Returns:
        Dict with base64-encoded cropped image and metadata
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

        image = Image.open(actual_path)

        # Unpack bounding box
        x1, y1, x2, y2 = bbox

        # Apply padding with bounds checking
        x1 = max(0, int(x1) - padding)
        y1 = max(0, int(y1) - padding)
        x2 = min(image.width, int(x2) + padding)
        y2 = min(image.height, int(y2) + padding)

        # Crop the region
        cropped = image.crop((x1, y1, x2, y2))

        # Convert to base64
        buffer = BytesIO()
        cropped.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return {
            "success": True,
            "image_base64": image_base64,
            "width": cropped.width,
            "height": cropped.height,
            "original_bbox": bbox,
            "padded_bbox": [x1, y1, x2, y2],
        }

    except Exception as e:
        return {"error": f"Failed to crop image: {str(e)}"}
    finally:
        # Clean up temporary file (with retry for Windows file locking)
        if temp_image and os.path.exists(temp_image):
            try:
                os.unlink(temp_image)
            except PermissionError:
                pass  # File still in use, will be cleaned up by OS later
