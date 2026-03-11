#!/bin/bash
set -e

# SWE-bench evaluation runner for WSL
PROJECT_DIR="/mnt/c/Users/rudi/source/pytaskforce"
VENV_DIR="$HOME/taskforce-eval-venv"
UV="$HOME/.local/bin/uv"

echo "=== SWE-bench WSL Runner ==="

# Ensure uv is available
if [ ! -f "$UV" ]; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Create venv in home dir (avoids /tmp issues)
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    "$UV" venv "$VENV_DIR" --python 3.11
fi

source "$VENV_DIR/bin/activate"

# Install in smaller batches to avoid memory spikes
echo "Installing core dependencies..."
"$UV" pip install --quiet "inspect-ai>=0.3.130" "python-dotenv>=1.0.0"

echo "Installing inspect-evals with swe_bench..."
"$UV" pip install --quiet "inspect-evals[swe_bench]>=0.3.0"

echo "Installing taskforce dependencies..."
"$UV" pip install --quiet \
    "litellm>=1.7.7" \
    "pydantic>=2.0" \
    "pydantic-settings>=2.0" \
    "pyyaml>=6.0" \
    "structlog>=24.2.0" \
    "aiofiles>=23.2.1" \
    "aiohttp>=3.9" \
    "typer>=0.9.0" \
    "rich>=13.0.0" \
    "prompt-toolkit>=3.0.0" \
    "fastapi>=0.116.1" \
    "uvicorn>=0.25" \
    "mcp>=1.0.0"

# Load .env
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "Loading .env..."
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Map Azure env vars for Inspect AI
export AZUREAI_OPENAI_API_KEY="${AZURE_API_KEY:-}"
export AZUREAI_OPENAI_BASE_URL="${AZURE_API_BASE:-}"
export AZUREAI_OPENAI_API_VERSION="${AZURE_API_VERSION:-}"
export PYTHONPATH="$PROJECT_DIR/src:$PROJECT_DIR/evals:$PYTHONPATH"

echo ""
echo "=== Running SWE-bench Verified Mini ==="
echo "Model: openai/azure/gpt-4.1"
echo ""

cd "$PROJECT_DIR"

python -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/evals')
sys.path.insert(0, '$PROJECT_DIR/src')

from inspect_ai import eval as inspect_eval
from evals.tasks.swe_bench import swe_bench_verified_mini

task = swe_bench_verified_mini()
results = inspect_eval(
    task,
    model='openai/azure/gpt-4.1',
    log_dir='$PROJECT_DIR/logs',
)

print()
print('=' * 60)
print('  SWE-bench Verified Mini Results')
print('=' * 60)
for r in results:
    if r.results:
        for metric_name, metric_val in r.results.metrics.items():
            print(f'  {metric_name}: {metric_val}')
    else:
        print('  No results (scoring may have failed)')
    print(f'  Status: {r.status}')
print('=' * 60)
"

echo ""
echo "=== Done ==="
