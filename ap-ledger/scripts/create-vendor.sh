#!/usr/bin/env bash
# create-vendor.sh — Erstellt einen neuen Vendor in der DB
# Usage: bash scripts/create-vendor.sh <db_path> <name> [category_code] [tax_code] [keywords]
set -euo pipefail

DB_PATH="${1:?Usage: create-vendor.sh <db_path> <name> [category_code] [tax_code] [keywords]}"
NAME="${2:?Usage: create-vendor.sh <db_path> <name> [category_code] [tax_code] [keywords]}"
CATEGORY_CODE="${3:-}"
TAX_CODE="${4:-AT_20}"
KEYWORDS="${5:-}"

# Normalisiere den Namen
NORMALIZED=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# Escape single quotes
NAME_ESCAPED=$(echo "$NAME" | sed "s/'/''/g")
NORMALIZED_ESCAPED=$(echo "$NORMALIZED" | sed "s/'/''/g")
KEYWORDS_ESCAPED=$(echo "$KEYWORDS" | sed "s/'/''/g")

# Prüfe ob Vendor schon existiert
EXISTING=$(sqlite3 "$DB_PATH" "SELECT id FROM vendors WHERE name_normalized = '$NORMALIZED_ESCAPED' LIMIT 1;")
if [ -n "$EXISTING" ]; then
    echo "{\"vendor_id\": $EXISTING, \"status\": \"already_exists\"}"
    exit 0
fi

# Category-Code als NULL oder String
if [ -z "$CATEGORY_CODE" ]; then
    CAT_SQL="NULL"
else
    CAT_SQL="'$CATEGORY_CODE'"
fi

# Keywords als NULL oder String
if [ -z "$KEYWORDS" ]; then
    KW_SQL="NULL"
else
    KW_SQL="'$KEYWORDS_ESCAPED'"
fi

sqlite3 "$DB_PATH" "
    INSERT INTO vendors (name, name_normalized, default_category_code, default_tax_code, match_keywords)
    VALUES ('$NAME_ESCAPED', '$NORMALIZED_ESCAPED', $CAT_SQL, '$TAX_CODE', $KW_SQL);
"

VENDOR_ID=$(sqlite3 "$DB_PATH" "SELECT last_insert_rowid();")

echo "{\"vendor_id\": $VENDOR_ID, \"status\": \"created\", \"name\": \"$NAME\"}"
