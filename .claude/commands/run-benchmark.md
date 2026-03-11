# Run Benchmark

Run a Taskforce agent or model evaluation benchmark via WSL 2.

## Arguments

$ARGUMENTS should specify: `<benchmark> [--model <model>]`

**Benchmarks available:**

| Benchmark | Type | Instances | Runtime |
|-----------|------|-----------|---------|
| `swe_bench_mini` | Agent (sandbox) | 20 | ~1-2h |
| `swe_bench_lite` | Agent (sandbox) | 300 | ~15-30h |
| `swe_bench_verified` | Agent (sandbox) | 500 | ~30-50h |
| `coding_spar` | Agent (host) | 8 | ~5min |
| `coding_react` | Agent (host) | 8 | ~1min |
| `coding_plan_and_execute` | Agent (host) | 8 | ~3min |
| `coding_full` | Agent (host) | 8×3 | ~10min |
| `arc` | Model baseline | 1172 | ~10min |
| `gpqa` | Model baseline | 792 | ~50min |
| `humaneval` | Model baseline | 164 | ~5min |

## Instructions

You are running a benchmark evaluation for the Taskforce agent framework.

### Step 1: Determine benchmark type

Parse $ARGUMENTS to identify:
- **benchmark name** (required)
- **model** (optional, default: `openai/azure/gpt-4.1` for agent benchmarks, `openai/azure/gpt-5-mini` for model baselines)

### Step 2: Choose execution environment

**SWE-bench benchmarks** (`swe_bench_*`) require WSL 2 + Docker:
1. Fix line endings: `wsl -d Ubuntu-20.04 -- sed -i 's/\r$//' /mnt/c/Users/rudi/source/pytaskforce/evals/wsl_run_swebench.sh`
2. Determine variant from benchmark name (`mini`, `lite`, or `verified`)
3. Run: `MSYS_NO_PATHCONV=1 wsl -d Ubuntu-20.04 -- bash /mnt/c/Users/rudi/source/pytaskforce/evals/wsl_run_swebench.sh <variant>`
4. This is long-running — use `run_in_background: true` for the Bash tool

**All other benchmarks** run directly on Windows:
1. Run: `PYTHONPATH=src;evals python evals/run_eval.py <benchmark_name> --model <model>`
2. For `coding_full`, run all three: `coding_spar coding_react coding_plan_and_execute`

### Step 3: Monitor and report

- For background tasks, inform the user that the benchmark is running and approximately how long it will take
- When complete, read the output and summarize results (accuracy, tokens, time)
- Update `evals/REPORT.md` with new results if they differ from existing entries

### Step 4: WSL dependency installation (only if needed)

If the WSL run fails with import errors, reinstall dependencies:
```bash
wsl -d Ubuntu-20.04 -- sed -i 's/\r$//' /mnt/c/Users/rudi/source/pytaskforce/evals/wsl_install.sh
MSYS_NO_PATHCONV=1 wsl -d Ubuntu-20.04 -- bash /mnt/c/Users/rudi/source/pytaskforce/evals/wsl_install.sh
```

### Key environment notes

- WSL distro: `Ubuntu-20.04` (WSL 2)
- WSL venv: `/home/rudi/taskforce-eval-venv/`
- Docker Desktop CLI in WSL: `/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker`
- Always use `MSYS_NO_PATHCONV=1` before `wsl` commands in Git Bash
- Always fix `\r` line endings before running scripts in WSL
- Log files go to `logs/` directory; view with `inspect view`
