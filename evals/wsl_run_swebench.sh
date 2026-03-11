#!/bin/bash
# SWE-bench evaluation runner for WSL 2.
#
# Runs SWE-bench Lite (300 instances) or Verified Mini (20 instances)
# using the Taskforce coding agent with sandbox-aware tools.
#
# Usage:
#   wsl -d Ubuntu-20.04 -- bash evals/wsl_run_swebench.sh          # default: lite
#   wsl -d Ubuntu-20.04 -- bash evals/wsl_run_swebench.sh mini     # quick test
#   wsl -d Ubuntu-20.04 -- bash evals/wsl_run_swebench.sh verified # full verified

set -euo pipefail

export PATH=/mnt/wsl/docker-desktop/cli-tools/usr/bin:/home/rudi/taskforce-eval-venv/bin:/usr/local/bin:/usr/bin:/bin:/home/rudi/.local/bin
export HOME=/home/rudi

PROJECT_DIR="/mnt/c/Users/rudi/source/pytaskforce"
VARIANT="${1:-lite}"  # lite, mini, or verified

# Load .env (strip Windows \r from values)
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

# Map Azure env vars for Inspect AI
export AZUREAI_OPENAI_API_KEY="${AZURE_API_KEY:-}"
export AZUREAI_OPENAI_BASE_URL="${AZURE_API_BASE:-}"
export AZUREAI_OPENAI_API_VERSION="${AZURE_API_VERSION:-}"
export PYTHONPATH="$PROJECT_DIR/src:$PROJECT_DIR/evals:${PYTHONPATH:-}"

# Verify Docker is available
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker is not available. Make sure Docker Desktop is running with WSL 2 integration."
    exit 1
fi
echo "Docker: $(docker --version)"

# Select task function based on variant
case "$VARIANT" in
    mini)
        TASK_FUNC="swe_bench_verified_mini"
        DESCRIPTION="SWE-bench Verified Mini (20 instances)"
        ;;
    lite)
        TASK_FUNC="swe_bench_lite"
        DESCRIPTION="SWE-bench Lite (300 instances)"
        ;;
    verified)
        TASK_FUNC="swe_bench_verified"
        DESCRIPTION="SWE-bench Verified (~500 instances)"
        ;;
    *)
        echo "Unknown variant: $VARIANT. Use 'mini', 'lite', or 'verified'."
        exit 1
        ;;
esac

echo "=== Running $DESCRIPTION ==="
echo "Model: openai/azure/gpt-4.1"
echo "Azure Base URL: ${AZUREAI_OPENAI_BASE_URL:0:30}..."
echo "Solver: taskforce_swebench_solver (sandbox tools)"
echo ""

cd "$PROJECT_DIR"

python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/evals')
sys.path.insert(0, '$PROJECT_DIR/src')

from inspect_ai import eval as inspect_eval
from evals.tasks.swe_bench import $TASK_FUNC

task = ${TASK_FUNC}()
results = inspect_eval(
    task,
    model='openai/azure/gpt-4.1',
    log_dir='$PROJECT_DIR/logs',
)

print()
print('=' * 60)
print('  $DESCRIPTION - Results')
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
