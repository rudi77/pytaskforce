---
name: invoice-extraction
description: Extract structured invoice data from PDF/image documents using OCR and layout detection. Returns JSON with all invoice fields including supplier, recipient, line items, and totals. Performs §14 UStG compliance validation for German invoices.
---

# Invoice Extraction Skill

This skill extracts structured invoice data from PDF or image documents using the document-extraction-mcp server tools. The output is a standardized JSON object containing all invoice fields required for accounts payable processing.

## MCP Server Requirement

This skill requires the **document-extraction-mcp** server to be configured:

```yaml
mcp_servers:
  - type: stdio
    command: uv
    args:
      - "--directory"
      - "servers/document-extraction-mcp"
      - "run"
      - "python"
      - "-m"
      - "document_extraction_mcp.server"
    env:
      OPENAI_API_KEY: "${OPENAI_API_KEY}"
    description: "Document extraction tools (OCR, Layout, VLM Analysis)"
```

## Available MCP Tools

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `ocr_extract` | Extract text with bounding boxes | `image_path` | Regions with text, bbox, confidence |
| `layout_detect` | Detect document regions | `image_path` | Region types (table, text, figure) with bbox |
| `reading_order` | Sort regions into reading sequence | `regions`, `image_path` | Ordered region indices |
| `crop_region` | Crop specific region | `image_path`, `bbox` | Base64 PNG image |
| `analyze_table` | Extract table structure via VLM | `image_path` or `image_base64` | Structured table data |

## Invoice Extraction Workflow

### Step 1: Run OCR on Invoice Document

```python
# Call ocr_extract tool
ocr_result = ocr_extract(image_path="/path/to/invoice.pdf")

# Returns:
{
    "success": true,
    "region_count": 45,
    "image_path": "/path/to/invoice.pdf",
    "image_width": 2480,
    "image_height": 3508,
    "regions": [
        {
            "index": 0,
            "text": "RECHNUNG",
            "confidence": 0.98,
            "bbox": [100, 50, 300, 90],
            "polygon": [[100, 50], [300, 50], [300, 90], [100, 90]]
        },
        ...
    ],
    "visualization_path": "/path/to/.artifacts/invoice_ocr.png"
}
```

### Step 2: Detect Layout (Optional but Recommended)

For complex invoices with tables, run layout detection:

```python
# Call layout_detect tool
layout_result = layout_detect(image_path="/path/to/invoice.pdf")

# Returns:
{
    "success": true,
    "regions": [
        {"type": "title", "bbox": [100, 50, 300, 90], "confidence": 0.95},
        {"type": "table", "bbox": [50, 400, 800, 700], "confidence": 0.92},
        {"type": "text", "bbox": [50, 150, 400, 350], "confidence": 0.89}
    ]
}
```

### Step 3: Extract Table Data (For Line Items)

If a table region is detected, analyze it with VLM:

```python
# Call analyze_table tool on the table region
table_result = analyze_table(image_path="/path/to/invoice.pdf")

# Returns structured table data:
{
    "success": true,
    "headers": ["Pos", "Beschreibung", "Menge", "Einzelpreis", "Gesamt"],
    "rows": [
        ["1", "Beratungsleistung", "10 Std", "150,00 EUR", "1.500,00 EUR"],
        ["2", "Softwareentwicklung", "20 Std", "120,00 EUR", "2.400,00 EUR"]
    ]
}
```

### Step 4: Parse OCR Text into Invoice Fields

Extract key fields from OCR text using pattern matching:

**German Invoice Patterns:**
- Rechnungsnummer: `Rechnungsnummer|Rechnungsnr\.?|Rechnung\s*[:#]?\s*([A-Z0-9-]+)`
- Rechnungsdatum: `Rechnungsdatum\s*[:#]?\s*(\d{2}[./]\d{2}[./]\d{4})`
- Leistungsdatum: `Leistungsdatum|Lieferdatum\s*[:#]?\s*(\d{2}[./]\d{2}[./]\d{4})`
- USt-IdNr: `USt-IdNr\.?|UID\s*[:#]?\s*(DE\d{9}|ATU\d{8})`
- Nettobetrag: `Netto\s*[:#]?\s*([0-9.,]+)`
- MwSt: `MwSt|USt\s*(\d{1,2})\s*%`
- Bruttobetrag: `Gesamt|Brutto|Total\s*[:#]?\s*([0-9.,]+)`

**English Invoice Patterns:**
- Invoice Number: `Invoice\s*(?:No\.?|Number|#)\s*[:#]?\s*([A-Z0-9-]+)`
- Invoice Date: `Invoice Date\s*[:#]?\s*(\d{2}[/-]\d{2}[/-]\d{4})`
- VAT Number: `VAT\s*(?:No\.?|Number|ID)\s*[:#]?\s*([A-Z0-9]+)`
- Net Amount: `(?:Sub)?Total|Net\s*[:#]?\s*([0-9.,]+)`
- VAT Amount: `VAT|Tax\s*[:#]?\s*([0-9.,]+)`
- Gross Amount: `Total\s*(?:Due|Amount)?\s*[:#]?\s*([0-9.,]+)`

## Output JSON Schema

The extracted invoice data follows this structure:

```json
{
    "invoice_id": "RE-2024-00123",
    "invoice_date": "2024-01-15",
    "service_date": "2024-01-10",
    "supplier": {
        "name": "Muster GmbH",
        "address": "Musterstraße 1, 12345 Musterstadt",
        "vat_id": "DE123456789",
        "country": "DE"
    },
    "recipient": {
        "name": "Kunde AG",
        "address": "Kundenweg 5, 54321 Kundenstadt"
    },
    "currency": "EUR",
    "line_items": [
        {
            "position": 1,
            "description": "Beratungsleistung",
            "quantity": 10,
            "unit": "Std",
            "unit_price": 150.00,
            "total": 1500.00
        }
    ],
    "totals": {
        "net_amount": 3900.00,
        "tax_rate": 0.19,
        "tax_amount": 741.00,
        "total_amount": 4641.00
    },
    "description": "Dienstleistungen Januar 2024",
    "payment_terms": "Zahlbar innerhalb von 14 Tagen",
    "bank_details": {
        "iban": "DE89370400440532013000",
        "bic": "COBADEFFXXX",
        "bank_name": "Commerzbank"
    }
}
```

## §14 UStG Compliance Check

German invoices must contain these mandatory fields per §14 UStG:

| Field | German Label | JSON Key |
|-------|--------------|----------|
| Full name and address of supplier | Vollständiger Name und Anschrift des leistenden Unternehmers | `supplier.name`, `supplier.address` |
| Full name and address of recipient | Vollständiger Name und Anschrift des Leistungsempfängers | `recipient.name`, `recipient.address` |
| Tax ID or VAT ID | Steuernummer oder USt-IdNr | `supplier.vat_id` |
| Invoice number | Fortlaufende Rechnungsnummer | `invoice_id` |
| Invoice date | Ausstellungsdatum | `invoice_date` |
| Service/delivery date | Zeitpunkt der Lieferung/Leistung | `service_date` |
| Quantity and description | Menge und Art der Leistung | `line_items[].description`, `line_items[].quantity` |
| Net amount | Entgelt (netto) | `totals.net_amount` |
| Tax rate | Steuersatz | `totals.tax_rate` |
| Tax amount | Steuerbetrag | `totals.tax_amount` |

### Compliance Validation

```python
def validate_compliance(invoice_data: dict) -> dict:
    """Check §14 UStG mandatory fields."""
    required_fields = {
        "invoice_id": "Rechnungsnummer",
        "invoice_date": "Rechnungsdatum",
        "supplier_name": "Lieferant",
        "supplier_address": "Lieferantenadresse",
        "supplier_vat_id": "USt-IdNr",
        "recipient_name": "Leistungsempfänger",
        "recipient_address": "Empfängeradresse",
        "service_date": "Leistungsdatum",
        "description": "Leistungsbeschreibung",
        "net_amount": "Nettobetrag",
        "tax_rate": "Steuersatz",
        "tax_amount": "Steuerbetrag",
        "total_amount": "Bruttobetrag",
    }

    missing = []
    for key, label in required_fields.items():
        value = get_nested_value(invoice_data, key)
        if not value:
            missing.append(label)

    return {
        "compliant": len(missing) == 0,
        "missing_fields": missing
    }
```

## Complete Extraction Example

```python
async def extract_invoice(invoice_path: str) -> dict:
    """Extract invoice data from PDF/image file."""

    # Step 1: OCR extraction
    ocr_result = await ocr_extract(image_path=invoice_path)
    if not ocr_result.get("success"):
        return {"error": ocr_result.get("error", "OCR failed")}

    regions = ocr_result.get("regions", [])
    text = " ".join(r["text"] for r in regions)

    # Step 2: Layout detection for tables
    layout_result = await layout_detect(image_path=invoice_path)
    table_regions = [
        r for r in layout_result.get("regions", [])
        if r.get("type") == "table"
    ]

    # Step 3: Extract line items from tables
    line_items = []
    for table_region in table_regions:
        table_data = await analyze_table(image_path=invoice_path)
        if table_data.get("success"):
            line_items.extend(parse_table_to_line_items(table_data))

    # Step 4: Parse text fields
    invoice_data = parse_invoice_fields(text)
    invoice_data["line_items"] = line_items

    # Step 5: Compliance check
    compliance = validate_compliance(invoice_data)

    return {
        "success": True,
        "invoice_data": invoice_data,
        "missing_fields": compliance["missing_fields"],
        "compliant": compliance["compliant"]
    }
```

## Integration with Gatekeeper Agent

The Gatekeeper agent uses this skill to extract invoice data:

1. Receives invoice file path or OCR results
2. Calls MCP tools for OCR and layout detection
3. Parses extracted text into structured fields
4. Validates §14 UStG compliance
5. Returns structured invoice JSON with compliance status

### Gatekeeper Tool Configuration

```yaml
tool_allowlist:
  - gatekeeper_extract_invoice
  - ocr_extract
  - layout_detect
  - analyze_table
  - file_read
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| "File not found" | Invalid path | Verify file exists |
| "OCR extraction failed" | Corrupted/unsupported format | Convert to PNG first |
| "PaddleOCR not installed" | Missing dependency | Run `pip install paddleocr paddlepaddle` |
| Low confidence scores | Poor image quality | Increase DPI, improve contrast |

## Tips for Better Extraction

1. **Use high-resolution images** - 300 DPI minimum for best OCR accuracy
2. **Ensure good contrast** - Black text on white background works best
3. **Straighten skewed documents** - Pre-process rotated scans
4. **Handle multi-page PDFs** - Process each page separately
5. **Validate extracted amounts** - Cross-check net + tax = gross
