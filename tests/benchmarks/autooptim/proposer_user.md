# Experiment Proposal Request

## Assigned Category: {category}

## Experiment History

{experiment_history}

## Current Baseline

Composite score: {baseline_composite:.4f}
{baseline_scores_text}

## Per-Mission Analysis

Look at the per-mission scores above to identify specific problems:
- `baseline_*` = zero-tool question overhead
- `singletool_*` = delegation efficiency
- `docreport_*` = multi-agent synthesis (THE HARDEST MISSION)
- `multistep_*` = direct tool use (full eval only)

Priority rules:
1. If any `*_completed = 0` -> that mission is BROKEN. Fix it first (quality > efficiency)
2. If `notification_spam > 3` -> butler is stuck in a notification loop. Fix the prompt.
3. If `docreport_steps > 6` -> butler is over-deliberating after delegation
4. If `singletool_steps > 3` -> delegation overhead is too high
5. If `baseline_steps > 1` -> system prompt is causing unnecessary reasoning

## Current File State

{current_files}

## Instructions

Propose a SINGLE experiment in the "{category}" category.

The composite metric weighs **efficiency at 60%** and **quality at 40%**:
- Quality: task_completion (all missions must succeed)
- Efficiency: fewer steps, tokens, wall time, tool calls, notifications

**Use the tool trace** (in last_eval_trace.md above) to diagnose the root cause before proposing a fix. Don't guess — look at what actually happened.

**Regression check:** If a previous experiment was DISCARDED, check which per-mission scores dropped. Target your fix at the specific regression.

Remember:
- Change only ONE variable
- NEVER modify tool lists in YAML configs
- NEVER rename exported symbols in Python files
- Be specific and provide complete file content (for prompt/code) or a YAML dict (for config)
- Build on what worked before; avoid repeating what failed
- The experiment must be in the "{category}" category

Return your experiment plan as a JSON object.
