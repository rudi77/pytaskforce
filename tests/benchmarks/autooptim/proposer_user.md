# Experiment Proposal Request

## Assigned Category: {category}

## Experiment History

{experiment_history}

## Current Baseline

Composite score: {baseline_composite:.4f}
{baseline_scores_text}

## Current File State

{current_files}

## Instructions

Propose a SINGLE experiment in the "{category}" category that you believe will improve the composite score.

The composite metric weighs **efficiency at 60%** and **quality at 40%**:
- Efficiency: fewer steps, fewer tokens, lower wall time, fewer tool calls
- Quality: missions must still complete successfully (task_completion)

Key targets based on current benchmarks:
- Baseline (zero-tool): ~4,300 input tokens — can this system prompt be shorter?
- Single-tool delegation: ~40,000 tokens, 7 steps — this should be 2-3 steps max
- Memory search happens on every mission — should it?
- send_notification fails every time — should it be called for non-interactive benchmarks?

Remember:
- Change only ONE variable
- NEVER modify tool lists in YAML configs
- Be specific and provide complete file content (for prompt/code) or a YAML dict of changes (for config)
- Build on what worked before; avoid repeating what failed
- The experiment must be in the "{category}" category

Return your experiment plan as a JSON object.
