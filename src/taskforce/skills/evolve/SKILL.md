---
name: evolve
type: prompt
description: >
  Evolutionary agent optimization using parallel worktree variants. Invoke with
  /evolve to start a Teacher-Student optimization session. Use when the user wants
  to improve agent performance, optimize prompts, reduce steps/tokens, fix failing
  missions, or run benchmark-driven iterative improvement. Also triggers for
  "optimize the butler", "make the agent faster", "reduce token usage",
  "fix the failing mission", or "run optimization cycles".
slash-name: evolve
---

# Evolutionary Agent Optimization

You are the **Teacher, Proposer, and Judge** in an evolutionary optimization loop.
You iteratively improve any Taskforce agent by analyzing execution traces, designing
competing mutations, testing them in parallel git worktrees, and merging the winners.

This is inspired by evolutionary algorithms:
- **Mutation**: each variant tests ONE hypothesis
- **Selection**: best variant survives (tournament selection)
- **Recombination**: when multiple variants improve different things, merge all (crossover)

## Your Three Roles

**Teacher** — Analyze traces to identify the weakest mission or skill dimension.
Design targeted missions that expose specific weaknesses. Skill dimensions to track:
tool_usage, delegation, error_recovery, efficiency, memory, formatting, multi_step_reasoning.

**Proposer** — Design 2-3 mutation variants per weakness. Each variant changes ONE variable.
Mutation targets (in order of preference):
1. Prompt changes (most effective, lowest risk)
2. Config changes (moderate effect)
3. Code changes (highest effect, highest risk — only when prompt/config insufficient)

**Judge** — Read traces and final answers yourself. You are the judge because you have
full context of the system, the mission intent, and what a good answer looks like.
Do NOT rely on the automated `_llm_quality_grade()` — it uses a cheap model and is inconsistent.

## Cycle Workflow

Each optimization cycle follows this exact sequence:

### 1. DIAGNOSE
Run a baseline eval or read the last trace to find the weakest mission.
```bash
python tests/benchmarks/autooptim/eval_butler.py daily 2>&1 | tail -15
```
Read the detailed trace:
```bash
cat .autooptim/last_eval_trace.md
```
Identify: Which mission has the most steps? Highest tokens? Failed? Worst answer quality?

### 2. DESIGN
Create 2-3 mutation hypotheses targeting the weakness. For each variant, describe:
- What you're changing and why
- Which file(s) to modify
- Expected impact on the metric

### 3. WORKTREE
Create worktrees at the SAME LEVEL as the repo (never inside it).
**Important**: Always create worktrees from the CURRENT branch so they include all
previous optimizations AND the latest eval tooling (dynamic mode, etc.).
```bash
git worktree add ../pytaskforce-variant-a -b variant-a $(git branch --show-current)
git worktree add ../pytaskforce-variant-b -b variant-b $(git branch --show-current)
```

### 4. MUTATE
Apply each variant's changes in its worktree. You must `Read` each file from the
worktree path before editing it (the Edit tool requires this).

### 5. EVALUATE
Run the target mission in each worktree in parallel.

**For dynamic missions** (arbitrary mission text):
```bash
echo 'Mission text here' > /tmp/mission.txt
MISSION=$(cat /tmp/mission.txt) && cd <worktree-path> && \
  EVAL_MISSION="$MISSION" python tests/benchmarks/autooptim/eval_butler.py dynamic \
  --name <VariantName> 2>/dev/null
```

**For standard missions** (quick/full/daily):
```bash
cd <worktree-path> && python tests/benchmarks/autooptim/eval_butler.py quick 2>/dev/null
```

Run all variants as background Bash commands. Parse results with:
```python
import json
# Find the JSON line in the output
for line in open(output_file, encoding='utf-8', errors='replace'):
    if line.strip().startswith('{"name"'):
        d = json.loads(line.strip())
        # d has: completed, steps, input_tokens, wall_seconds, tool_trace, final_answer, errors
```

### 6. JUDGE
Compare results across variants. Evaluation criteria (in priority order):
1. **completed** — must be true. Failed = disqualified.
2. **steps** — fewer is better (measures reasoning efficiency)
3. **input_tokens** — fewer is better (measures cost)
4. **tool_trace** — correct tool selection? unnecessary calls? delegation count?
5. **final_answer** — does it actually answer the question well? (your judgment)

### 7. SELECT & RECOMBINE
- If ONE variant is best: commit its changes in the worktree, merge into current branch
- If MULTIPLE variants improve DIFFERENT files: **RECOMBINE** — commit and merge ALL
  (e.g., Variant A improved Butler prompt, Variant B improved research_agent config → merge both)
- If NO variant improves: discard all, try different hypotheses next cycle

```bash
# Commit winner in worktree
cd <worktree> && git add <files> && git commit -m "feat: <description> (cycle N)"

# Merge into current branch
cd <main-repo> && git merge <variant-branch> --no-edit
```

### 8. CLEANUP
```bash
git worktree remove ../pytaskforce-variant-a --force
git worktree remove ../pytaskforce-variant-b --force
git branch -D variant-a variant-b 2>/dev/null
```

### 9. REPEAT
Go to step 1 with the improved baseline. Continue until:
- User says stop
- All missions pass with acceptable efficiency
- No more improvements found (diminishing returns)

## Key Files to Mutate

| Target | File | What to change |
|--------|------|----------------|
| Butler delegation & coordination | `src/taskforce/core/prompts/autonomous_prompts.py` → `BUTLER_SPECIALIST_PROMPT` | Task patterns, delegation rules, output style, error recovery |
| PC-Agent (files, system, docs) | `src/taskforce/configs/custom/pc-agent.yaml` → `system_prompt` | Tool selection hierarchy, batch processing, efficiency limits |
| Research-Agent (web, facts) | `src/taskforce/configs/custom/research_agent.yaml` → `system_prompt` | Search strategy, completeness, source quality |
| Butler config | `src/taskforce/configs/butler.yaml` | max_steps, planning_strategy_params, context_policy |
| Sub-agent configs | `src/taskforce/configs/custom/*.yaml` | max_steps, tools, context_management |

## Proven Optimization Patterns

These patterns consistently produced improvements across multiple PoC cycles:

1. **Prompt instructions > config limits** — "max 3 tool calls" in prompt works;
   `max_steps: 8` in config causes premature abort and retries (worse overall).

2. **Concrete fallback paths > generic error handling** — "if reminder fails, create
   a calendar event" works; "try alternatives" doesn't survive the no-progress stall detector.

3. **"ONE comprehensive delegation"** — Telling the Butler to send one complete mission
   instead of multiple sequential ones eliminates the biggest source of wasted steps/tokens.

4. **"No planner/skills before delegating"** — The Butler was activating skills and
   creating plans before delegating to sub-agents who handle their own workflow.
   Removing this overhead cut DocReport from 7 to 2 steps.

5. **Sub-agent completeness rules** — "Deliver ALL requested points in one pass"
   prevents the Butler from re-delegating for "the remaining items".

6. **Parallel tool calls at Butler level** — For multi-source tasks (calendar + email),
   the Butler can call both tools in one step. No delegation needed.

## Anti-Patterns to Avoid

- Don't reduce `max_steps` to force efficiency — it causes abort + retry loops
- Don't add generic "try harder" instructions — they have no measurable effect
- Don't test mutations against the wrong eval mode (ensure worktrees have `dynamic` mode)
- Don't pipe eval output through `tail` with German text — use env vars and file redirects
- Don't create worktrees before committing eval tooling changes to the branch

## Session Start

$ARGUMENTS

If no arguments provided, start with a baseline evaluation and analyze the trace.
