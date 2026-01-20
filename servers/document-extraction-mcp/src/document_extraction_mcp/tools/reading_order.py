"""Reading order tool using LayoutReader (LayoutLMv3)."""

from typing import Any


def reading_order(
    regions: list[dict[str, Any]],
    image_width: float | None = None,
    image_height: float | None = None,
) -> dict[str, Any]:
    """Determine reading order of OCR regions using LayoutReader.

    Args:
        regions: List of OCR regions with 'text' and 'bbox' [x1, y1, x2, y2]
        image_width: Optional image width (estimated from boxes if not provided)
        image_height: Optional image height (estimated from boxes if not provided)

    Returns:
        Dict with ordered regions and reading sequence
    """
    if not regions:
        return {"error": "No regions provided"}

    try:
        # Lazy imports
        from layoutreader.v3.helpers import boxes2inputs, parse_logits, prepare_inputs
        from transformers import LayoutLMv3ForTokenClassification

        # Estimate image dimensions from bounding boxes if not provided
        if image_width is None or image_height is None:
            max_x = max_y = 0
            for region in regions:
                bbox = region.get("bbox", [0, 0, 0, 0])
                if len(bbox) >= 4:
                    max_x = max(max_x, bbox[2])
                    max_y = max(max_y, bbox[3])
            image_width = image_width or max_x * 1.1
            image_height = image_height or max_y * 1.1

        if image_width == 0 or image_height == 0:
            return {"error": "Could not determine image dimensions"}

        # Convert bboxes to LayoutReader format (normalized to 0-1000)
        boxes = []
        for region in regions:
            bbox = region.get("bbox", [0, 0, 0, 0])
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox
                # Normalize to 0-1000 range
                left = int((x1 / image_width) * 1000)
                top = int((y1 / image_height) * 1000)
                right = int((x2 / image_width) * 1000)
                bottom = int((y2 / image_height) * 1000)
                boxes.append([left, top, right, bottom])
            else:
                boxes.append([0, 0, 0, 0])

        # Load LayoutReader model
        model_slug = "hantian/layoutreader"
        layout_model = LayoutLMv3ForTokenClassification.from_pretrained(model_slug)

        # Prepare inputs for the model
        inputs = boxes2inputs(boxes)
        inputs = prepare_inputs(inputs, layout_model)

        # Run inference
        logits = layout_model(**inputs).logits.cpu().squeeze(0)

        # Parse the model's outputs to get reading order
        reading_positions = parse_logits(logits, len(boxes))

        # Create ordered regions
        ordered_regions = []
        for i, region in enumerate(regions):
            position = reading_positions[i] if i < len(reading_positions) else i
            ordered_regions.append(
                {
                    "original_index": i,
                    "reading_position": position,
                    "text": region.get("text", ""),
                    "bbox": region.get("bbox", []),
                    "confidence": region.get("confidence", 0.0),
                }
            )

        # Sort by reading position
        ordered_regions.sort(key=lambda x: x["reading_position"])

        # Extract ordered text
        ordered_text = [r["text"] for r in ordered_regions]

        return {
            "success": True,
            "region_count": len(regions),
            "reading_order": reading_positions,
            "ordered_regions": ordered_regions,
            "ordered_text": ordered_text,
        }

    except ImportError as e:
        missing = str(e)
        if "layoutreader" in missing.lower():
            return {
                "error": "LayoutReader not installed. Run: pip install git+https://github.com/ppaanngggg/layoutreader.git"
            }
        elif "transformers" in missing.lower():
            return {"error": "Transformers not installed. Run: pip install transformers torch"}
        else:
            return {"error": f"Missing dependency: {missing}"}
    except Exception as e:
        return {"error": f"Reading order detection failed: {str(e)}"}
