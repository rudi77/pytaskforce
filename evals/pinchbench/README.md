# PinchBench integration

Runs [pinchbench](https://github.com/pinchbench/skill) task definitions
against the Taskforce agent through Inspect AI.

This integration deliberately **does not** depend on the upstream
`openclaw` CLI or pinchbench's own `scripts/benchmark.py` runner — both
of those treat pinchbench as a "test a model via OpenClaw" benchmark.
We instead vendor only what's stable (the task markdowns + manifest +
fixtures) and own the loop end-to-end so Taskforce is the agent under
test.

## How it works

1. **Task source**: `loader.ensure_skill_checkout()` shallow-clones
   `pinchbench/skill` into `evals/pinchbench/skill/` on first use
   (gitignored). Pass `update=True` (or wipe the directory) to refresh.
2. **Task loader** (`loader.py`): parses each `task_*.md` file
   (YAML frontmatter + `## Prompt | Expected Behavior | Grading Criteria
   | Automated Checks | LLM Judge Rubric` sections) into a
   `PinchbenchTask` dataclass. Suites supported: `all`, `core`,
   `<category>`, or `task_a,task_b,...`.
3. **Solver** (`solver.py`): provisions an isolated workspace dir
   (with any `workspace_files:` fixtures copied from `skill/assets/`),
   passes its absolute path to the agent via prompt augmentation
   (no `os.chdir` — Inspect AI runs samples concurrently and process-
   wide CWD changes are unsafe), runs Taskforce via
   `AgentExecutor.execute_mission_streaming`, and translates the event
   stream into pinchbench's transcript format.
4. **Scorer** (`scorer.py` + `grading.py`):
   * `grading_type=automated` → execute the task's `def grade(transcript,
     workspace_path)` function in a subprocess with a wall-clock cap,
     mean-aggregate the returned criterion scores.
   * `grading_type=llm_judge` → call a Taskforce LLM with the task's
     rubric and the rendered transcript, parse `{"score": float, ...}`.
   * `grading_type=hybrid` → run both, then average. This matches
     pinchbench's intent that automated and judge signals should agree.

The whole thing plugs into Inspect AI like the existing GAIA and
SWE-bench tasks, so `inspect view` shows results the same way.

## Prerequisites

* `uv sync --extra evals` — installs Inspect AI
* `git` — used to clone the skill repo on first run
* LLM credentials for whichever `--model` you pass (Azure / OpenAI /
  OpenRouter / Anthropic), exposed through `.env`

## Usage

```bash
# Quick smoke test — first 5 core tasks
python evals/run_eval.py pinchbench_smoke

# ~25 representative core tasks
python evals/run_eval.py pinchbench_core

# Single category
python evals/run_eval.py pinchbench_coding --model openai/azure/gpt-5.4-mini

# Full benchmark (~180 tasks, slow)
python evals/run_eval.py pinchbench_full
```

Tasks register with Inspect AI via `evals/tasks/pinchbench.py`; the
`run_eval.py` shortcuts (`pinchbench_smoke`, `pinchbench_core`,
`pinchbench_<category>`, `pinchbench_full`) cover the common entry
points. Drop into `inspect_ai` directly for ad-hoc filters:

```bash
inspect eval evals/tasks/pinchbench.py@pinchbench_core \
    --model openai/azure/gpt-5.4-mini --max-samples 4
```

## Layout

```
evals/pinchbench/
├── __init__.py
├── README.md           ← you are here
├── loader.py           ← clone + parse task markdowns
├── transcript.py       ← Taskforce events → pinchbench transcript
├── grading.py          ← subprocess-isolated automated check + LLM judge
├── solver.py           ← Inspect AI solver wrapping AgentExecutor
├── scorer.py           ← Inspect AI scorer applying hybrid grading
└── skill/              ← upstream pinchbench/skill checkout (gitignored)

evals/tasks/pinchbench.py
    @task pinchbench_smoke / pinchbench_core / pinchbench_full /
          pinchbench_<category>

agents/pinchbench-agent/
    configs/pinchbench.yaml  ← profile consumed by pinchbench_solver
```

## Limitations

* The transcript translation maps Taskforce events to OpenClaw's
  message shape on a best-effort basis. Automated graders that inspect
  fine-grained OpenClaw-only fields (skill activation events, internal
  workflow state) will under-count; the LLM judge picks up the slack
  in `hybrid` mode. When the automated check errors inside a hybrid
  task, the scorer falls back to judge-only and tags the result as
  `hybrid_degraded_to_judge_only` so analysis can filter those rows.
* Multi-session tasks (`multi_session_prompts:`) are parsed into
  metadata but currently executed as a single session — extending the
  solver to honour the session-reset semantics is a follow-up. A WARN
  is logged at sample-build time so users know which tasks are
  affected.
* Workspace fixtures named in `workspace_files:` are copied flat into
  the temp workspace; tasks that expect nested asset paths may need
  loader tweaks.

## Security boundary

`grading.py:run_automated_check` executes Python authored upstream in
the pinchbench/skill repo. The subprocess inherits the eval-harness's
environment and interpreter (same filesystem + network reach), so the
trust boundary is the same as cloning any third-party repo and
running its scripts. Today every pinchbench grader is Stdlib-only;
if that ever changes, sandbox further (Docker, `resource` rlimits,
restricted `PYTHONHOME`).
