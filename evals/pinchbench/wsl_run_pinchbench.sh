#!/bin/bash
# PinchBench evaluation runner for WSL 2 / Linux.
#
# Clones (or updates) the upstream pinchbench/skill repository, prepares
# the environment, and runs `scripts/benchmark.py` for the chosen suite
# and model. Mirrors evals/wsl_run_swebench.sh in style.
#
# Usage:
#   bash evals/pinchbench/wsl_run_pinchbench.sh                       # core suite, default model
#   bash evals/pinchbench/wsl_run_pinchbench.sh coding                # coding category only
#   bash evals/pinchbench/wsl_run_pinchbench.sh core openrouter/anthropic/claude-sonnet-4
#   bash evals/pinchbench/wsl_run_pinchbench.sh all   openai/azure/gpt-4.1
#
# Prerequisites: `uv` and the `openclaw` CLI must be on PATH, plus an
# API key for the chosen model provider (OPENROUTER_API_KEY etc.).

set -euo pipefail

# Resolve project root regardless of where the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL_DIR="$SCRIPT_DIR/skill"
RESULTS_DIR="$SCRIPT_DIR/results"

SUITE="${1:-core}"
MODEL="${2:-openrouter/anthropic/claude-sonnet-4}"

# Load .env (strip Windows \r from values; same parser as wsl_run_swebench.sh).
if [ -f "$PROJECT_DIR/.env" ]; then
    while IFS='=' read -r key value; do
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        key=$(echo "$key" | tr -d '\r' | xargs)
        value=$(echo "$value" | tr -d '\r' | xargs)
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "$key=$value" 2>/dev/null || true
    done < "$PROJECT_DIR/.env"
fi

# Sanity checks
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: \`uv\` is not on PATH. Install from https://docs.astral.sh/uv/." >&2
    exit 1
fi
if ! command -v openclaw >/dev/null 2>&1; then
    echo "WARNING: \`openclaw\` CLI is not on PATH. PinchBench drives every" >&2
    echo "         task through \`openclaw agent\`; expect immediate failures." >&2
fi

# Clone or update the upstream skill repo.
if [ ! -d "$SKILL_DIR" ]; then
    echo "Cloning pinchbench/skill into $SKILL_DIR ..."
    git clone --depth 1 https://github.com/pinchbench/skill.git "$SKILL_DIR"
else
    echo "Using existing pinchbench checkout at $SKILL_DIR (pass --update to refresh)."
    if [ "${3:-}" = "--update" ]; then
        git -C "$SKILL_DIR" fetch --depth 1 origin
        git -C "$SKILL_DIR" reset --hard origin/HEAD
    fi
fi

mkdir -p "$RESULTS_DIR"

echo ""
echo "=== Running PinchBench ==="
echo "  Suite:       $SUITE"
echo "  Model:       $MODEL"
echo "  Skill repo:  $SKILL_DIR"
echo "  Results dir: $RESULTS_DIR"
echo ""

cd "$SKILL_DIR"
uv run scripts/benchmark.py \
    --model "$MODEL" \
    --suite "$SUITE" \
    --output-dir "$RESULTS_DIR" \
    --no-upload \
    "${@:4}"
