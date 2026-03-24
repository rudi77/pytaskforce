---
name: evolve
type: prompt
description: >
  Evolutionary agent optimization with curriculum learning. You act as Teacher,
  Proposer, and Judge: generate missions of increasing difficulty, test 3 mutation
  variants in parallel git worktrees, merge the winners. Use /evolve to start.
  Triggers for: "optimize the butler", "make the agent faster", "reduce token usage",
  "fix the failing mission", "run optimization cycles", "improve agent performance",
  or any request to iteratively improve agent prompts/configs/code.
slash-name: evolve
---

# Evolutionary Agent Optimization

Focused, measurable, statistically rigorous optimization of Taskforce agents.

## Core Principles

1. **One objective per session** — optimize ONE metric deeply, not many shallowly
2. **3 runs per variant** — median comparison eliminates LLM noise
3. **Sub-agents for evals** — keep main context clean (JSON results only, no logs)
4. **Automated cycles** — run N cycles without manual intervention

## Arguments

Parse `$ARGUMENTS` for:
- `--objective <name>` — REQUIRED. One of: `token_efficiency`, `step_reduction`, `memory_recall`, `answer_quality`, `wall_time`
- `--cycles <N>` — optional, default 3. Number of optimization cycles.
- No arguments → show objectives table and ask user to pick one.

## Objectives

| Objective | Eval Mode | Primary Metric (direction) | Secondary | Mutation Focus |
|-----------|-----------|---------------------------|-----------|----------------|
| `token_efficiency` | `quick` | `avg_input_tokens` (↓ lower) | `avg_steps` | Context policy, prompt length, tool result handling, message compression |
| `step_reduction` | `daily` | `avg_steps` (↓ lower) | `avg_input_tokens` | Planning strategy, delegation patterns, tool selection |
| `memory_recall` | `memory` | `memory_recall` (↑ higher) | `avg_steps` | Memory save/search prompts, consolidation, recall patterns |
| `answer_quality` | `daily` | Teacher quality judgment | `task_completion` | Output formatting, delegation specificity, value extraction |
| `wall_time` | `quick` | `avg_wall_seconds` (↓ lower) | `avg_input_tokens` | Parallelization, caching, LLM routing, tool batching |

## Branch Rule

NEVER work on `main`. If on main, create `experiments/evolve-session-N` first.

## Cycle Workflow

Each cycle follows 7 steps. Run `--cycles` cycles automatically.

### Step 1: BASELINE (3 runs via sub-agents)

Run the eval 3 times in the MAIN repo using 3 **parallel sub-agents**.
Each sub-agent gets this prompt:

```
Run this eval and return ONLY the JSON result line.

Command: cd <REPO_DIR> && uv run python tests/benchmarks/autooptim/eval_butler.py <MODE> 2>/dev/null

The command outputs one JSON line to stdout. Find it and return ONLY that JSON object.
Do NOT summarize or interpret. Return the raw JSON string only.
```

Launch all 3 sub-agents in parallel using the Agent tool. Compute the **median** of
the primary metric from the 3 results. This is the baseline to beat.

Present baseline as:
```
Baseline (median of 3 runs):
  primary_metric: <value>
  secondary_metric: <value>
  task_completion: <value>
```

### Step 2: DIAGNOSE + TEACHER

Analyze the baseline results to find the weakest area for this objective:
- `token_efficiency`: which mission uses the most tokens?
- `step_reduction`: which mission uses the most steps?
- `memory_recall`: which sequence fails?
- `answer_quality`: read traces, which answer is worst?
- `wall_time`: which mission is slowest?

Design a **Teacher mission** (or select eval mode missions) that targets this weakness.

### Step 3: PROPOSER — Design 3 Mutations

Design exactly 3 mutation variants. Each changes **ONE variable** to isolate effects.

**Mutation targets** (in order of effectiveness):
1. **Prompt changes** — Butler prompt, sub-agent prompts (most effective)
2. **Config changes** — YAML parameters (planning strategy, context policy)
3. **Code changes** — only when prompt/config insufficient

Present as table:
```
| Variant | Target File | Change | Hypothesis |
|---------|-------------|--------|------------|
| A | ... | ... | ... |
| B | ... | ... | ... |
| C | ... | ... | ... |
```

### Step 4: WORKTREE + MUTATE

Create 3 worktrees at the SAME LEVEL as the repo (never inside it):
```bash
BRANCH=$(git branch --show-current)
git worktree add ../pytaskforce-evolve-a -b evolve-a $BRANCH
git worktree add ../pytaskforce-evolve-b -b evolve-b $BRANCH
git worktree add ../pytaskforce-evolve-c -b evolve-c $BRANCH
# CRITICAL: copy .env to each worktree
cp .env ../pytaskforce-evolve-a/.env
cp .env ../pytaskforce-evolve-b/.env
cp .env ../pytaskforce-evolve-c/.env
```

Apply each variant's mutations using Read + Edit tools (read from worktree path first).

### Step 5: EVALUATE (9 sub-agents: 3 variants × 3 runs)

For each variant, launch 3 eval sub-agents in parallel (9 total, launched in batches
of 3-6 depending on rate limits). Each sub-agent gets:

```
Run this eval and return ONLY the JSON result line.

Command: cd <WORKTREE_DIR> && uv run python tests/benchmarks/autooptim/eval_butler.py <MODE> 2>/dev/null

The command outputs one JSON line to stdout. Find it and return ONLY that JSON object.
Do NOT summarize or interpret. Return the raw JSON string only.
```

Collect all 9 JSON results. Compute median of primary metric per variant.

### Step 6: JUDGE — Compare Medians

Present comparison table:
```
| | Baseline | A | B | C |
|---|---|---|---|---|
| primary_metric (median) | ... | ... | ... | ... |
| secondary_metric (median) | ... | ... | ... | ... |
| task_completion (min) | ... | ... | ... | ... |
| Δ primary vs baseline | — | ...% | ...% | ...% |
```

**Winner selection rules:**
1. `task_completion` must be >= baseline (no regression on completions)
2. Primary metric must improve by >= 5% over baseline median
3. If tie on primary, use secondary metric
4. If multiple variants improve different files → RECOMBINE (merge all)
5. If no variant improves >= 5% → NO WINNER, try different mutations next cycle

### Step 7: REGRESSION GATE + MERGE + CLEANUP

**Before merging, run regression smoke test on the winner worktree:**
```
cd ../pytaskforce-evolve-{x} && uv run python tests/benchmarks/autooptim/eval_butler.py regression
```
This runs 6 core capability tests (~2 min): text file read, PDF read, web search, email, memory, delegation.
If ANY test fails → **REJECT the variant**. Do NOT merge.

**If winner AND regression passes:**
```bash
cd ../pytaskforce-evolve-{x} && git add <changed_files> && git commit -m "feat: <desc> (evolve <objective> cycle N)"
cd <REPO_DIR> && git merge evolve-{x} --no-edit
```

**Always cleanup:**
```bash
git worktree remove ../pytaskforce-evolve-a --force
git worktree remove ../pytaskforce-evolve-b --force
git worktree remove ../pytaskforce-evolve-c --force
git branch -D evolve-a evolve-b evolve-c 2>/dev/null
```

**Log result** — append one line to `.autooptim/evolve_log.jsonl`:
```json
{"cycle": N, "objective": "...", "baseline_median": ..., "winner": "A|B|C|none", "improvement_pct": ..., "files_changed": [...], "timestamp": "..."}
```

Then continue to next cycle (Step 1 with updated codebase).

## Key Files to Mutate

| Target | File | What to change |
|--------|------|----------------|
| Butler coordination | `src/taskforce/core/prompts/autonomous_prompts.py` → `BUTLER_SPECIALIST_PROMPT` | Task patterns, delegation, error recovery, output style |
| PC-Agent (files, docs) | `src/taskforce/configs/custom/pc-agent.yaml` → `system_prompt` | Tool hierarchy, batch processing, efficiency |
| Research-Agent (web) | `src/taskforce/configs/custom/research_agent.yaml` → `system_prompt` | Completeness, search strategy |
| Butler config | `src/taskforce/configs/butler.yaml` | max_steps, planning_strategy_params, context_policy |
| Context policy | `src/taskforce/core/domain/context_policy.py` | Default budget values |
| Message compression | `src/taskforce/core/domain/lean_agent_components/message_history_manager.py` | Compression thresholds |
| LLM routing | `src/taskforce/configs/llm_config.yaml` | Model routing rules per phase |

## Proven Patterns

1. **Prompt > config** — "max 3 tool calls" in prompt works. `max_steps: 8` in config causes abort+retry.
2. **Concrete fallbacks > generic** — "if reminder fails → calendar event" works. "try alternatives" doesn't.
3. **"ONE comprehensive delegation"** — biggest single improvement. Eliminates redundant steps/tokens.
4. **Sub-agent completeness** — "deliver ALL requested points in one pass" prevents re-delegation.
5. **Parallel direct tools** — For multi-source (calendar+email), Butler calls both directly.
6. **Deterministic tool patterns** — Python/pathlib template for dir scans eliminates variance.
7. **PC-agent prompt > Butler prompt** — sub-agent's own instructions are more reliable than delegation wording.

## Anti-Patterns

- Hard config limits (max_steps reduction) → abort+retry loops
- Generic "try harder" instructions → no measurable effect
- Testing in worktrees without `.env` → API errors
- Combined mutations (A+B in one variant) → can regress; isolate changes
- Single eval run → LLM noise dominates; always use 3-run median

## Session End

After all cycles complete:
1. Show cumulative results table (baseline → final, per metric)
2. Update `docs/optimization-report.md` with session results
3. List remaining weaknesses for next session

## Session Start

$ARGUMENTS

If no arguments provided, show the objectives table and ask: "Which objective should we optimize?"
