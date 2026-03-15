# AutoOptim

**LLM-driven iterative optimization framework.**

AutoOptim runs an automated experiment loop that uses an LLM to propose single-variable experiments, applies mutations to your codebase, evaluates results, and keeps improvements. It works with any git-managed project.

## How It Works

```
┌─────────────────────────────────────────┐
│  1. PROPOSE (LLM generates experiment)  │
│     "Increase max_steps to 50..."       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  2. MUTATE (Apply file changes)         │
│     Modify config/code/prompts          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  3. EVALUATE (Run your eval suite)      │
│     Benchmark, test, measure metrics    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  4. DECIDE (Keep or discard)            │
│     composite >= baseline? → KEEP       │
└──────────────┬──────────────────────────┘
               │
               ▼ (repeat)
```

## Quick Start

```bash
# Install
pip install autooptim

# Create a config file (see examples/)
# Run optimization
autooptim run --config my_optimization.yaml
```

## Configuration

Everything is defined in a YAML config file:

```yaml
name: "my-optimization"
project_root: "."

categories:
  config:
    weight: 0.5
    mutator:
      type: yaml
      allowed_paths: ["config/"]
    context_files: ["config/settings.yaml"]

  code:
    weight: 0.5
    mutator:
      type: code
      allowed_paths: ["src/"]
      blocked_paths: ["tests/"]
      preflight: ["pytest tests/ -x -q"]
    context_files: ["src/core.py"]

evaluator:
  type: command
  command: "python eval.py {task_name}"
  quick_task: "quick"
  full_task: "full"

metric:
  scores:
    - {name: accuracy, range: [0, 1]}
    - {name: latency, type: lower_is_better}
  composite:
    quality:
      weight: 0.8
      components: {accuracy: 1.0}
    efficiency:
      weight: 0.2
      type: ratio_to_baseline
      components: [latency]

proposer:
  model: "claude-sonnet-4-20250514"

runner:
  max_iterations: 30
  max_cost_usd: 20.0
  tolerance: 0.02
```

## Extension Points

AutoOptim is built on 6 protocols you can implement:

| Protocol | Purpose |
|----------|---------|
| `MutatorProtocol` | How files are modified |
| `EvaluatorProtocol` | How results are measured |
| `MetricProtocol` | How scores become a single number |
| `ProposerProtocol` | How experiments are generated |
| `ScoreParserProtocol` | How eval output becomes scores |
| `PreflightProtocol` | How mutations are validated |

## Built-in Mutators

- **`yaml`** — YAML config files with safe-key whitelists
- **`code`** — Python files with syntax checking and preflight commands
- **`text`** — Text/prompt files with full content replacement

## Built-in Evaluators

- **`command`** — Run a shell command, parse JSON output
- **`script`** — Run inline Python that prints JSON scores

## Examples

See `examples/` for complete configurations:

- `taskforce_agent/` — AI agent optimization with Inspect AI
- `code_simplification/` — Reduce complexity while keeping tests passing

## CLI

```bash
autooptim run --config config.yaml              # basic run
autooptim run --config config.yaml --resume     # resume from last log
autooptim run --config config.yaml --max-iterations 10
autooptim run --config config.yaml --eval-mode full
```
