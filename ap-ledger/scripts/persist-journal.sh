#!/usr/bin/env bash
# persist-journal.sh — Speichert einen Buchungssatz (Journal Entry) in der DB
# Usage: bash scripts/persist-journal.sh <db_path> '<journal_json>'
#
# JSON-Format:
# {
#   "journal_entry": {
#     "invoice_id": 42,
#     "entry_date": "2025-03-15",
#     "description": "Wella Austria - Haarfarben",
#     "fiscal_period_id": 3
#   },
#   "journal_lines": [
#     {
#       "line_number": 1,
#       "account_code": "5100",
#       "account_name": "Wareneinsatz Haarfarben",
#       "debit_amount": 85.00,
#       "credit_amount": 0,
#       "tax_code": "AT_20",
#       "description": "Wella Koleston Haarfarben"
#     }
#   ]
# }
set -euo pipefail

DB_PATH="${1:?Usage: persist-journal.sh <db_path> '<journal_json>'}"
JOURNAL_JSON="${2:?Usage: persist-journal.sh <db_path> '<journal_json>'}"

JOURNAL_ID=$(python3 -c "
import json, subprocess, sys

data = json.loads('''$JOURNAL_JSON''')
entry = data['journal_entry']
lines = data['journal_lines']

def sql_str(val):
    if val is None:
        return 'NULL'
    return \"'\" + str(val).replace(\"'\", \"''\") + \"'\"

def sql_num(val):
    if val is None:
        return 'NULL'
    return str(val)

# Soll/Haben-Prüfung
total_debit = sum(l.get('debit_amount', 0) for l in lines)
total_credit = sum(l.get('credit_amount', 0) for l in lines)
if abs(total_debit - total_credit) > 0.01:
    print(f'ERROR: Soll ({total_debit:.2f}) != Haben ({total_credit:.2f})', file=sys.stderr)
    sys.exit(1)

# Journal Entry
sql_entry = f'''
INSERT INTO journal_entries (
    invoice_id, entry_date, description, status, fiscal_period_id
) VALUES (
    {sql_num(entry.get('invoice_id'))},
    {sql_str(entry.get('entry_date'))},
    {sql_str(entry.get('description'))},
    'draft',
    {sql_num(entry.get('fiscal_period_id'))}
);
'''

# Journal Lines — verwende eine Variable für die journal_entry_id
sql_lines = ''
for i, line in enumerate(lines):
    if i == 0:
        # Erste Zeile: verwende last_insert_rowid()
        journal_ref = 'last_insert_rowid()'
    else:
        # Folgende Zeilen: verwende die gleiche ID
        journal_ref = '(SELECT MAX(id) FROM journal_entries)'

    sql_lines += f'''
INSERT INTO journal_lines (
    journal_entry_id, line_number, account_code, account_name,
    debit_amount, credit_amount, tax_code, description
) VALUES (
    {journal_ref},
    {sql_num(line.get('line_number', i + 1))},
    {sql_str(line.get('account_code'))},
    {sql_str(line.get('account_name'))},
    {sql_num(line.get('debit_amount', 0))},
    {sql_num(line.get('credit_amount', 0))},
    {sql_str(line.get('tax_code'))},
    {sql_str(line.get('description'))}
);
'''

full_sql = f'''
BEGIN TRANSACTION;
{sql_entry}
{sql_lines}
COMMIT;
SELECT MAX(id) FROM journal_entries;
'''

result = subprocess.run(
    ['sqlite3', '$DB_PATH'],
    input=full_sql,
    capture_output=True, text=True
)

if result.returncode != 0:
    print(f'ERROR: {result.stderr}', file=sys.stderr)
    sys.exit(1)

journal_id = result.stdout.strip().split('\\n')[-1]
print(journal_id)
")

echo "{\"journal_id\": $JOURNAL_ID}"
