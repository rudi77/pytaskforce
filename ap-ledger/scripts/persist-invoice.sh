#!/usr/bin/env bash
# persist-invoice.sh — Speichert einen Beleg und seine Positionen in der DB
# Usage: bash scripts/persist-invoice.sh <db_path> '<invoice_json>'
#
# JSON-Format:
# {
#   "external_ref": "R-2025-001",
#   "vendor_id": 1,
#   "vendor_name_raw": "Wella Austria",
#   "invoice_date": "2025-03-15",
#   "due_date": null,
#   "total_gross": 102.00,
#   "total_net": 85.00,
#   "total_tax": 17.00,
#   "type": "invoice",
#   "source_file": "/path/to/file.jpg",
#   "source_type": "photo",
#   "extraction_confidence": 0.92,
#   "fiscal_period_id": 3,
#   "notes": "",
#   "lines": [
#     {
#       "position": 1,
#       "description": "Koleston Perfect 6/0",
#       "quantity": 3,
#       "unit_price": 28.33,
#       "net_amount": 85.00,
#       "tax_code": "AT_20",
#       "tax_amount": 17.00,
#       "gross_amount": 102.00,
#       "category_code": "waren_farbe"
#     }
#   ]
# }
set -euo pipefail

DB_PATH="${1:?Usage: persist-invoice.sh <db_path> '<invoice_json>'}"
INVOICE_JSON="${2:?Usage: persist-invoice.sh <db_path> '<invoice_json>'}"

# Parse JSON-Felder mit sqlite3's json_extract (oder jq wenn verfügbar)
# Wir verwenden Python für zuverlässiges JSON-Parsing
INVOICE_ID=$(python3 -c "
import json, subprocess, sys

data = json.loads('''$INVOICE_JSON''')

# Invoice einfügen
vendor_id = data.get('vendor_id', 'NULL')
if vendor_id is None:
    vendor_id = 'NULL'

def sql_str(val):
    if val is None:
        return 'NULL'
    return \"'\" + str(val).replace(\"'\", \"''\") + \"'\"

def sql_num(val):
    if val is None:
        return 'NULL'
    return str(val)

sql_invoice = f'''
INSERT INTO invoices (
    external_ref, vendor_id, vendor_name_raw, invoice_date, due_date,
    total_gross, total_net, total_tax, type, status,
    source_file, source_type, extraction_confidence,
    fiscal_period_id, notes
) VALUES (
    {sql_str(data.get('external_ref'))},
    {sql_num(vendor_id)},
    {sql_str(data.get('vendor_name_raw'))},
    {sql_str(data.get('invoice_date'))},
    {sql_str(data.get('due_date'))},
    {sql_num(data.get('total_gross'))},
    {sql_num(data.get('total_net'))},
    {sql_num(data.get('total_tax'))},
    {sql_str(data.get('type', 'invoice'))},
    'validated',
    {sql_str(data.get('source_file'))},
    {sql_str(data.get('source_type'))},
    {sql_num(data.get('extraction_confidence'))},
    {sql_num(data.get('fiscal_period_id'))},
    {sql_str(data.get('notes'))}
);
'''

# Lines einfügen
sql_lines = ''
for line in data.get('lines', []):
    sql_lines += f'''
INSERT INTO invoice_lines (
    invoice_id, position, description, quantity, unit_price,
    net_amount, tax_code, tax_amount, gross_amount, category_code
) VALUES (
    last_insert_rowid(),
    {sql_num(line.get('position', 1))},
    {sql_str(line.get('description'))},
    {sql_num(line.get('quantity', 1))},
    {sql_num(line.get('unit_price'))},
    {sql_num(line.get('net_amount'))},
    {sql_str(line.get('tax_code'))},
    {sql_num(line.get('tax_amount'))},
    {sql_num(line.get('gross_amount'))},
    {sql_str(line.get('category_code'))}
);
'''

# Alles in einer Transaktion
full_sql = f'''
BEGIN TRANSACTION;
{sql_invoice}
{sql_lines}
COMMIT;
SELECT last_insert_rowid();
'''

result = subprocess.run(
    ['sqlite3', '$DB_PATH'],
    input=full_sql,
    capture_output=True, text=True
)

if result.returncode != 0:
    print(f'ERROR: {result.stderr}', file=sys.stderr)
    sys.exit(1)

# Die letzte Zeile der Ausgabe ist die Invoice-ID
invoice_id = result.stdout.strip().split('\\n')[-1]
print(invoice_id)
")

echo "{\"invoice_id\": $INVOICE_ID}"
