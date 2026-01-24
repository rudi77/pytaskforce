# PDF Processing Advanced Reference

This reference covers advanced PDF processing techniques, library comparisons, and performance optimization strategies.

## Core Libraries Overview

### Python Libraries

| Library | License | Best For |
|---------|---------|----------|
| **pypdfium2** | Apache/BSD | High-quality rendering, image generation |
| **pdfplumber** | MIT | Text extraction with coordinates, complex tables |
| **reportlab** | BSD | Creating professional PDFs programmatically |
| **pypdf** | BSD | Manipulating existing PDF documents |

### JavaScript Libraries

| Library | License | Best For |
|---------|---------|----------|
| **pdf-lib** | MIT | Creating and modifying PDFs in Node.js/browser |
| **pdfjs-dist** | Apache | Browser-based PDF rendering (Mozilla) |

### Command-Line Tools

| Tool | License | Best For |
|------|---------|----------|
| **poppler-utils** | GPL-2 | `pdftotext`, `pdftoppm`, `pdfimages` |
| **qpdf** | Apache | Advanced manipulation, repair, encryption |

## Text Extraction Techniques

### Basic Extraction with pdfplumber

```python
import pdfplumber

def extract_text_with_layout(pdf_path: str) -> list[dict]:
    """Extract text with position information."""
    pages_data = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            chars = page.chars
            words = page.extract_words()
            pages_data.append({
                "page": i + 1,
                "text": page.extract_text(),
                "word_count": len(words),
                "chars": chars,
            })
    return pages_data
```

### Bounding Box Extraction with pdftotext

```bash
# Extract text with bounding box coordinates
pdftotext -bbox-layout input.pdf output.html
```

The output HTML contains elements with position data:
```html
<word xMin="72.0" yMin="720.0" xMax="150.0" yMax="735.0">Example</word>
```

### Custom Table Extraction Settings

```python
import pdfplumber

def extract_tables_custom(pdf_path: str) -> list:
    """Extract tables with custom detection settings."""
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "edge_min_length": 10,
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
    }

    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables(table_settings)
            tables.extend(page_tables)
    return tables
```

## Image Processing

### High-Resolution Rendering with pypdfium2

```python
import pypdfium2 as pdfium

def render_page_high_quality(pdf_path: str, page_num: int, scale: float = 4.0) -> bytes:
    """Render a PDF page at high resolution."""
    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[page_num]

    # Scale 4.0 = 288 DPI (72 * 4)
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()

    # Convert to bytes
    from io import BytesIO
    buffer = BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()
```

### Extract Embedded Images

```bash
# Extract all embedded images
pdfimages -all input.pdf output_prefix

# Extract as PNG
pdfimages -png input.pdf output_prefix

# Extract as JPEG
pdfimages -j input.pdf output_prefix
```

### Python Image Extraction

```python
from pypdf import PdfReader
from PIL import Image
from io import BytesIO

def extract_images(pdf_path: str) -> list:
    """Extract all embedded images from PDF."""
    reader = PdfReader(pdf_path)
    images = []

    for page in reader.pages:
        if "/XObject" in page["/Resources"]:
            x_objects = page["/Resources"]["/XObject"].get_object()
            for obj in x_objects:
                if x_objects[obj]["/Subtype"] == "/Image":
                    data = x_objects[obj].get_data()
                    images.append(data)

    return images
```

## PDF Generation

### Professional Reports with reportlab

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

def create_report(output_path: str, title: str, sections: list) -> None:
    """Create a professional PDF report."""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
    )
    story.append(Paragraph(title, title_style))

    # Sections
    for section in sections:
        story.append(Paragraph(section['heading'], styles['Heading2']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(section['content'], styles['Normal']))
        story.append(Spacer(1, 20))

    doc.build(story)
```

### Tables with Styling

```python
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors

def create_styled_table(data: list) -> Table:
    """Create a styled table for PDF."""
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    return table
```

## Document Manipulation

### Page Cropping

```python
from pypdf import PdfReader, PdfWriter

def crop_pages(input_path: str, output_path: str, margins: tuple) -> None:
    """Crop pages with specified margins (left, bottom, right, top)."""
    reader = PdfReader(input_path)
    writer = PdfWriter()

    left, bottom, right, top = margins

    for page in reader.pages:
        page.mediabox.lower_left = (
            page.mediabox.lower_left[0] + left,
            page.mediabox.lower_left[1] + bottom,
        )
        page.mediabox.upper_right = (
            page.mediabox.upper_right[0] - right,
            page.mediabox.upper_right[1] - top,
        )
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)
```

### Watermarking

```python
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

def add_watermark(input_path: str, output_path: str, watermark_text: str) -> None:
    """Add a diagonal watermark to all pages."""
    # Create watermark PDF
    watermark_buffer = BytesIO()
    c = canvas.Canvas(watermark_buffer, pagesize=letter)
    c.setFont("Helvetica", 50)
    c.setFillColorRGB(0.5, 0.5, 0.5, alpha=0.3)
    c.saveState()
    c.translate(300, 400)
    c.rotate(45)
    c.drawCentredString(0, 0, watermark_text)
    c.restoreState()
    c.save()
    watermark_buffer.seek(0)

    watermark_reader = PdfReader(watermark_buffer)
    watermark_page = watermark_reader.pages[0]

    reader = PdfReader(input_path)
    writer = PdfWriter()

    for page in reader.pages:
        page.merge_page(watermark_page)
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)
```

### Password Protection

```python
from pypdf import PdfReader, PdfWriter

def encrypt_pdf(input_path: str, output_path: str, user_password: str, owner_password: str = None) -> None:
    """Encrypt PDF with passwords."""
    reader = PdfReader(input_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    writer.encrypt(
        user_password=user_password,
        owner_password=owner_password or user_password,
        permissions_flag=0b111111111100,  # Allow all except modify
    )

    with open(output_path, "wb") as f:
        writer.write(f)

def decrypt_pdf(input_path: str, output_path: str, password: str) -> None:
    """Decrypt a password-protected PDF."""
    reader = PdfReader(input_path)
    reader.decrypt(password)

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)
```

## OCR for Scanned Documents

### Using pytesseract

```python
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

def ocr_pdf(pdf_path: str, language: str = "eng") -> str:
    """Perform OCR on scanned PDF."""
    images = convert_from_path(pdf_path, dpi=300)
    text_parts = []

    for i, image in enumerate(images):
        # Preprocess image for better OCR
        image = image.convert("L")  # Convert to grayscale

        text = pytesseract.image_to_string(
            image,
            lang=language,
            config="--psm 1",  # Automatic page segmentation
        )
        text_parts.append(f"--- Page {i + 1} ---\n{text}")

    return "\n\n".join(text_parts)

def ocr_with_confidence(pdf_path: str) -> list[dict]:
    """OCR with word-level confidence scores."""
    images = convert_from_path(pdf_path, dpi=300)
    results = []

    for i, image in enumerate(images):
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT
        )

        page_words = []
        for j, word in enumerate(data["text"]):
            if word.strip():
                page_words.append({
                    "text": word,
                    "confidence": data["conf"][j],
                    "x": data["left"][j],
                    "y": data["top"][j],
                    "width": data["width"][j],
                    "height": data["height"][j],
                })

        results.append({
            "page": i + 1,
            "words": page_words,
        })

    return results
```

## Performance Optimization

### Processing Large Files

```python
from pypdf import PdfReader, PdfWriter

def process_large_pdf_in_chunks(input_path: str, output_dir: str, chunk_size: int = 50) -> list:
    """Process large PDFs in chunks to manage memory."""
    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    output_files = []

    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)
        writer = PdfWriter()

        for i in range(start, end):
            writer.add_page(reader.pages[i])

        output_path = f"{output_dir}/chunk_{start + 1}_{end}.pdf"
        with open(output_path, "wb") as f:
            writer.write(f)
        output_files.append(output_path)

        # Force garbage collection
        del writer

    return output_files
```

### Streaming Text Extraction

```python
import pdfplumber

def stream_text_extraction(pdf_path: str):
    """Generator for memory-efficient text extraction."""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            yield {
                "page": i + 1,
                "text": page.extract_text(),
            }
```

### Command-Line Performance

For fastest text extraction from large files:
```bash
# Fastest method - uses optimized C code
pdftotext -layout large_file.pdf output.txt

# For specific page range
pdftotext -f 1 -l 100 large_file.pdf output.txt
```

## Error Handling Patterns

### Robust PDF Processing

```python
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import logging

logger = logging.getLogger(__name__)

def safe_read_pdf(pdf_path: str) -> PdfReader | None:
    """Safely read a PDF with error handling."""
    try:
        reader = PdfReader(pdf_path)

        # Handle encryption
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # Try empty password
            except Exception:
                logger.warning(f"PDF is encrypted: {pdf_path}")
                return None

        return reader

    except PdfReadError as e:
        logger.error(f"Failed to read PDF: {e}")
        return None
    except FileNotFoundError:
        logger.error(f"PDF file not found: {pdf_path}")
        return None

def repair_and_read(pdf_path: str) -> PdfReader | None:
    """Attempt to repair corrupted PDF before reading."""
    import subprocess
    import tempfile

    try:
        # Try normal read first
        return PdfReader(pdf_path)
    except PdfReadError:
        # Attempt repair with qpdf
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            result = subprocess.run(
                ["qpdf", "--replace-input", pdf_path, tmp.name],
                capture_output=True,
            )
            if result.returncode == 0:
                return PdfReader(tmp.name)
        return None
```

### Fallback Strategies

```python
def extract_text_with_fallback(pdf_path: str) -> str:
    """Extract text with multiple fallback methods."""
    # Method 1: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            if text.strip():
                return text
    except Exception:
        pass

    # Method 2: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        if text.strip():
            return text
    except Exception:
        pass

    # Method 3: Command-line pdftotext
    try:
        import subprocess
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except Exception:
        pass

    # Method 4: OCR fallback
    try:
        import pytesseract
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path)
        text = "\n".join(pytesseract.image_to_string(img) for img in images)
        return text
    except Exception:
        pass

    raise ValueError(f"Could not extract text from: {pdf_path}")
```

## JavaScript/Node.js Reference

### pdf-lib for Node.js

```javascript
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import fs from 'fs';

async function createPdf(outputPath) {
    const pdfDoc = await PDFDocument.create();
    const page = pdfDoc.addPage([612, 792]); // Letter size

    const font = await pdfDoc.embedFont(StandardFonts.Helvetica);

    page.drawText('Hello, PDF!', {
        x: 50,
        y: 700,
        size: 24,
        font: font,
        color: rgb(0, 0, 0),
    });

    const pdfBytes = await pdfDoc.save();
    fs.writeFileSync(outputPath, pdfBytes);
}

async function modifyPdf(inputPath, outputPath) {
    const existingPdf = fs.readFileSync(inputPath);
    const pdfDoc = await PDFDocument.load(existingPdf);

    const pages = pdfDoc.getPages();
    const firstPage = pages[0];

    firstPage.drawText('Added text', {
        x: 50,
        y: 50,
        size: 12,
    });

    const pdfBytes = await pdfDoc.save();
    fs.writeFileSync(outputPath, pdfBytes);
}
```

### pdfjs-dist for Text Extraction

```javascript
import * as pdfjsLib from 'pdfjs-dist';

async function extractText(pdfPath) {
    const data = new Uint8Array(fs.readFileSync(pdfPath));
    const pdf = await pdfjsLib.getDocument(data).promise;

    let fullText = '';

    for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const content = await page.getTextContent();
        const pageText = content.items.map(item => item.str).join(' ');
        fullText += pageText + '\n';
    }

    return fullText;
}
```
