#!/usr/bin/env python3
"""Script to determine whether a PDF has fillable form fields.

Usage:
    python check_fillable_fields.py input.pdf
"""
import sys

from pypdf import PdfReader


def main() -> None:
    """Check if PDF has fillable form fields."""
    if len(sys.argv) != 2:
        print("Usage: check_fillable_fields.py [input pdf]")
        sys.exit(1)

    pdf_path = sys.argv[1]

    try:
        reader = PdfReader(pdf_path)
        fields = reader.get_fields()

        if fields:
            print("This PDF has fillable form fields")
            print(f"Found {len(fields)} field(s)")
        else:
            print(
                "This PDF does not have fillable form fields; "
                "you will need to visually determine where to enter data"
            )
    except FileNotFoundError:
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
