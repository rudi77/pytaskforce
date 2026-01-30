---
name: invoice-extraction
description: Extract structured invoice data from PDF/image documents. Run the extract_invoice.py script with invoice path as input, returns JSON with all fields and §14 UStG compliance validation.
---

# Invoice Extraction Skill

Extracts structured invoice data from PDF or image documents using OCR. The extraction is deterministic and token-efficient.

## Usage

Run the script with the invoice file path:

```bash
python scripts/extract_invoice.py /path/to/invoice.pdf
```

With output file:

```bash
python scripts/extract_invoice.py /path/to/invoice.pdf --output result.json --pretty
```

## Input

Supported file formats:
- PDF files (`.pdf`)
- Images (`.png`, `.jpg`, `.jpeg`, `.tiff`)
- Pre-extracted JSON (`.json`)

## Output

The script outputs JSON to stdout:

```json
{
    "success": true,
    "invoice_data": {
        "invoice_id": "RE-2024-00123",
        "invoice_date": "2024-01-15",
        "service_date": "2024-01-10",
        "supplier_name": "Muster GmbH",
        "supplier_address": "Musterstraße 1, 12345 Musterstadt",
        "supplier_vat_id": "DE123456789",
        "supplier_country": "DE",
        "recipient_name": "Kunde AG",
        "recipient_address": "Kundenweg 5, 54321 Kundenstadt",
        "currency": "EUR",
        "line_items": [],
        "net_amount": 3900.00,
        "tax_rate": 0.19,
        "tax_amount": 741.00,
        "total_amount": 4641.00,
        "description": null
    },
    "missing_fields": ["Leistungsdatum", "Leistungsbeschreibung"],
    "compliant": false,
    "ocr_info": {
        "region_count": 45,
        "text_length": 1234
    }
}
```

## §14 UStG Compliance

The script validates these mandatory fields:

| Field | JSON Key | German Label |
|-------|----------|--------------|
| Invoice number | `invoice_id` | Rechnungsnummer |
| Invoice date | `invoice_date` | Rechnungsdatum |
| Service date | `service_date` | Leistungsdatum |
| Supplier name | `supplier_name` | Lieferant |
| Supplier address | `supplier_address` | Lieferantenadresse |
| VAT ID | `supplier_vat_id` | USt-IdNr |
| Recipient name | `recipient_name` | Leistungsempfänger |
| Recipient address | `recipient_address` | Empfängeradresse |
| Description | `description` | Leistungsbeschreibung |
| Net amount | `net_amount` | Nettobetrag |
| Tax rate | `tax_rate` | Steuersatz |
| Tax amount | `tax_amount` | Steuerbetrag |
| Total amount | `total_amount` | Bruttobetrag |

- `compliant: true` when all fields are present
- `missing_fields` lists missing fields in German

## Error Handling

On failure, returns:

```json
{
    "success": false,
    "error": "File not found: /path/to/missing.pdf"
}
```

Exit code is `1` on failure, `0` on success.

## Dependencies

Requires the `document-extraction-mcp` server to be available for OCR:

```
servers/document-extraction-mcp/src/document_extraction_mcp/tools/ocr.py
```

## Integration with Gatekeeper

The Gatekeeper agent executes this script:

```python
import subprocess
import json

result = subprocess.run(
    ["python", "scripts/extract_invoice.py", invoice_path],
    capture_output=True,
    text=True,
    cwd=skill_path
)
invoice_data = json.loads(result.stdout)
```
