---
name: code-review-pipeline
description: Multi-step code review pipeline that analyzes code for bugs, security issues, and quality, then produces a structured report.
type: context
---

# Code Review Pipeline

## Objective

Perform a comprehensive, multi-agent code review on a given codebase path. Delegates specialized analysis to sub-agents and aggregates results into a structured report.

## Required Input

- **target_path**: Path to the file or directory to review (ask user if not provided)

## Workflow Steps

### Step 1: Code Discovery

- **Action**: Scan the target path to understand the codebase structure
- **Agent/Tool**: `pc-agent` — list files, detect languages, identify entry points
- **Input**: `target_path` from user
- **Output**: File list, language breakdown, architecture overview

### Step 2: Static Analysis

- **Action**: Run linters and static analysis tools on the code
- **Agent/Tool**: `coding_agent` — execute ruff, mypy, eslint (as appropriate for the language)
- **Input**: File list from Step 1
- **Output**: Lint errors, type errors, style violations

### Step 3: Security Review

- **Action**: Check for common security vulnerabilities (OWASP Top 10)
- **Agent/Tool**: `coding_agent` — analyze for injection, XSS, CSRF, secrets in code
- **Input**: File list from Step 1
- **Output**: Security findings with severity ratings

### Step 4: Quality Analysis

- **Action**: Evaluate code quality, complexity, and maintainability
- **Agent/Tool**: `analysis_agent` — calculate cyclomatic complexity, duplication, test coverage
- **Input**: File list from Step 1
- **Output**: Quality metrics, improvement suggestions

### Step 5: Report Generation

- **Action**: Aggregate all findings into a structured Markdown report
- **Agent/Tool**: Direct (no sub-agent needed) — combine outputs from Steps 2-4
- **Input**: Outputs from Steps 2, 3, and 4
- **Output**: Final review report saved to file

## Output Format

```markdown
# Code Review Report: <target_path>

## Summary
- Files reviewed: N
- Critical issues: N
- Warnings: N
- Overall quality score: X/10

## Static Analysis
<findings from Step 2>

## Security Review
<findings from Step 3>

## Quality Metrics
<findings from Step 4>

## Recommendations
<prioritized list of improvements>
```

## Error Handling

- If target_path is not provided: ask the user via `ask_user`
- If a sub-agent fails: log the error and continue with remaining steps
- If no issues found: report clean status with positive feedback
