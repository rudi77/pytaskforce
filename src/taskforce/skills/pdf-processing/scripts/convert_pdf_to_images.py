#!/usr/bin/env python3
"""Convert each page of a PDF to a PNG image.

Usage:
    python convert_pdf_to_images.py input.pdf output_directory/
"""
import os
import sys

from pdf2image import convert_from_path


def convert(pdf_path: str, output_dir: str, max_dim: int = 1000) -> None:
    """Convert PDF pages to PNG images.

    Args:
        pdf_path: Path to input PDF file.
        output_dir: Directory to save output images.
        max_dim: Maximum dimension (width/height) for output images.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    images = convert_from_path(pdf_path, dpi=200)

    for i, image in enumerate(images):
        # Scale image if needed to keep width/height under max_dim
        width, height = image.size
        if width > max_dim or height > max_dim:
            scale_factor = min(max_dim / width, max_dim / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height))

        image_path = os.path.join(output_dir, f"page_{i + 1}.png")
        image.save(image_path)
        print(f"Saved page {i + 1} as {image_path} (size: {image.size})")

    print(f"Converted {len(images)} pages to PNG images")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: convert_pdf_to_images.py [input pdf] [output directory]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_directory = sys.argv[2]

    try:
        convert(pdf_path, output_directory)
    except FileNotFoundError:
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error converting PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
