#!/usr/bin/env bash
# Start a provisioned BluBot customer instance (POSIX / Linux).
#
# Loads the customer's .env, switches to the customer directory, and
# launches `taskforce chat --telegram-polling` against the customer's
# profile YAML. Stays in the foreground.
#
# Usage:
#   ./start_customer.sh <slug>
#
# Env overrides:
#   BLUBOT_ROOT  (default: /srv/blubot)
#   REPO_PATH    (default: derived from this script's location)

set -euo pipefail

SLUG="${1:?usage: $0 <slug>}"
BLUBOT_ROOT="${BLUBOT_ROOT:-/srv/blubot}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_PATH="${REPO_PATH:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

CUSTOMER_DIR="$BLUBOT_ROOT/customers/$SLUG"
ENV_FILE="$CUSTOMER_DIR/.env"
PROFILE_FILE="$CUSTOMER_DIR/ap_ledger_agent.yaml"
VENV_ACTIVATE="$REPO_PATH/.venv/bin/activate"

if [[ ! -d "$CUSTOMER_DIR" ]]; then
    echo "❌ Customer directory not found: $CUSTOMER_DIR" >&2
    echo "   Provision first: python $SCRIPT_DIR/provision_customer.py --slug $SLUG --name '...'" >&2
    exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env file not found: $ENV_FILE" >&2
    exit 1
fi
if [[ ! -f "$PROFILE_FILE" ]]; then
    echo "❌ Profile YAML not found: $PROFILE_FILE" >&2
    exit 1
fi

# Load .env (export each non-comment KEY=VALUE line)
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Activate venv if present
if [[ -f "$VENV_ACTIVATE" ]]; then
    # shellcheck disable=SC1090
    . "$VENV_ACTIVATE"
else
    echo "⚠ venv activate script not found at $VENV_ACTIVATE — make sure 'taskforce' is on PATH." >&2
fi

echo "▶ Starting BluBot for $SLUG"
echo "  Customer dir: $CUSTOMER_DIR"
echo "  Profile:      $PROFILE_FILE"
echo "  Press Ctrl+C for graceful shutdown, Ctrl+\\ for force exit (SIGQUIT)."
echo ""

cd "$CUSTOMER_DIR"
exec taskforce chat --telegram-polling --profile "$PROFILE_FILE"
