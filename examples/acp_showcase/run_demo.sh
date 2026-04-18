#!/usr/bin/env bash
# ACP Showcase runner.
#
# Starts the researcher + coder peers in the background, waits for their
# ACP ports to come up, then runs a mission through the orchestrator
# profile that delegates to both peers.
#
# Usage:
#   ./examples/acp_showcase/run_demo.sh
#   ./examples/acp_showcase/run_demo.sh "Custom mission text"

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
OUT_DIR="$SCRIPT_DIR/out"
PIDS=()

DEFAULT_MISSION='Research the three most-used Python HTTP client libraries in 2026 and write a minimal working example using the recommended one. Save the example to examples/acp_showcase/out/demo_client.py.'
MISSION="${1:-$DEFAULT_MISSION}"

mkdir -p "$LOG_DIR" "$OUT_DIR"
cd "$REPO_ROOT"

# --- helpers --------------------------------------------------------------

cleanup() {
  local exit_code=$?
  echo
  echo "[demo] Stopping background peers..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

wait_for_port() {
  local port="$1"
  local attempts=40
  while (( attempts > 0 )); do
    if (exec 3<>/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
      exec 3<&- 3>&- || true
      return 0
    fi
    sleep 0.5
    attempts=$((attempts - 1))
  done
  echo "[demo] Timed out waiting for port $port" >&2
  return 1
}

# --- sanity checks -------------------------------------------------------

if ! command -v uv >/dev/null 2>&1; then
  echo "[demo] 'uv' not found on PATH. Install uv first." >&2
  exit 1
fi

if ! uv run python -c "import acp_sdk" 2>/dev/null; then
  echo "[demo] acp-sdk not installed. Run: uv sync --extra acp" >&2
  exit 1
fi

# --- start peers in background -------------------------------------------

echo "[demo] Starting researcher peer on :8801 (logs: $LOG_DIR/researcher.log)"
uv run taskforce acp start --profile showcase_researcher \
  >"$LOG_DIR/researcher.log" 2>&1 &
PIDS+=($!)

echo "[demo] Starting coder peer on :8802 (logs: $LOG_DIR/coder.log)"
uv run taskforce acp start --profile showcase_coder \
  >"$LOG_DIR/coder.log" 2>&1 &
PIDS+=($!)

echo "[demo] Waiting for peers to become reachable..."
wait_for_port 8801
wait_for_port 8802
echo "[demo] Peers up."

# --- run the orchestrator mission ---------------------------------------

echo
echo "[demo] Running mission through orchestrator (profile: showcase_orchestrator)"
echo "[demo] Mission: $MISSION"
echo "=========================================================================="

uv run taskforce run mission --profile showcase_orchestrator "$MISSION"

echo "=========================================================================="
echo "[demo] Output artefacts (if the coder produced any):"
ls -l "$OUT_DIR" 2>/dev/null || true
echo
echo "[demo] Peer logs are kept in $LOG_DIR/ for inspection."
