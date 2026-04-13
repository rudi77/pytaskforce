#!/usr/bin/env bash
# resolve-period.sh — Findet die passende Geschäftsperiode für ein Datum
# Usage: bash scripts/resolve-period.sh <db_path> <date>
# Date format: YYYY-MM-DD
set -euo pipefail

DB_PATH="${1:?Usage: resolve-period.sh <db_path> <date>}"
DATE="${2:?Usage: resolve-period.sh <db_path> <date>}"

# Extrahiere Jahr und Monat aus dem Datum
YEAR=$(echo "$DATE" | cut -d'-' -f1)
MONTH=$(echo "$DATE" | cut -d'-' -f2 | sed 's/^0//')

RESULT=$(sqlite3 -json "$DB_PATH" "
    SELECT id, year, month, label, start_date, end_date, is_closed
    FROM fiscal_periods
    WHERE year = $YEAR AND month = $MONTH
    LIMIT 1;
")

if [ "$RESULT" != "[]" ] && [ -n "$RESULT" ]; then
    echo "$RESULT"
else
    # Periode existiert nicht → erstelle sie
    LABEL=$(date -d "$YEAR-$(printf '%02d' $MONTH)-01" '+%B %Y' 2>/dev/null || echo "Monat $MONTH $YEAR")
    START_DATE="$YEAR-$(printf '%02d' $MONTH)-01"

    # Letzter Tag des Monats berechnen
    if [ "$MONTH" -eq 12 ]; then
        NEXT_YEAR=$((YEAR + 1))
        NEXT_MONTH=1
    else
        NEXT_YEAR=$YEAR
        NEXT_MONTH=$((MONTH + 1))
    fi
    END_DATE=$(date -d "$NEXT_YEAR-$(printf '%02d' $NEXT_MONTH)-01 -1 day" '+%Y-%m-%d' 2>/dev/null || echo "$YEAR-$(printf '%02d' $MONTH)-28")

    sqlite3 "$DB_PATH" "
        INSERT INTO fiscal_periods (year, month, label, start_date, end_date)
        VALUES ($YEAR, $MONTH, '$LABEL', '$START_DATE', '$END_DATE');
    "

    sqlite3 -json "$DB_PATH" "
        SELECT id, year, month, label, start_date, end_date, is_closed
        FROM fiscal_periods
        WHERE year = $YEAR AND month = $MONTH
        LIMIT 1;
    "
fi
