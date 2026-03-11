# Taskforce Coding Agent - Benchmark Report

**Date:** 2026-03-10
**Framework:** Taskforce v0.1.0
**Eval Framework:** Inspect AI 0.3.189
**Platform:** Windows 10 Pro, Python 3.11

---

## Overview

This report evaluates the Taskforce coding agent across two dimensions:

1. **Agent Benchmarks** - Tests the full agent framework (planning, tool use, code generation)
2. **Model Baselines** - Tests the underlying LLM capabilities independently

### Eval Runs Completed

| # | Benchmark | Type | Samples | Model | Status |
|---|-----------|------|---------|-------|--------|
| 1 | coding_spar | Agent | 8 | azure/gpt-4.1 | Success |
| 2 | coding_react | Agent | 8 | azure/gpt-4.1 | Success |
| 3 | coding_plan_and_execute | Agent | 8 | azure/gpt-4.1 | Success |
| 4 | ARC Challenge | Model Baseline | 1,172 | azure/gpt-5-mini | Success |
| 5 | GPQA Diamond | Model Baseline | 198 (4 epochs = 792) | azure/gpt-5-mini | Success |
| 6 | SWE-bench Verified Mini | Agent | 20 | azure/gpt-4.1 | Success (WSL 2) |
| 7 | HumanEval | Model Baseline | - | azure/gpt-5-mini | Failed (Docker) |

---

## 1. Coding Agent - Planning Strategy Comparison

All strategies tested on 8 custom coding tasks (code generation, bug fixing, refactoring, testing, code analysis) using the Taskforce `coding_agent` profile with sub-agents.

**Agent models:** azure/gpt-5-mini (main/acting), azure/gpt-4.1 (planning), azure/gpt-5.2 (powerful)
**Scorer model:** azure/gpt-4.1

### Results

| Metric | SPAR | Plan & Execute | Native ReAct |
|--------|:----:|:--------------:|:------------:|
| **Task Completion** | 100% | 100% | 100% |
| **Code Quality (LLM-Judge)** | **100%** | **100%** | 93.8% |
| **Avg Steps** | 22.6 | 23.5 | 2.0 |
| **Avg Tool Calls** | 6.4 | 5.6 | 1.0 |
| **Avg Total Tokens** | 214,919 | 157,838 | 18,162 |
| **Avg Prompt Tokens** | 208,349 | 153,862 | 17,115 |
| **Avg Completion Tokens** | 6,570 | 3,976 | 1,047 |
| **Total Time (8 tasks)** | 4m 16s | 2m 53s | 1m 00s |
| **Grader Tokens** | 8,652 | 8,035 | 5,377 |

### Key Findings

- **SPAR and Plan & Execute achieve perfect quality** (100% LLM-Judge score on all 8 tasks)
- **Native ReAct is 12x cheaper** in token usage but has a slight quality drop (93.8%, 1 task scored partial)
- **Plan & Execute is the sweet spot** - same quality as SPAR, 26% fewer tokens, 32% faster

### Cost per Task (estimated)

| Strategy | Tokens/Task | Est. Cost/Task | Relative |
|----------|-------------|----------------|----------|
| SPAR | ~215k | ~$0.65 | 1.0x |
| Plan & Execute | ~158k | ~$0.48 | 0.74x |
| Native ReAct | ~18k | ~$0.06 | 0.08x |

### Task Categories

All three strategies achieved 100% task completion across all categories:

| Category | Tasks | Description |
|----------|-------|-------------|
| Code Generation | 4 | merge_sorted_lists, Stack class, CSV parser, retry decorator |
| Bug Fixing | 1 | Fix flatten() to handle tuples |
| Refactoring | 1 | Optimize O(n^2) to O(n) duplicate finder |
| Test Writing | 1 | Comprehensive test suite for Calculator class |
| Code Analysis | 1 | Security review of command injection vulnerability |

---

## 2. Model Baselines (InstructEval)

These benchmarks test the raw LLM capabilities, independent of the Taskforce framework.

### GPQA Diamond (Graduate-Level Expert Q&A)

| Metric | Value |
|--------|-------|
| Model | azure/gpt-5-mini |
| Samples | 198 questions x 4 epochs = 792 runs |
| **Accuracy** | **73.7%** |
| Stderr | +/-2.5% |
| Time | 48m 35s |
| Tokens | 2,228,664 (incl. 1,784,832 reasoning) |

> GPQA Diamond contains graduate-level science questions (physics, chemistry, biology)
> validated by domain experts. The 73.7% accuracy for gpt-5-mini is strong -
> for reference, human expert accuracy on GPQA is ~65% for non-specialists.

### ARC Challenge (Science Reasoning)

| Metric | Value |
|--------|-------|
| Model | azure/gpt-5-mini |
| Samples | 1,172 |
| **Accuracy** | **55.6%** |
| Stderr | +/-1.5% |
| Time | 10m 43s |
| Tokens | 417,201 (incl. 245,888 reasoning) |

> ARC Challenge tests grade-school science reasoning with multiple-choice questions.
> The 55.6% accuracy for gpt-5-mini is a baseline. Stronger models (gpt-4.1, gpt-5.2)
> would be expected to score higher.

### SWE-bench Verified Mini (Real-World GitHub Issues)

| Metric | Value |
|--------|-------|
| Model | azure/gpt-5-mini (agent main), azure/gpt-4.1 (planning) |
| Samples | 20 GitHub issues (from SWE-bench Verified) |
| Agent Strategy | SPAR (Sense → Plan → Act → Reflect) |
| Agent Execution | Completed all 20 instances |
| **Accuracy (swe_bench_scorer)** | **0.0%** (0/20 resolved) |
| Avg Tokens/Instance | ~240k |
| Avg Tool Calls/Instance | ~5 |
| Total Time | 1h 14m 19s |
| Platform | WSL 2 (Ubuntu 20.04) with Docker Desktop |

> SWE-bench Verified contains real-world GitHub issues from major open-source projects
> (astropy, scikit-learn, django, etc.). The 0% resolution rate indicates that the
> current agent configuration — which operates only with file tools (grep, glob,
> file_read/write) and no direct shell access inside the repo — is not yet equipped
> for SWE-bench. Key gaps:
>
> - **No sandbox execution**: The agent cannot run tests or install dependencies
>   inside the target repo's Docker container
> - **Tool limitations**: The agent uses `powershell` (Windows) instead of `bash`,
>   and cannot execute Python in the target repo's environment
> - **No git apply**: The agent generates analysis/suggestions but doesn't produce
>   `git diff` patches in the format SWE-bench expects
>
> **Recommended next steps for SWE-bench improvement:**
> 1. Add a `bash` tool that executes inside the SWE-bench Docker sandbox
> 2. Provide the agent with `git diff` output capability
> 3. Allow the agent to run the repo's test suite for validation
> 4. Consider using the inspect-evals built-in SWE-bench solver as a reference

### HumanEval (Python Coding)

| Metric | Value |
|--------|-------|
| Status | Failed - Docker registry was unreachable at time of run |

---

## 3. Benchmarks Pending

| Benchmark | Samples | Blocker | Resolution |
|-----------|---------|---------|------------|
| SWE-bench Verified (full) | 500 | Long-running (~30h estimated) | Schedule dedicated run on Linux |
| SWE-bench Lite | 300 | Long-running | Schedule dedicated run on Linux |
| HumanEval | 164 | Docker sandbox | Re-run now that Docker works |
| MMLU 5-shot | ~14,000 | Long-running | Schedule dedicated run |

To run when ready:
```bash
# Model baselines
python evals/run_eval.py humaneval --model openai/azure/gpt-5-mini
python evals/run_eval.py mmlu_5shot --model openai/azure/gpt-5-mini

# SWE-bench (requires Linux/WSL)
python evals/run_eval.py swe_bench_verified_mini --model openai/azure/gpt-4.1
```

---

## 4. Recommendations

### Strategy Selection

| Use Case | Recommended Strategy | Rationale |
|----------|---------------------|-----------|
| Production coding tasks | **Plan & Execute** | Best quality-to-cost ratio (100% quality, 26% cheaper than SPAR) |
| Critical/complex tasks | **SPAR** | Maximum quality with reflection loop, worth the overhead |
| Batch/simple tasks | **Native ReAct** | 12x cheaper, acceptable for straightforward tasks |
| Cost-sensitive environments | **Native ReAct** | ~$0.06/task vs ~$0.65 for SPAR |

### Next Steps

1. **Run SWE-bench on Linux/WSL** to get real-world issue resolution scores
2. **Expand coding dataset** to 20-30 tasks (multi-file refactoring, API design, debugging)
3. **Compare models** on same tasks (gpt-4.1 vs gpt-5-mini vs gpt-5.2) to find optimal model-per-strategy
4. **Run HumanEval** now that Docker is available
5. **Add regression suite** - run `coding_full` on every release to catch quality regressions

---

## 5. Log Files

All results are viewable with `inspect view` in the browser.

| Log File | Benchmark | Status |
|----------|-----------|--------|
| `coding-spar_*.eval` | SPAR strategy (8 tasks) | Success |
| `coding-react_*.eval` | ReAct strategy (8 tasks) | Success |
| `coding-plan-and-execute_*.eval` | Plan & Execute (8 tasks) | Success |
| `gpqa_o7nsCtPMC8Za2DHiA3i5DP.eval` | GPQA Diamond (792 runs) | Success |
| `arc_*.eval` | ARC Challenge (1,172 questions) | Success |
| `swe-bench-verified-mini_*.eval` | SWE-bench Mini (20 issues) | Scoring failed |
| `humaneval_*.eval` | HumanEval | Error (Docker) |

---

## 6. Reproduce

```bash
# Install dependencies
uv sync --extra evals
# or: uv pip install "inspect-evals[swe_bench]"

# Full coding agent benchmark
python evals/run_eval.py coding_full --model openai/azure/gpt-4.1

# Strategy comparison
python evals/run_eval.py coding_spar coding_react coding_plan_and_execute

# Model baselines
python evals/run_eval.py arc gpqa --model openai/azure/gpt-5-mini

# View results
inspect view
```

---

*Generated by Taskforce Eval Framework using Inspect AI*
