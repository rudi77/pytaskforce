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

Propose a SINGLE experiment in the "{category}" category that you believe will improve the composite score. Focus on quality (task_completion, output_accuracy, model_graded_qa) as it accounts for 90% of the composite metric.

Remember:
- Change only ONE variable
- Be specific and provide complete file content (for prompt/code) or a YAML dict of changes (for config)
- Build on what worked before; avoid repeating what failed
- The experiment must be in the "{category}" category

Return your experiment plan as a JSON object.
