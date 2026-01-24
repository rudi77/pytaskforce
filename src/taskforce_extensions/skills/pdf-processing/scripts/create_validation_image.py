#!/usr/bin/env python3
"""Create validation images with bounding box overlays.

This script creates images that visualize the bounding boxes defined in a
fields.json file, making it easier to verify correct placement.

Usage:
    python create_validation_image.py page_number fields.json input.png output.png
"""
import json
import sys

from PIL import Image, ImageDraw


def create_validation_image(
    page_number: int,
    fields_json_path: str,
    input_path: str,
    output_path: str,
) -> None:
    """Create a validation image with bounding box overlays.

    Args:
        page_number: Page number to create validation image for.
        fields_json_path: Path to fields.json file.
        input_path: Path to input image (PNG).
        output_path: Path to save output image.
    """
    with open(fields_json_path) as f:
        data = json.load(f)

    img = Image.open(input_path)
    draw = ImageDraw.Draw(img)
    num_boxes = 0

    for field in data["form_fields"]:
        if field["page_number"] == page_number:
            entry_box = field["entry_bounding_box"]
            label_box = field["label_bounding_box"]

            # Draw red rectangle over entry bounding box
            # and blue rectangle over the label
            draw.rectangle(entry_box, outline="red", width=2)
            draw.rectangle(label_box, outline="blue", width=2)
            num_boxes += 2

    img.save(output_path)
    print(f"Created validation image at {output_path} with {num_boxes} bounding boxes")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 5:
        print(
            "Usage: create_validation_image.py "
            "[page number] [fields.json file] [input image path] [output image path]"
        )
        sys.exit(1)

    try:
        page_number = int(sys.argv[1])
        fields_json_path = sys.argv[2]
        input_image_path = sys.argv[3]
        output_image_path = sys.argv[4]

        create_validation_image(
            page_number, fields_json_path, input_image_path, output_image_path
        )
    except ValueError:
        print("Error: Page number must be an integer")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating validation image: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
