# PinchBench integration

[PinchBench](https://github.com/pinchbench/skill) evaluates LLM models as
OpenClaw coding agents on ~180 real-world tasks across 10 categories
(productivity, research, writing, coding, analysis, CSV / log / meeting
parsing, memory, skills, integrations).

## How this differs from the SWE-bench setup

SWE-bench plugs into Taskforce through `inspect-evals[swe_bench]` — the
benchmark framework owns task definitions and scoring while we provide a
custom solver (`taskforce_swebench_solver`) that runs the Taskforce agent
inside the SWE-bench Docker sandbox.

PinchBench has no Inspect AI adapter. Its runner shells out to the
`openclaw agent` CLI for every task and grades the resulting transcripts.
This integration therefore **does not** wire pinchbench through Inspect
AI; instead it clones the upstream `pinchbench/skill` repository and
forwards arguments to its `scripts/benchmark.py`, with the model and
suite selected by us. It evaluates the **model** (and OpenClaw's harness),
not the Taskforce agent framework directly.

If a Taskforce-as-agent evaluation is needed later, the natural next
step is to add an `openclaw` shim that translates pinchbench's subprocess
calls into Taskforce mission invocations and writes OpenClaw-compatible
transcripts. That is intentionally out of scope here.

## Prerequisites

- `uv` on PATH (the upstream runner uses `uv run`)
- `openclaw` CLI on PATH (pinchbench drives the agent via subprocess)
- API key for the chosen provider:
  - `OPENROUTER_API_KEY` for `openrouter/*` models (default)
  - `ANTHROPIC_API_KEY` for `anthropic/*` models
  - `OPENAI_API_KEY` for `openai/*` models
  - For Azure / custom OpenAI-compatible endpoints pass
    `-- --base-url <url> --api-key <key>`

## Usage

```bash
# ~25 representative core tasks (quick smoke test)
python evals/pinchbench/run_pinchbench.py --suite core

# Single category against a specific OpenRouter model
python evals/pinchbench/run_pinchbench.py \
    --model openrouter/anthropic/claude-sonnet-4 --suite coding

# Full benchmark (slow, ~180 tasks)
python evals/pinchbench/run_pinchbench.py --suite all

# Bash variant (analogous to evals/wsl_run_swebench.sh)
bash evals/pinchbench/wsl_run_pinchbench.sh core openrouter/anthropic/claude-sonnet-4
```

Forward additional flags through to upstream `scripts/benchmark.py`
after a `--` separator:

```bash
python evals/pinchbench/run_pinchbench.py --suite coding -- \
    --verbose --judge openrouter/openai/gpt-4o --no-judge-cache
```

## Outputs

- `evals/pinchbench/skill/` — upstream checkout (gitignored)
- `evals/pinchbench/results/<run_id>_<model>.json` — task scores, category
  rollups, efficiency metrics
- `evals/pinchbench/results/<run_id>_transcripts/` — per-task execution
  transcripts
- `evals/pinchbench/results/.judge_cache/` — cached LLM-judge results
  (gitignored)

## Suite reference

| Suite | What it runs |
| --- | --- |
| `core` | ~25 representative tasks across all categories (quick smoke test) |
| `all`  | Full benchmark (~180 tasks, slow) |
| `automated-only` | Tasks with deterministic graders (no LLM judge) |
| `productivity` / `research` / `writing` / `coding` / `analysis` | Single category |
| `csv_analysis` / `log_analysis` / `meeting_analysis` | Single category |
| `memory` / `skills` / `integrations` | Single category |
| `task_xxx,task_yyy` | Comma-separated list of specific task IDs |
