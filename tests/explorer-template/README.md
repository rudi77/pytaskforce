# Exploratory Test Template for Taskforce Agents

A **copyable scaffold** for running autonomous, Claude-driven exploratory
tests against any Taskforce agent. Based on the pattern that produced
the AP-Ledger test suite under
`examples/ap_ledger_agent/tests/explorer/`.

## What it does

1. You write a **test plan** (`test_plan.md`) — a living Markdown
   checklist of scenarios you want covered.
2. Claude works the plan in a `/loop`: picks the next unchecked
   scenario, writes a short Python runner, executes it against a fresh
   agent instance, compares actual vs expected, records the finding in
   `test_report.md`, fixes bugs if needed, commits, and moves on.
3. Each scenario writer is a tiny wrapper around **three harness
   primitives** you implement once for your agent:
   - `make_fresh_env(slug, …)` — provision an isolated customer/workspace
   - `send_message(env, text)` — feed a mission to the agent, collect
     the result
   - `db_query(db_path, sql)` — inspect state afterwards

Everything else — the plan structure, the report layout, the loop
prompt, the commit/push workflow, the branch isolation rules — is
generic and ships with this template.

## Layout

```
tests/explorer-template/
├── README.md                          ← this file
├── LOOP_PROMPT.md                     ← ready-to-paste /loop command
├── test_plan.md                       ← plan skeleton with a legend + examples
├── test_report.md                     ← empty journal with iteration template
└── scenarios/
    ├── _harness.template.py           ← generic helpers + TODO stub for
    │                                     the one agent-specific function
    └── run_example.py                 ← pattern reference for a scenario
```

## How to use

1. **Copy this directory** to wherever your agent's tests should live,
   e.g. `cp -r tests/explorer-template examples/my_agent/tests/explorer`.
2. **Rename** `_harness.template.py` → `_harness.py` and implement
   `make_fresh_env()` for your agent. The other helpers
   (`send_message`, `db_query`, `_install_auto_yes_ask_user`) are
   generic and copy as-is — they work for any Taskforce agent that
   uses the standard `AgentFactory` + `AgentExecutor` pipeline.
3. **Rename** `run_example.py` → `run_s01.py` and adapt it to your
   first scenario.
4. **Fill in** `test_plan.md` with the 6-10 scenarios you want Claude
   to explore first. Keep each scenario to "setup → steps → expected"
   in ~5 lines. Leave Round-2 ideas in the bottom section.
5. **Create a branch** for the exploration session:
   `git checkout -b test/explorer-<date>`.
6. **Start the loop** in Claude Code by pasting the prompt from
   `LOOP_PROMPT.md` (with the branch name substituted).

## Why a template, not a skill?

Kept intentionally as a copyable template (no tooling) because:
- The harness is 80 % agent-agnostic, 20 % agent-specific. You write
  the 20 % once and it becomes part of your tests — not hidden behind
  a wrapper.
- The plan and report are meant to be **yours** — rename, restructure,
  add sections. A scaffold that generates them would keep people from
  taking full ownership.
- Claude Code's `/loop` handles the automation part. This template
  just documents the convention.

If running multiple explorer suites in parallel becomes routine, the
obvious next step is a `/explorer init <agent-dir>` skill that copies
this template with a couple of substitutions. Not needed until it is.

## Workflow rules (enforced by the loop prompt)

- **Branch isolation** — work on `test/explorer-<date>`, never commit
  directly to `main`.
- **Fix-and-prove** — if a scenario fails and Claude fixes it, the fix
  gets a separate commit *before* the plan/report update, and
  `pytest` unit tests must stay green.
- **Architectural blockers stop the loop** — if a finding needs a
  design decision, Claude writes the question into the report and
  halts instead of guessing.
- **Token budget caps** — soft 50k per iteration, hard 500k across
  the loop. Prevents runaway cost.
- **Termination** — all scenarios checked OR 15 iterations OR any
  architectural `[!]` marker.
