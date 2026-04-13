#!/usr/bin/env bash
# post-journal.sh — Bucht einen Journal Entry (Status: draft → posted)
# Usage: bash scripts/post-journal.sh <db_path> <journal_id>
set -euo pipefail

DB_PATH="${1:?Usage: post-journal.sh <db_path> <journal_id>}"
JOURNAL_ID="${2:?Usage: post-journal.sh <db_path> <journal_id>}"

# Prüfe ob der Eintrag existiert und im Status 'draft' ist
STATUS=$(sqlite3 "$DB_PATH" "SELECT status FROM journal_entries WHERE id = $JOURNAL_ID;")

if [ -z "$STATUS" ]; then
    echo "ERROR: Journal Entry $JOURNAL_ID nicht gefunden." >&2
    exit 1
fi

if [ "$STATUS" != "draft" ]; then
    echo "ERROR: Journal Entry $JOURNAL_ID ist im Status '$STATUS', erwartet 'draft'." >&2
    exit 1
fi

# Soll/Haben-Check
BALANCE_CHECK=$(sqlite3 "$DB_PATH" "
    SELECT
        ROUND(SUM(debit_amount), 2) as total_debit,
        ROUND(SUM(credit_amount), 2) as total_credit,
        ROUND(SUM(debit_amount) - SUM(credit_amount), 2) as diff
    FROM journal_lines
    WHERE journal_entry_id = $JOURNAL_ID;
")

DIFF=$(echo "$BALANCE_CHECK" | cut -d'|' -f3)
if [ "$DIFF" != "0.0" ] && [ "$DIFF" != "0" ]; then
    echo "ERROR: Soll/Haben ungleich (Differenz: $DIFF)" >&2
    exit 1
fi

# Status auf 'posted' setzen
sqlite3 "$DB_PATH" "
    UPDATE journal_entries
    SET status = 'posted',
        posted_at = datetime('now'),
        posted_by = 'claude'
    WHERE id = $JOURNAL_ID;

    UPDATE invoices
    SET status = 'posted',
        updated_at = datetime('now')
    WHERE id = (SELECT invoice_id FROM journal_entries WHERE id = $JOURNAL_ID);
"

# Ergebnis ausgeben
sqlite3 -json "$DB_PATH" "
    SELECT je.id, je.entry_date, je.description, je.status, je.posted_at,
           i.vendor_name_raw, i.total_gross
    FROM journal_entries je
    LEFT JOIN invoices i ON i.id = je.invoice_id
    WHERE je.id = $JOURNAL_ID;
"
