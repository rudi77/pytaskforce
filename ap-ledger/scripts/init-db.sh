#!/usr/bin/env bash
# init-db.sh — Initialisiert die SQLite-Datenbank
# Usage: bash scripts/init-db.sh [db_path]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_PATH="${1:-$PROJECT_DIR/db/ap-ledger.db}"

if [ -f "$DB_PATH" ]; then
    echo "Datenbank existiert bereits: $DB_PATH"
    echo "Lösche mit 'rm $DB_PATH' und starte erneut, um neu zu initialisieren."
    exit 1
fi

echo "Erstelle Datenbank: $DB_PATH"
sqlite3 "$DB_PATH" < "$PROJECT_DIR/db/schema.sql"
echo "Schema erstellt."

sqlite3 "$DB_PATH" < "$PROJECT_DIR/db/seed-data.sql"
echo "Seed-Daten eingefügt."

# Verifizierung
VENDOR_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM vendors;")
CATEGORY_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM categories;")
TAX_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM tax_codes;")
PERIOD_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM fiscal_periods;")

echo ""
echo "Initialisierung abgeschlossen:"
echo "  Vendors:    $VENDOR_COUNT"
echo "  Kategorien: $CATEGORY_COUNT"
echo "  Steuersätze: $TAX_COUNT"
echo "  Perioden:   $PERIOD_COUNT"
echo ""
echo "Bereit für Beleg-Verarbeitung."
