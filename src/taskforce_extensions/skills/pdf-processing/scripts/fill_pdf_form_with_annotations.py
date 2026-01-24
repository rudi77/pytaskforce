#!/usr/bin/env python3
"""Fill non-fillable PDF forms using text annotations.

This script adds text annotations at specified bounding box locations to fill
PDF forms that do not have interactive form fields.

Usage:
    python fill_pdf_form_with_annotations.py input.pdf fields.json output.pdf
"""
import json
import sys
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText


def transform_coordinates(
    bbox: list[float],
    image_width: int,
    image_height: int,
    pdf_width: float,
    pdf_height: float,
) -> tuple[float, float, float, float]:
    """Transform bounding box from image coordinates to PDF coordinates.

    Image coordinates have origin at top-left with Y increasing downward.
    PDF coordinates have origin at bottom-left with Y increasing upward.

    Args:
        bbox: Bounding box in image coordinates [x_min, y_min, x_max, y_max].
        image_width: Width of the source image in pixels.
        image_height: Height of the source image in pixels.
        pdf_width: Width of the PDF page in points.
        pdf_height: Height of the PDF page in points.

    Returns:
        Bounding box in PDF coordinates (left, bottom, right, top).
    """
    x_scale = pdf_width / image_width
    y_scale = pdf_height / image_height

    left = bbox[0] * x_scale
    right = bbox[2] * x_scale

    # Flip Y coordinate (image Y=0 at top, PDF Y=0 at bottom)
    top = pdf_height - (bbox[1] * y_scale)
    bottom = pdf_height - (bbox[3] * y_scale)

    return left, bottom, right, top


def fill_pdf_form(
    input_pdf_path: str,
    fields_json_path: str,
    output_pdf_path: str,
) -> None:
    """Fill a PDF form using text annotations.

    Args:
        input_pdf_path: Path to input PDF.
        fields_json_path: Path to fields.json file.
        output_pdf_path: Path to save output PDF.
    """
    with open(fields_json_path) as f:
        fields_data: dict[str, Any] = json.load(f)

    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()

    writer.append(reader)

    # Get PDF page dimensions
    pdf_dimensions: dict[int, tuple[float, float]] = {}
    for i, page in enumerate(reader.pages):
        mediabox = page.mediabox
        pdf_dimensions[i + 1] = (float(mediabox.width), float(mediabox.height))

    annotations_added = 0

    for field in fields_data["form_fields"]:
        page_num = field["page_number"]

        # Get image dimensions for this page
        page_info = next(
            p for p in fields_data["pages"] if p["page_number"] == page_num
        )
        image_width = page_info["image_width"]
        image_height = page_info["image_height"]
        pdf_width, pdf_height = pdf_dimensions[page_num]

        # Transform coordinates
        transformed_entry_box = transform_coordinates(
            field["entry_bounding_box"],
            image_width,
            image_height,
            pdf_width,
            pdf_height,
        )

        # Skip fields without text content
        if "entry_text" not in field or "text" not in field["entry_text"]:
            continue

        entry_text = field["entry_text"]
        text = entry_text["text"]
        if not text:
            continue

        font_name = entry_text.get("font", "Arial")
        font_size = str(entry_text.get("font_size", 14)) + "pt"
        font_color = entry_text.get("font_color", "000000")

        annotation = FreeText(
            text=text,
            rect=transformed_entry_box,
            font=font_name,
            font_size=font_size,
            font_color=font_color,
            border_color=None,
            background_color=None,
        )

        writer.add_annotation(page_number=page_num - 1, annotation=annotation)
        annotations_added += 1

    with open(output_pdf_path, "wb") as output:
        writer.write(output)

    print(f"Successfully filled PDF form and saved to {output_pdf_path}")
    print(f"Added {annotations_added} text annotations")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 4:
        print(
            "Usage: fill_pdf_form_with_annotations.py "
            "[input pdf] [fields.json] [output pdf]"
        )
        sys.exit(1)

    input_pdf = sys.argv[1]
    fields_json = sys.argv[2]
    output_pdf = sys.argv[3]

    try:
        fill_pdf_form(input_pdf, fields_json, output_pdf)
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        sys.exit(1)
    except StopIteration:
        print("Error: Page dimensions not found in fields.json")
        sys.exit(1)
    except Exception as e:
        print(f"Error filling PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
