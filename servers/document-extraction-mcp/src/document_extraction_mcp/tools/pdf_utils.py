"""PDF utilities for converting PDF pages to images."""

import tempfile
from pathlib import Path
from typing import Generator


def is_pdf(file_path: str | Path) -> bool:
    """Check if file is a PDF."""
    return str(file_path).lower().endswith(".pdf")


def pdf_to_images(pdf_path: str | Path, dpi: int = 200) -> list[str]:
    """Convert PDF pages to temporary image files.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution for rendering (default: 200)

    Returns:
        List of paths to temporary PNG files for each page
    """
    import fitz  # PyMuPDF

    temp_files = []
    doc = fitz.open(str(pdf_path))

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Render page to image
            mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale factor
            pix = page.get_pixmap(matrix=mat)

            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f"_page{page_num + 1}.png",
                delete=False,
            )
            temp_file.close()
            pix.save(temp_file.name)

            temp_files.append(temp_file.name)
    finally:
        doc.close()

    return temp_files


def pdf_first_page_to_image(pdf_path: str | Path, dpi: int = 200) -> str:
    """Convert first page of PDF to a temporary image file.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution for rendering (default: 200)

    Returns:
        Path to temporary PNG file
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))

    try:
        page = doc[0]

        # Render page to image
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale factor
        pix = page.get_pixmap(matrix=mat)

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(
            suffix="_page1.png",
            delete=False,
        )
        temp_file.close()
        pix.save(temp_file.name)

        return temp_file.name
    finally:
        doc.close()


def ensure_image(file_path: str | Path, dpi: int = 200) -> tuple[str, bool]:
    """Ensure file is an image, converting PDF if necessary.

    Args:
        file_path: Path to image or PDF file
        dpi: Resolution for PDF rendering

    Returns:
        Tuple of (image_path, is_temporary)
        If is_temporary is True, caller should delete the file after use
    """
    if is_pdf(file_path):
        return pdf_first_page_to_image(file_path, dpi), True
    return str(file_path), False
