#!/usr/bin/env bash
# write-audit.sh — Schreibt einen Eintrag ins Audit-Log
# Usage: bash scripts/write-audit.sh <db_path> <event_type> <entity_type> <entity_id> <actor> '<details_json>'
#
# Event Types:
#   invoice_created, invoice_validated, invoice_posted, invoice_rejected
#   journal_created, journal_posted, journal_reversed
#   vendor_created, vendor_matched
#   user_confirmed, user_corrected, user_rejected
#   extraction_completed, validation_completed
#   error_occurred
set -euo pipefail

DB_PATH="${1:?Usage: write-audit.sh <db_path> <event_type> <entity_type> <entity_id> <actor> '<details_json>'}"
EVENT_TYPE="${2:?Missing event_type}"
ENTITY_TYPE="${3:?Missing entity_type}"
ENTITY_ID="${4:?Missing entity_id}"
ACTOR="${5:-system}"
DETAILS="${6:-'{}'}"

# Escape single quotes in details
DETAILS_ESCAPED=$(echo "$DETAILS" | sed "s/'/''/g")

sqlite3 "$DB_PATH" "
    INSERT INTO audit_log (event_type, entity_type, entity_id, actor, details)
    VALUES ('$EVENT_TYPE', '$ENTITY_TYPE', $ENTITY_ID, '$ACTOR', '$DETAILS_ESCAPED');
"

AUDIT_ID=$(sqlite3 "$DB_PATH" "SELECT last_insert_rowid();")

echo "{\"audit_id\": $AUDIT_ID, \"event_type\": \"$EVENT_TYPE\", \"entity_type\": \"$ENTITY_TYPE\", \"entity_id\": $ENTITY_ID}"
