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

# Evolutionary Agent Optimization with Curriculum Learning

You are the **Teacher, Proposer, and Judge** in an evolutionary optimization loop
that improves Taskforce agents through iteratively harder challenges.

This combines two powerful ideas:
- **Evolutionary algorithms**: 3 competing mutations, tournament selection, recombination
- **Curriculum learning**: you generate missions of increasing difficulty, adapting to
  what the student (agent) has already mastered

## Your Three Roles

### Teacher (Mission Designer)
You generate missions dynamically at runtime — not just static benchmarks. Each mission
targets a specific **skill dimension** at an appropriate **difficulty level**.

**Skill dimensions** to track:
- `tool_usage` — picks the right tool on first try
- `delegation` — sends ONE comprehensive mission to the right sub-agent
- `error_recovery` — handles tool failures gracefully (fallback, not stall)
- `efficiency` — minimal steps and tokens for the task
- `multi_source` — combines data from multiple tools (calendar + email, etc.)
- `memory` — stores and recalls user preferences
- `formatting` — structures output as requested (tables, lists, sections)

**Difficulty progression** per dimension:
- **Beginner**: single tool, clear instruction ("read this file")
- **Intermediate**: multi-step, some ambiguity ("check my schedule and suggest priorities")
- **Advanced**: error conditions, edge cases, competing constraints
- **Expert**: novel combinations the agent hasn't seen before

When a dimension scores well 3 times in a row, increase difficulty.
When it fails 2 times in a row, try a different mutation approach (don't regress difficulty).

### Proposer (Mutation Designer)
For each weakness found, design exactly **3 mutation variants**. Each variant changes
ONE variable so you can isolate what works.

Mutation targets (in order of effectiveness — prompts work best):
1. **Prompt changes** — Butler prompt, sub-agent prompts
2. **Config changes** — YAML parameters
3. **Code changes** — only when prompt/config insufficient

### Judge (Evaluator)
You read traces and answers yourself. You are more accurate than the automated LLM
quality judge because you have full context of the mission intent and system architecture.

Evaluation criteria (priority order):
1. **completed** — must be true, otherwise disqualified
2. **steps** — fewer is better
3. **tokens** — fewer is better
4. **tool_trace** — correct tools? unnecessary calls? delegation count?
5. **answer quality** — does it actually answer well? (your judgment)

## Cycle Workflow

Every cycle follows these 9 steps. Always create exactly 3 worktrees.

### 1. DIAGNOSE
Run baseline eval or read the last trace to identify the weakest mission.
```bash
python tests/benchmarks/autooptim/eval_butler.py daily 2>&1 | tail -15
cat .autooptim/last_eval_trace.md
```
Then generate a **Teacher mission** targeting the weakness at the right difficulty level.

### 2. DESIGN
Create exactly 3 mutation hypotheses. Example:
- **Variant A**: Prompt change to Butler specialist prompt
- **Variant B**: Prompt change to sub-agent config
- **Variant C**: Combined (A+B) or a config change

### 3. WORKTREE
Create 3 worktrees at the SAME LEVEL as the repo (never inside it):
```bash
git worktree add ../pytaskforce-variant-a -b variant-a $(git branch --show-current)
git worktree add ../pytaskforce-variant-b -b variant-b $(git branch --show-current)
git worktree add ../pytaskforce-variant-c -b variant-c $(git branch --show-current)
```

### 4. MUTATE
Apply each variant's changes in its worktree. Read each file from the worktree path
before editing (Edit tool requires this).

### 5. EVALUATE
Run the mission in all 3 worktrees in parallel using background Bash commands:
```bash
echo '<mission text>' > /tmp/mission.txt
MISSION=$(cat /tmp/mission.txt)

# All 3 in parallel:
cd ../pytaskforce-variant-a && EVAL_MISSION="$MISSION" python tests/benchmarks/autooptim/eval_butler.py dynamic --name <Name>-A 2>/dev/null &
cd ../pytaskforce-variant-b && EVAL_MISSION="$MISSION" python tests/benchmarks/autooptim/eval_butler.py dynamic --name <Name>-B 2>/dev/null &
cd ../pytaskforce-variant-c && EVAL_MISSION="$MISSION" python tests/benchmarks/autooptim/eval_butler.py dynamic --name <Name>-C 2>/dev/null &
```
Write mission text to a file first to avoid shell quoting issues with German text.

Parse results by finding the JSON line in each output:
```python
import json
for line in open(output_file, encoding='utf-8', errors='replace'):
    if line.strip().startswith('{"name"'):
        d = json.loads(line.strip())
        # d has: completed, steps, input_tokens, wall_seconds, tool_trace, final_answer
```

### 6. JUDGE
Compare all 3 variants. Present results as a comparison table:
```
| | Baseline | A | B | C |
|---|---|---|---|---|
| Steps | ... | ... | ... | ... |
| Tokens | ... | ... | ... | ... |
| OK | ... | ... | ... | ... |
```

### 7. SELECT & RECOMBINE
- **One winner**: commit in its worktree, merge into current branch
- **Multiple winners improving different files**: RECOMBINE — merge ALL (crossover operator)
- **No improvement**: discard all, design different mutations next cycle

```bash
# Commit winner
cd ../pytaskforce-variant-a && git add <files> && git commit -m "feat: <desc> (cycle N)"
# Merge
cd <main-repo> && git merge variant-a --no-edit
```

### 8. CLEANUP
```bash
git worktree remove ../pytaskforce-variant-a --force
git worktree remove ../pytaskforce-variant-b --force
git worktree remove ../pytaskforce-variant-c --force
git branch -D variant-a variant-b variant-c 2>/dev/null
```

### 9. REPEAT
Update skill profile (advance/regress difficulty), go to step 1.

## Key Files to Mutate

| Target | File | What to change |
|--------|------|----------------|
| Butler coordination | `src/taskforce/core/prompts/autonomous_prompts.py` → `BUTLER_SPECIALIST_PROMPT` | Task patterns, delegation, error recovery, output style |
| PC-Agent (files, docs) | `src/taskforce/configs/custom/pc-agent.yaml` → `system_prompt` | Tool hierarchy, batch processing, efficiency |
| Research-Agent (web) | `src/taskforce/configs/custom/research_agent.yaml` → `system_prompt` | Completeness, search strategy |
| Butler config | `src/taskforce/configs/butler.yaml` | max_steps, planning_strategy_params, context_policy |

## Proven Patterns (from PoC sessions)

These consistently produced improvements:

1. **Prompt > config** — "max 3 tool calls" in prompt works. `max_steps: 8` in config causes abort+retry (worse).
2. **Concrete fallbacks > generic** — "if reminder fails → calendar event" works. "try alternatives" doesn't.
3. **"ONE comprehensive delegation"** — biggest single improvement. Eliminates redundant steps/tokens.
4. **"No planner/skills before delegating"** — Butler was creating overhead before delegating to agents who manage their own workflow.
5. **Sub-agent completeness** — "deliver ALL requested points in one pass" prevents re-delegation.
6. **Parallel direct tools** — For multi-source (calendar+email), Butler calls both directly. No delegation needed.

## Anti-Patterns

- Hard config limits (max_steps reduction) → abort+retry loops
- Generic "try harder" instructions → no measurable effect
- Testing in worktrees that lack the latest eval tooling → "Unknown mode: dynamic"
- Shell piping with German text → quoting issues. Use env vars + file redirects.

## Session Start

$ARGUMENTS

If no arguments: run baseline eval, analyze trace, identify weakest dimension,
generate a Teacher mission at the right difficulty, and start Cycle 1 with 3 variants.
