"""Image cropping tool."""

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


def crop_region(
    image_path: str,
    bbox: list[float],
    padding: int = 10,
) -> dict[str, Any]:
    """Crop a region from an image and return as base64.

    Args:
        image_path: Path to the input image file
        bbox: Bounding box as [x1, y1, x2, y2]
        padding: Padding around the region in pixels

    Returns:
        Dict with base64-encoded cropped image and metadata
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": f"Image file not found: {image_path}"}

    try:
        image = Image.open(path)

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
