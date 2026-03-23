"""Extract text from PDF using docling (handles scanned/image-based PDFs with OCR).

Usage:
    python extract_text_with_ocr.py <pdf_path> [--output-format markdown|text]

Returns extracted text/markdown to stdout. Uses GPU if available.
Falls back to pypdf for text-based PDFs (faster, no OCR needed).
"""

import sys
from pathlib import Path


def extract_with_pypdf(pdf_path: str) -> str | None:
    """Try fast extraction with pypdf first (text-based PDFs only)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
        # If we got meaningful text (not just whitespace), return it
        if text.strip() and len(text.strip()) > 50:
            return text.strip()
        return None
    except Exception:
        return None


def extract_with_docling(pdf_path: str, output_format: str = "markdown") -> str:
    """Extract text using docling (handles scanned PDFs with OCR)."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(pdf_path)

    if output_format == "markdown":
        return result.document.export_to_markdown()
    else:
        return result.document.export_to_text()


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_text_with_ocr.py <pdf_path> [--output-format markdown|text]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_format = "markdown"

    if "--output-format" in sys.argv:
        idx = sys.argv.index("--output-format")
        if idx + 1 < len(sys.argv):
            output_format = sys.argv[idx + 1]

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Try fast pypdf first
    text = extract_with_pypdf(pdf_path)
    if text:
        print(text)
        return

    # Fall back to docling (OCR)
    print("[Using docling OCR for scanned PDF]", file=sys.stderr)
    text = extract_with_docling(pdf_path, output_format)
    print(text)


if __name__ == "__main__":
    main()
