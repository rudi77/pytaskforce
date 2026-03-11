#!/bin/bash
export PATH=/home/rudi/taskforce-eval-venv/bin:/usr/local/bin:/usr/bin:/bin:/home/rudi/.local/bin
export HOME=/home/rudi
alias pip=pip3

echo "=== Installing dependencies ==="

pip3 install "inspect-ai>=0.3.130" "python-dotenv>=1.0.0" 2>&1 | tail -5
echo "--- inspect-ai done ---"

pip3 install "inspect-evals[swe_bench]>=0.3.0" 2>&1 | tail -5
echo "--- inspect-evals done ---"

pip3 install "litellm>=1.7.7" "pydantic>=2.0" "pydantic-settings>=2.0" "pyyaml>=6.0" "structlog>=24.2.0" "aiofiles>=23.2.1" "aiohttp>=3.9" "typer>=0.9.0" "rich>=13.0.0" "prompt-toolkit>=3.0.0" "fastapi>=0.116.1" "uvicorn>=0.25" "mcp>=1.0.0" 2>&1 | tail -5
echo "--- taskforce deps done ---"

echo "=== All dependencies installed ==="
