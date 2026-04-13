#!/usr/bin/env bash
# resolve-tax.sh — Löst einen Steuercode auf
# Usage: bash scripts/resolve-tax.sh <db_path> <tax_code>
set -euo pipefail

DB_PATH="${1:?Usage: resolve-tax.sh <db_path> <tax_code>}"
TAX_CODE="${2:?Usage: resolve-tax.sh <db_path> <tax_code>}"

RESULT=$(sqlite3 -json "$DB_PATH" "
    SELECT code, rate, label, description
    FROM tax_codes
    WHERE code = '$TAX_CODE'
      AND (valid_to IS NULL OR valid_to >= date('now'))
    LIMIT 1;
")

if [ "$RESULT" != "[]" ] && [ -n "$RESULT" ]; then
    echo "$RESULT"
else
    echo "[]"
    echo "WARNUNG: Steuercode '$TAX_CODE' nicht gefunden." >&2
    exit 1
fi
