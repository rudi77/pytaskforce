#!/usr/bin/env bash
# resolve-vendor.sh — Sucht einen Vendor in der DB anhand des Namens
# Usage: bash scripts/resolve-vendor.sh <db_path> <vendor_name>
set -euo pipefail

DB_PATH="${1:?Usage: resolve-vendor.sh <db_path> <vendor_name>}"
VENDOR_NAME="${2:?Usage: resolve-vendor.sh <db_path> <vendor_name>}"

# Normalisiere den Namen: Kleinbuchstaben, trim
NORMALIZED=$(echo "$VENDOR_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# 1. Exakte Suche auf normalized name
RESULT=$(sqlite3 -json "$DB_PATH" "
    SELECT id, name, name_normalized, default_category_code, default_tax_code, match_keywords
    FROM vendors
    WHERE name_normalized = '$NORMALIZED'
    LIMIT 1;
")

if [ "$RESULT" != "[]" ] && [ -n "$RESULT" ]; then
    echo "$RESULT"
    exit 0
fi

# 2. LIKE-Suche (enthält den Namen)
RESULT=$(sqlite3 -json "$DB_PATH" "
    SELECT id, name, name_normalized, default_category_code, default_tax_code, match_keywords
    FROM vendors
    WHERE name_normalized LIKE '%$NORMALIZED%'
       OR '$NORMALIZED' LIKE '%' || name_normalized || '%'
    LIMIT 3;
")

if [ "$RESULT" != "[]" ] && [ -n "$RESULT" ]; then
    echo "$RESULT"
    exit 0
fi

# 3. Keyword-Suche: Prüfe ob einer der match_keywords im Vendor-Namen vorkommt
RESULT=$(sqlite3 -json "$DB_PATH" "
    SELECT id, name, name_normalized, default_category_code, default_tax_code, match_keywords
    FROM vendors
    WHERE EXISTS (
        SELECT 1
        FROM (
            WITH RECURSIVE split(word, rest) AS (
                SELECT '', match_keywords || ','
                UNION ALL
                SELECT
                    TRIM(SUBSTR(rest, 1, INSTR(rest, ',') - 1)),
                    SUBSTR(rest, INSTR(rest, ',') + 1)
                FROM split
                WHERE rest != ''
            )
            SELECT word FROM split WHERE word != ''
        )
        WHERE '$NORMALIZED' LIKE '%' || LOWER(word) || '%'
    )
    LIMIT 3;
")

if [ "$RESULT" != "[]" ] && [ -n "$RESULT" ]; then
    echo "$RESULT"
    exit 0
fi

# Kein Treffer
echo "[]"
exit 0
