---
name: pdf-processing
description: Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. Use when working with PDF files, extracting content from PDFs, or filling PDF forms.
---

# PDF Processing Skill

This skill provides comprehensive PDF manipulation capabilities including:
- Text and table extraction
- PDF creation and modification
- Document merging and splitting
- Form detection and filling
- Image extraction and conversion

## Required Dependencies

Ensure these Python libraries are installed:

```bash
uv add pypdf pdfplumber reportlab pdf2image pillow
```

For command-line PDF tools (optional but recommended):
```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils qpdf

# macOS
brew install poppler qpdf
```

## Quick Reference

### Core Libraries

| Library | Purpose | Key Features |
|---------|---------|--------------|
| **pypdf** | PDF manipulation | Merge, split, rotate, extract metadata |
| **pdfplumber** | Content extraction | Text with layout, table extraction |
| **reportlab** | PDF generation | Create PDFs programmatically |
| **pdf2image** | Image conversion | Convert PDF pages to images |

## Common Operations

### 1. Text Extraction

```python
import pdfplumber

def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    text_content = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_content.append(text)
    return "\n\n".join(text_content)
```

### 2. Table Extraction

```python
import pdfplumber
import pandas as pd

def extract_tables(pdf_path: str) -> list:
    """Extract all tables from a PDF as DataFrames."""
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            for table in page_tables:
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    tables.append(df)
    return tables
```

### 3. Merge PDFs

```python
from pypdf import PdfWriter

def merge_pdfs(input_paths: list, output_path: str) -> None:
    """Merge multiple PDFs into a single document."""
    writer = PdfWriter()
    for path in input_paths:
        writer.append(path)
    with open(output_path, "wb") as f:
        writer.write(f)
```

### 4. Split PDF

```python
from pypdf import PdfReader, PdfWriter

def split_pdf(input_path: str, output_dir: str) -> list:
    """Split a PDF into individual pages."""
    reader = PdfReader(input_path)
    output_files = []
    for i, page in enumerate(reader.pages):
        writer = PdfWriter()
        writer.add_page(page)
        output_path = f"{output_dir}/page_{i + 1}.pdf"
        with open(output_path, "wb") as f:
            writer.write(f)
        output_files.append(output_path)
    return output_files
```

### 5. Rotate Pages

```python
from pypdf import PdfReader, PdfWriter

def rotate_pages(input_path: str, output_path: str, degrees: int = 90) -> None:
    """Rotate all pages in a PDF by specified degrees."""
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)
```

### 6. Extract Metadata

```python
from pypdf import PdfReader

def get_metadata(pdf_path: str) -> dict:
    """Extract PDF metadata."""
    reader = PdfReader(pdf_path)
    meta = reader.metadata
    return {
        "title": meta.title if meta else None,
        "author": meta.author if meta else None,
        "subject": meta.subject if meta else None,
        "creator": meta.creator if meta else None,
        "pages": len(reader.pages),
    }
```

### 7. Convert to Images

```python
from pdf2image import convert_from_path

def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 200) -> list:
    """Convert PDF pages to PNG images."""
    images = convert_from_path(pdf_path, dpi=dpi)
    output_paths = []
    for i, image in enumerate(images):
        output_path = f"{output_dir}/page_{i + 1}.png"
        image.save(output_path)
        output_paths.append(output_path)
    return output_paths
```

### 8. Create PDF from Scratch

```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def create_pdf(output_path: str, content: list) -> None:
    """Create a simple PDF with text content."""
    c = canvas.Canvas(output_path, pagesize=letter)
    y_position = 750
    for line in content:
        c.drawString(72, y_position, line)
        y_position -= 20
        if y_position < 72:
            c.showPage()
            y_position = 750
    c.save()
```

## Command-Line Tools

### pdftotext (poppler-utils)

Extract text with layout preservation:
```bash
pdftotext -layout input.pdf output.txt
```

Extract with bounding box info:
```bash
pdftotext -bbox-layout input.pdf output.html
```

### qpdf

Merge PDFs:
```bash
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf
```

Split into single pages:
```bash
qpdf input.pdf --split-pages output_%d.pdf
```

Rotate pages:
```bash
qpdf input.pdf --rotate=90:1-5 output.pdf
```

Decrypt password-protected PDF:
```bash
qpdf --password=secret --decrypt protected.pdf decrypted.pdf
```

## Form Handling

This skill includes specialized workflows for PDF forms. See the bundled `forms.md` resource for detailed instructions on:

1. **Detecting fillable fields** - Check if a PDF has form fields
2. **Extracting field information** - Get field names, types, and locations
3. **Filling fillable forms** - Programmatically fill form fields
4. **Handling non-fillable forms** - Add text annotations to static PDFs

### Quick Form Detection

```python
from pypdf import PdfReader

def has_fillable_fields(pdf_path: str) -> bool:
    """Check if PDF has fillable form fields."""
    reader = PdfReader(pdf_path)
    fields = reader.get_fields()
    return bool(fields)
```

## Bundled Scripts

This skill includes ready-to-use scripts in the `scripts/` directory:

| Script | Purpose |
|--------|---------|
| `check_fillable_fields.py` | Determine if PDF has form fields |
| `extract_form_field_info.py` | Extract form field details to JSON |
| `fill_fillable_fields.py` | Fill form fields from JSON values |
| `convert_pdf_to_images.py` | Convert PDF pages to PNG images |
| `check_bounding_boxes.py` | Validate bounding box definitions |
| `create_validation_image.py` | Create visual validation overlays |
| `fill_pdf_form_with_annotations.py` | Fill non-fillable forms with annotations |

### Running Scripts

```bash
# Check for fillable fields
python scripts/check_fillable_fields.py input.pdf

# Extract form field info
python scripts/extract_form_field_info.py input.pdf fields.json

# Fill fillable form
python scripts/fill_fillable_fields.py input.pdf field_values.json output.pdf

# Convert to images
python scripts/convert_pdf_to_images.py input.pdf ./output_images/
```

## Advanced Topics

For advanced PDF processing techniques, see the bundled `reference.md` resource covering:

- OCR for scanned documents
- Watermarking
- Password protection
- Image extraction
- Performance optimization
- Error handling strategies

## Error Handling

Common issues and solutions:

### Encrypted PDFs
```python
from pypdf import PdfReader

reader = PdfReader("encrypted.pdf")
if reader.is_encrypted:
    reader.decrypt("password")
```

### Corrupted PDFs
Use qpdf to attempt repair:
```bash
qpdf --check input.pdf  # Check for issues
qpdf input.pdf repaired.pdf  # Attempt repair
```

### Scanned PDFs (no text layer)
For scanned documents without embedded text, use OCR:
```python
import pytesseract
from pdf2image import convert_from_path

def ocr_pdf(pdf_path: str) -> str:
    """Extract text from scanned PDF using OCR."""
    images = convert_from_path(pdf_path)
    text = []
    for image in images:
        text.append(pytesseract.image_to_string(image))
    return "\n\n".join(text)
```

## Best Practices

1. **Always close file handles** - Use context managers (`with` statements)
2. **Check for encryption** - Handle encrypted PDFs gracefully
3. **Validate output** - Verify generated PDFs open correctly
4. **Handle large files** - Process pages individually for memory efficiency
5. **Use appropriate DPI** - Balance quality vs file size for images
