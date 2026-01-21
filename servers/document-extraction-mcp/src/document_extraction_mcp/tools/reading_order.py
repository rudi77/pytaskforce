"""Reading order tool using LayoutReader (LayoutLMv3).

Helper functions adapted from: https://github.com/ppaanngggg/layoutreader
"""

import json
from pathlib import Path
from typing import Any

import torch

from document_extraction_mcp.tools._stdio_silence import suppress_stdout
from document_extraction_mcp.tools.visualization import visualize_reading_order


def boxes2inputs(boxes: list[list[int]]) -> dict[str, Any]:
    """Convert bounding boxes to model input format.

    Args:
        boxes: List of bounding boxes in [left, top, right, bottom] format (0-1000 normalized)

    Returns:
        Dict with bbox tensor for model input
    """
    return {"bbox": torch.tensor(boxes).unsqueeze(0)}


def prepare_inputs(inputs: dict[str, Any], model: Any) -> dict[str, Any]:
    """Prepare inputs for the LayoutLMv3 model.

    Args:
        inputs: Dict with bbox tensor
        model: The LayoutLMv3ForTokenClassification model

    Returns:
        Dict with prepared tensors for model inference
    """
    bbox = inputs["bbox"]
    batch_size, seq_len, _ = bbox.shape

    # Create input_ids (all zeros, as we don't use text tokens)
    input_ids = torch.zeros(batch_size, seq_len, dtype=torch.long)

    # Create attention mask (all ones)
    attention_mask = torch.ones(batch_size, seq_len, dtype=torch.long)

    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "bbox": bbox,
    }


def parse_logits(logits: torch.Tensor, num_boxes: int) -> list[int]:
    """Parse model logits to reading order positions.

    The model predicts a position for each bounding box.
    We use argmax to get the most likely position for each box.

    Args:
        logits: Model output logits [seq_len, num_classes]
        num_boxes: Number of bounding boxes

    Returns:
        List of reading order positions (0-indexed)
    """
    # Get predictions for each box
    predictions = logits[:num_boxes].argmax(dim=-1).tolist()

    # Handle duplicate positions by creating a unique ordering
    # Sort boxes by their predicted position, breaking ties by original index
    indexed_preds = [(pred, i) for i, pred in enumerate(predictions)]
    indexed_preds.sort(key=lambda x: (x[0], x[1]))

    # Assign sequential positions
    reading_order = [0] * num_boxes
    for position, (_, original_idx) in enumerate(indexed_preds):
        reading_order[original_idx] = position

    return reading_order


def reading_order(
    regions: list[dict[str, Any]],
    image_path: str | None = None,
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
                # Clamp to valid range
                left = max(0, min(1000, left))
                top = max(0, min(1000, top))
                right = max(0, min(1000, right))
                bottom = max(0, min(1000, bottom))
                boxes.append([left, top, right, bottom])
            else:
                boxes.append([0, 0, 0, 0])

        # Load LayoutReader model from Hugging Face
        # Suppress stdout during model download/loading to prevent MCP protocol corruption
        model_slug = "hantian/layoutreader"
        with suppress_stdout():
            layout_model = LayoutLMv3ForTokenClassification.from_pretrained(model_slug)
        layout_model.eval()

        # Prepare inputs for the model
        inputs = boxes2inputs(boxes)
        inputs = prepare_inputs(inputs, layout_model)

        # Run inference
        with torch.no_grad():
            outputs = layout_model(**inputs)
            logits = outputs.logits.squeeze(0)

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

        result = {
            "success": True,
            "region_count": len(regions),
            "reading_order": reading_positions,
            "ordered_regions": ordered_regions,
            "ordered_text": ordered_text,
        }
        
        # Save visualization artifact if image path is provided
        if image_path and Path(image_path).exists():
            try:
                from document_extraction_mcp.tools.visualization import (
                    draw_bboxes_on_image,
                    get_artifacts_dir,
                )
                
                artifacts_dir = get_artifacts_dir(image_path)
                image_name = Path(image_path).stem
                output_path = str(artifacts_dir / f"{image_name}_reading_order.png")
                
                # Create regions with reading position as label
                regions_with_labels = []
                for region in ordered_regions:
                    reading_pos = region.get("reading_position", 0)
                    regions_with_labels.append({
                        **region,
                        "_label": f"#{reading_pos}",
                    })
                
                visualization_path = draw_bboxes_on_image(
                    image_path=image_path,
                    regions=regions_with_labels,
                    output_path=output_path,
                    bbox_key="bbox",
                    label_key="_label",
                    default_color=(0, 0, 255),  # Blue
                )
                result["visualization_path"] = visualization_path
                result["artifacts_dir"] = str(artifacts_dir)
            except Exception as e:
                # Store error to include in response
                result["visualization_error"] = str(e)

        return result

    except ImportError as e:
        missing = str(e)
        if "transformers" in missing.lower():
            return {"error": "Transformers not installed. Run: pip install transformers torch"}
        else:
            return {"error": f"Missing dependency: {missing}"}
    except Exception as e:
        return {"error": f"Reading order detection failed: {str(e)}"}


def reading_order_from_json(
    regions_json: str,
    image_path_json: str | None = None,
    image_width_json: str | None = None,
    image_height_json: str | None = None,
) -> dict[str, Any]:
    """Subprocess-friendly wrapper for `reading_order`.

    Accepts JSON-encoded inputs, so the MCP server can run this function in a
    fresh subprocess without worrying about complex argument marshaling.
    """
    try:
        regions = json.loads(regions_json)
        image_path = (
            json.loads(image_path_json) if image_path_json is not None else None
        )
        image_width = (
            json.loads(image_width_json) if image_width_json is not None else None
        )
        image_height = (
            json.loads(image_height_json) if image_height_json is not None else None
        )
    except Exception as e:
        return {"error": f"Invalid JSON inputs: {str(e)}"}

    return reading_order(
        regions,
        image_path=image_path,
        image_width=image_width,
        image_height=image_height,
    )
