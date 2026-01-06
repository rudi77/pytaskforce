"""
Invoice extraction prompt for DACH region invoices.

This prompt instructs the LLM to extract structured data from invoice
markdown content, supporting German, Austrian, and Swiss formats.
"""

INVOICE_EXTRACTION_PROMPT = """
# Invoice Data Extraction Task

You are an expert at extracting structured data from invoice documents.
Extract all invoice-relevant fields from the following markdown content.

## Input Document
```markdown
{markdown_content}
```

## Expected Currency
{expected_currency}

## DACH Region VAT ID Formats

Recognize and validate these formats:
- **German (DE)**: USt-IdNr. DE123456789 (DE + 9 digits) or Steuernummer XX/XXX/XXXXX
- **Austrian (AT)**: UID ATU12345678 (ATU + 8 chars)
- **Swiss (CH)**: CHE-123.456.789 MWST (or TVA/IVA for French/Italian regions)

## Required Output Schema

Return ONLY a JSON object with the following structure:

```json
{{
  "supplier_name": "Full legal name of supplier",
  "supplier_address": "Complete supplier address (street, postal code, city, country)",
  "supplier_vat_id": "VAT ID or tax number (preserve original format)",
  "supplier_country": "ISO 2-letter country code (DE/AT/CH/etc.)",

  "recipient_name": "Full legal name of invoice recipient",
  "recipient_address": "Complete recipient address",
  "recipient_vat_id": "Recipient VAT ID if present (for B2B)",

  "invoice_number": "Invoice/document number (Rechnungsnummer)",
  "invoice_date": "Invoice date in ISO format YYYY-MM-DD",
  "due_date": "Payment due date in ISO format YYYY-MM-DD (null if not specified)",
  "delivery_date": "Delivery/service date in ISO format YYYY-MM-DD (null if not specified)",

  "line_items": [
    {{
      "position": 1,
      "description": "Item description",
      "quantity": 1.0,
      "unit": "Stk/Stunde/pcs/etc.",
      "unit_price": 100.00,
      "net_amount": 100.00,
      "vat_rate": 0.19,
      "vat_amount": 19.00
    }}
  ],

  "total_net": 100.00,
  "total_vat": 19.00,
  "total_gross": 119.00,

  "vat_breakdown": [
    {{
      "rate": 0.19,
      "rate_percent": 19,
      "net_amount": 100.00,
      "vat_amount": 19.00,
      "description": "Regelsteuersatz / Standard rate"
    }}
  ],

  "payment_info": {{
    "iban": "IBAN if present",
    "bic": "BIC/SWIFT if present",
    "bank_name": "Bank name if present",
    "payment_terms": "Payment terms text (e.g., '14 Tage netto')",
    "payment_reference": "Payment reference / Verwendungszweck"
  }},

  "additional_info": {{
    "reverse_charge": false,
    "reverse_charge_note": "Reverse charge text if applicable",
    "tax_exemption": null,
    "tax_exemption_reason": null,
    "order_number": "PO/Bestellnummer if present",
    "customer_number": "Kundennummer if present",
    "internal_note": "Any other relevant notes"
  }},

  "confidence_score": 0.95,
  "extraction_warnings": ["List of any extraction uncertainties"]
}}
```

## Extraction Rules

1. **Dates**: Convert all dates to ISO format (YYYY-MM-DD).
   - German format: DD.MM.YYYY (e.g., 15.03.2024 -> 2024-03-15)
   - Austrian/Swiss formats may vary

2. **Numbers**:
   - Use decimal point (not comma) for decimal values
   - Convert German/Austrian number format (1.234,56) to standard (1234.56)
   - Convert Swiss number format (1'234.56) to standard (1234.56)
   - VAT rates as decimal (0.19 for 19%, 0.07 for 7%, 0.081 for 8.1%)

3. **VAT Rates by Country**:
   - Germany (DE): 19% standard, 7% reduced
   - Austria (AT): 20% standard, 10% reduced, 13% special
   - Switzerland (CH): 8.1% standard (since 2024), 2.6% reduced, 3.8% accommodation

4. **Missing Fields**: Use null for fields that cannot be extracted. Add explanation to extraction_warnings.

5. **Line Items**: If no explicit line items table, create entries from invoice totals or descriptions.

6. **Reverse Charge Detection**:
   - German: "Steuerschuldnerschaft des Leistungsempfängers", "Reverse Charge"
   - Austrian: "Übergang der Steuerschuld"
   - Swiss: "Bezugsteuer"
   - Set reverse_charge: true and capture note text

7. **Confidence Score**:
   - 1.0: All mandatory fields extracted with high certainty
   - 0.8-0.9: Most fields extracted, minor uncertainties
   - 0.5-0.7: Key fields missing or unclear
   - <0.5: Significant extraction issues

## Important Notes

- Output ONLY the JSON object, no additional text or explanation
- Preserve original VAT ID format exactly as written in document
- For Swiss invoices, note MWST/TVA/IVA designation based on language region
- If invoice appears to be from outside DACH region, still extract but add warning
- Handle multi-page invoices by aggregating all line items
- Be careful with similar field names (e.g., Rechnungsnummer vs. Bestellnummer)
"""
