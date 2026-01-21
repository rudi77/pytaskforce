"""Visualization utilities for document extraction tools.

Provides functions to draw bounding boxes on images and save visualization artifacts.
"""

import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def get_artifacts_dir(image_path: str) -> Path:
    """Get the artifacts directory for a given image path.
    
    Creates a directory next to the input image with '_artifacts' suffix.
    
    Args:
        image_path: Path to the input image
        
    Returns:
        Path to the artifacts directory
    """
    image_path_obj = Path(image_path)
    artifacts_dir = image_path_obj.parent / f"{image_path_obj.stem}_artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def draw_bboxes_on_image(
    image_path: str,
    regions: list[dict[str, Any]],
    output_path: str | None = None,
    bbox_key: str = "bbox",
    label_key: str | None = None,
    label_prefix: str = "",
    colors: dict[str, tuple[int, int, int]] | None = None,
    default_color: tuple[int, int, int] = (255, 0, 0),  # Red
) -> str:
    """Draw bounding boxes on an image and save the visualization.
    
    Args:
        image_path: Path to the input image
        regions: List of region dicts with bounding boxes
        output_path: Optional output path. If None, auto-generates in artifacts dir
        bbox_key: Key in region dict for bounding box (default: "bbox")
        label_key: Optional key in region dict for label text
        label_prefix: Optional prefix for labels (e.g., "Region 1:")
        colors: Optional dict mapping label values to RGB colors
        default_color: Default color for boxes without specific color (RGB tuple)
        
    Returns:
        Path to the saved visualization image
    """
    # Load image and convert to RGB if necessary
    image = Image.open(image_path)
    if image.mode != "RGB":
        image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    
    # Try to load a font (fallback to default if not available)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except Exception:
            font = ImageFont.load_default()
    
    # Draw bounding boxes
    for i, region in enumerate(regions):
        bbox = region.get(bbox_key, [])
        if len(bbox) < 4:
            continue
            
        x1, y1, x2, y2 = bbox[:4]
        
        # Determine color
        color = default_color
        if colors and label_key:
            label = region.get(label_key, "")
            color = colors.get(label, default_color)
        elif colors and i < len(colors):
            # Use index-based color if no label key
            color = list(colors.values())[i % len(colors)]
        
        # Draw rectangle
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        
        # Draw label if available
        if label_key:
            label_text = region.get(label_key, "")
            if label_prefix:
                label_text = f"{label_prefix}{label_text}"
            elif label_text:
                label_text = f"{i}: {label_text}"
            else:
                label_text = str(i)
        else:
            label_text = str(i)
        
        # Draw text background and text
        text_bbox = draw.textbbox((x1, y1 - 20), label_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        # Draw semi-transparent white background
        bg_y1 = max(0, y1 - text_height - 4)
        bg_y2 = y1
        draw.rectangle(
            [x1, bg_y1, x1 + text_width + 4, bg_y2],
            fill=(255, 255, 255),
            outline=color,
        )
        draw.text((x1 + 2, bg_y1 + 2), label_text, fill=color, font=font)
    
    # Determine output path
    if output_path is None:
        artifacts_dir = get_artifacts_dir(image_path)
        image_name = Path(image_path).stem
        output_path = str(artifacts_dir / f"{image_name}_visualization.png")
    
    # Save image
    image.save(output_path)
    return output_path


def visualize_layout_regions(
    image_path: str,
    regions: list[dict[str, Any]],
    output_path: str | None = None,
) -> str:
    """Visualize layout detection regions with color-coded region types.
    
    Args:
        image_path: Path to the input image
        regions: List of layout regions with 'region_type' and 'bbox'
        output_path: Optional output path
        
    Returns:
        Path to the saved visualization image
    """
    # Color mapping for different region types
    type_colors = {
        "Text": (0, 255, 0),      # Green
        "Table": (255, 0, 0),     # Red
        "Figure": (0, 0, 255),    # Blue
        "Chart": (255, 165, 0),   # Orange
        "Title": (255, 0, 255),   # Magenta
        "List": (0, 255, 255),    # Cyan
    }
    
    if output_path is None:
        artifacts_dir = get_artifacts_dir(image_path)
        image_name = Path(image_path).stem
        output_path = str(artifacts_dir / f"{image_name}_layout.png")
    
    return draw_bboxes_on_image(
        image_path=image_path,
        regions=regions,
        output_path=output_path,
        bbox_key="bbox",
        label_key="region_type",
        colors=type_colors,
        default_color=(128, 128, 128),  # Gray for unknown types
    )


def visualize_reading_order(
    image_path: str,
    ordered_regions: list[dict[str, Any]],
    output_path: str | None = None,
) -> str:
    """Visualize reading order with numbered sequence.
    
    Args:
        image_path: Path to the input image
        ordered_regions: List of ordered regions with 'reading_position' and 'bbox'
        output_path: Optional output path
        
    Returns:
        Path to the saved visualization image
    """
    if output_path is None:
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
    
    return draw_bboxes_on_image(
        image_path=image_path,
        regions=regions_with_labels,
        output_path=output_path,
        bbox_key="bbox",
        label_key="_label",
        default_color=(0, 0, 255),  # Blue
    )


def visualize_ocr_regions(
    image_path: str,
    regions: list[dict[str, Any]],
    output_path: str | None = None,
) -> str:
    """Visualize OCR regions with text snippets.
    
    Args:
        image_path: Path to the input image
        regions: List of OCR regions with 'text' and 'bbox'
        output_path: Optional output path
        
    Returns:
        Path to the saved visualization image
    """
    if output_path is None:
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
    
    return draw_bboxes_on_image(
        image_path=image_path,
        regions=regions_with_labels,
        output_path=output_path,
        bbox_key="bbox",
        label_key="_label",
        default_color=(0, 255, 0),  # Green
    )
