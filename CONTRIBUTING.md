# Contributing to pytaskforce

This document describes the **actual** development cycle we run on this
repo — board-driven, spec-first, direct-to-main for small changes, with
mandatory documentation upkeep. It is the canonical source; `CLAUDE.md`
and the PR template link back here.

> If you find this document out of date relative to how work is really
> being done, that is itself a bug — open an issue or update the file
> in the same PR that changes the process.

---

## TL;DR — One Cycle, Nine Steps

```
1. Pick work from Project #3   →  /code-review-board, /spec-check
2. Think before coding         →  CLAUDE.md §1
3. Update the spec (if needed) →  docs/spec/<feature>.md
4. Implement surgically        →  CLAUDE.md §2-§3
5. Write spec()-tagged tests   →  @pytest.mark.spec("feature.invariant")
6. Local quality gates         →  black, ruff, mypy, pytest
7. Commit + push               →  direct-to-main for small fixes
8. Update docs                 →  README, docs/cli.md, docs/api.md, …
9. CI + tag                    →  .github/workflows/ci.yml
```

---

## 1. Source of Work — Board-Driven

All work originates on **GitHub Project #3 ("PyTaskforce", owner
`rudi77`)**. Before writing code:

- Confirm an issue exists. If not, surface the gap and create one
  before starting — do not silently implement.
  (Memory: `feedback_board_driven_work`.)
- **Feature freeze since v0.2.0 (2026-05-06)**: no new features, only
  bug fixes, improvements, and tests. User-requested capabilities are
  an explicit override and must be tagged as such on the issue.
  (Memory: `project_feature_freeze_post_adr022`.)
- **Gap classification**: a missing piece in a shipped feature is a
  *bug* (freeze does not cover that); net-new authoring or scope is a
  *feature* and is deferred.
  (Memory: `feedback_multitenant_gap_classification`.)
- **Code-review P0 items (#276–#375)** have a high false-positive rate.
  Verify each against live code before implementing.
  (Memory: `feedback_codereview_p0_triage_first`.)
- **Agent packages** (Butler, Coding, RAG, …) are intentionally *not*
  in `docs/spec/`. Improve via evals + monitoring, not spec drift.
  (Memory: `feedback_agents_out_of_spec`.)

### Skills for this step

| Skill | When to use |
|---|---|
| `/code-review-board` | Repo-wide review (bugs, security, architecture, concurrency, performance, smells). Creates one Project #3 issue per finding. Optimized for pytaskforce; follows the playbook in `reference_code_review_playbook`. |
| `/spec-check` | Verify every spec in `docs/spec/` against the live codebase. Use after refactors or when a contract may have shifted. Reports P0/P1/P2 drift. |
| `/security-review` | Targeted security review of the pending changes on the current branch. |

### `gh` CLI usage

Always `unset GITHUB_TOKEN` before any `gh` call — the env var holds a
stale token; keyring auth is the valid one.
(Memory: `feedback_gh_clear_token`.)

```bash
unset GITHUB_TOKEN
gh project item-list 3 --owner rudi77 --format json --limit 600
```

---

## 2. Think Before Coding

From `CLAUDE.md` §1 (Behavioral guidelines):

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- For multi-step tasks, state a brief plan with a verification step
  per step.

---

## 3. Update the Spec (if the change touches a contract)

The `docs/spec/` directory is the **contract** for each subsystem
(conversations, gateway, react-loop, …). If the work changes a
capability, invariant, API surface, configuration, or test obligation:

1. Edit `docs/spec/<feature>.md` **first**.
2. Bump `last_verified:` in the frontmatter to today.
3. Add new Capabilities, Invariants, API rows.
4. Add `spec("<feature>.<invariant_name>")` entries to the Tests
   section — these are the marker strings the tests must use.

Agent-package code lives outside this discipline by design — those
packages move too fast for a spec layer (see
`feedback_agents_out_of_spec`).

---

## 4. Implementation — Clean Architecture, Surgical Changes

### Architectural rules (PR template enforces)

- Four-layer separation: **Core (Domain + Interfaces) → Infrastructure
  → Application → API**. Dependency direction inward only.
- Core domain has **zero** infrastructure dependencies.
- New interfaces use **Python Protocols** (PEP 544), not ABCs.

(Full layer matrix and import rules in `CLAUDE.md` §"Clean Architecture".)

### Surgical-change discipline (`CLAUDE.md` §3)

- Touch only what you must. Don't "improve" adjacent code.
- Match existing style, even if you would do it differently.
- Remove orphans (imports / variables / functions) *your* changes
  created. Don't delete pre-existing dead code unless asked.
- Every changed line should trace back to the user's request.

### Path rules (memory-derived)

| Concern | Correct location | Wrong location |
|---|---|---|
| Agent YAML / `.agent.md` configs | `agents/<agent>/configs/` | `src/taskforce/configs/` |
| Workflow management UI (CRUD/list/run) | `ui/` (this repo) | enterprise repo |
| Long-term memory access | on-demand via `wiki` tool or memory_specialist sub-agent | auto-inject into master system prompt |

Memories: `feedback_agent_configs_location`,
`feedback_workflow_ui_location`, `feedback_no_wiki_in_system_prompt`.

### Skills for this step

| Skill | When to use |
|---|---|
| `/run` | Launch this project's app to see a change in context. Tries a project-skill first, falls back to built-in patterns per project type. |
| `/init` | Bootstrap `CLAUDE.md` (one-off per repo). |

---

## 5. Tests — Spec-Tagged

- Every spec point gets a test with `@pytest.mark.spec("feature.invariant_name")`.
  (Goal: `project_spec_test_coverage_goal`, set 2026-05-21.)
- Mirror source structure under `tests/unit/` and `tests/integration/`.
- Coverage targets: Core ≥ 90 %, Infra ≥ 80 %, Application ≥ 75 %,
  total ≥ 80 %.
- Issues found while testing → straight onto Project #3.

### Local invocation (Windows)

The `.venv` in this repo has `taskforce-enterprise` installed, whose
auth middleware will 401 ~26 framework route tests. **Trust the delta
against `main`, not absolute local pass/fail**
(memory: `reference_enterprise_plugin_in_local_venv`).

Run tests against the local source (not the venv-installed package):

```powershell
$env:PYTHONPATH = "src;cli\src;$env:PYTHONPATH"
.\.venv\Scripts\python.exe -m pytest tests/unit/<area> -q --no-cov
```

### Skills for this step

| Skill | When to use |
|---|---|
| `/verify` | Run the app and observe real behaviour — for "does the fix actually work in the app?" beyond unit tests. |
| `/run-benchmark` | Performance benchmarks (for perf-tagged issues). |

---

## 6. Quality Gates — Pre-Commit

The PR template checklist (`.github/PULL_REQUEST_TEMPLATE.md`) requires:

```bash
uv run black .
uv run ruff check .
uv run mypy .            # if applicable to your area
uv run pytest
```

Plus: no secrets / PII; Clean Architecture compliance ticked.

### Skills for this step

| Skill | When to use |
|---|---|
| `/code-review` | Review changed code (reuse, quality, efficiency) and fix issues found. Useful before commit on larger diffs. |
| `/security-review` | Same as step 1 — also valuable here once changes are concrete. |
| `/review` | Review an existing PR end-to-end. |

---

## 7. Commit and Push — Branch Policy

| Change type | Branch policy |
|---|---|
| Small bugfix / improvement / test | **Direct to `main`** — no branch, no PR (memory: `feedback_direct_main_commit`) |
| User-requested feature bundle with passing tests | Same — direct to `main` is fine when the diff is coherent and tests are green |
| AutoOptim / `/evolve` runs | **Always on an experiment branch**, never `main`. Max 10 experiments per session. (Memories: `feedback_autooptim_workflow`, `feedback_evolve_workflow`) |
| Larger refactor / risky surgery | Branch + PR + review |

### CI-wait policy

For **mechanically trivial fixes** whose local tests pin the bug, merge
immediately — do not arm a Monitor on remote CI
(memory: `feedback_skip_ci_wait_when_local_green`).

### Worktree placement

Git worktrees go **at the same level as the repo directory**, not
inside it (memory: `feedback_worktree_location`):

```
C:\Users\rudi\source\
├── pytaskforce\            ← repo
├── pytaskforce-fix-123\    ← worktree, sibling
└── pytaskforce-evolve-a\   ← worktree, sibling
```

### Commit message trailer

End every commit message with:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

End PR bodies with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## 8. Documentation Upkeep (MANDATORY)

When code changes affect CLI / API / config / architecture, update the
docs **in the same session** (this is `CLAUDE.md`'s mandatory rule):

| Change type | Update these files |
|---|---|
| CLI behavior | `README.md`, `docs/cli.md` |
| API routes / schemas / errors | `README.md`, `docs/api.md` |
| Config / profile changes | `docs/profiles.md` |
| Architecture changes | `docs/architecture.md`, `docs/architecture/` |
| Cross-cutting decisions | New / updated ADR in `docs/adr/` |
| Spec contract | `docs/spec/<feature>.md` |
| Developer workflow | `README.md`, `docs/testing.md`, **this file** |
| Integrations | `docs/integrations.md` |
| Feature surfaces (memory, skills, …) | `docs/features/<page>.md` |

### Post-AutoOptim

After each AutoOptim session, update `docs/optimization-report.md` with
the results (memory: `feedback_optimization_report`).

### Skills for this step

| Skill | When to use |
|---|---|
| `/living-docs` | Render a long markdown doc as a polished single-file HTML viewer (sidebar TOC, search, Mermaid, dark mode). For specs / architecture / runbooks meant to be browsed. |
| `/llm-wiki` | Build / maintain an interlinked markdown wiki from sources (including code repos). For knowledge bases, not the daily cycle. |

---

## 9. CI Pipeline (`.github/workflows/ci.yml`)

Three jobs run on every push and PR:

1. **`test`**
   - `uv sync --locked`
   - `uv run pytest`
   - PowerShell-parses `dev.ps1` to catch syntax breakage
2. **`ui-test`**
   - Builds `packages/ui-shell` (gitignored `dist/`)
   - `npm ci` in `ui/`
   - `npm run typecheck` + `npm run test`
3. **`tag`** (only on the default branch)
   - Reads `version` from `pyproject.toml`
   - Computes the next `vMAJOR.MINOR.PATCH` tag (patch auto-increments)
   - Pushes the tag

---

## Skills Reference — Complete Map

| Phase | Skill | Purpose |
|---|---|---|
| 1. Find work | `/code-review-board` | Repo-wide review → board issues |
| 1. Find work | `/spec-check` | Spec drift detection |
| 1. Find work | `/security-review` | Targeted security review of branch |
| 4. Implement | `/init` | Bootstrap `CLAUDE.md` (one-off) |
| 4. Implement | `/run` | Launch the project's app |
| 5. Test | `/verify` | Run the app and observe behaviour |
| 5. Test | `/run-benchmark` | Perf benchmarks |
| 6. Pre-commit | `/code-review` | Review + fix changed code |
| 6. Pre-commit | `/review` | Review a PR |
| 8. Docs | `/living-docs` | Markdown → HTML viewer |
| 8. Docs | `/llm-wiki` | Wiki from sources |
| Optimization | `/evolve` | Evolutionary agent optimization (branches only) |
| Recurring | `/loop` | Run a prompt on an interval |
| Recurring | `/schedule` | Cron / one-time remote agent routines |
| Repo hygiene | `/fewer-permission-prompts` | Build a project allowlist from transcripts |
| Settings | `/update-config` | `settings.json` + hooks |
| Settings | `/keybindings-help` | Customise keyboard shortcuts |
| Meta | `skill-creator` | Create / benchmark / optimise skills |
| Stack-specific | `/claude-api` | Anthropic SDK work |

### BMAD layer — available but not active

The BMAD-Method roles (`/sm`, `/dev`, `/qa`, `/pm`, `/po`,
`/architect`, `/analyst`, `/ux-expert`, `/bmad-master`,
`/bmad-orchestrator`, `/sentinel`) and tasks (`/create-doc`,
`/shard-doc`, `/qa-gate`, `/review-story`, `/risk-profile`,
`/nfr-assess`, `/test-design`, `/trace-requirements`,
`/validate-next-story`, `/correct-course`, `/apply-qa-fixes`,
`/brownfield-create-epic`, `/brownfield-create-story`, …) are a
heavier alternative workflow with PRD / Story / Epic / QA-Gates. They
are **not** part of the current daily cycle (incompatible with the
feature freeze and the direct-to-main pattern) but remain available
for greenfield initiatives.

---

## Worked Example — How One Cycle Looked

The 2026-05-23 session that shipped conversations auto-title + rename
+ UI-delete (commit `fd7e6c1`, issues #431/#432/#433) followed this
exact pattern:

1. Goal received from user (3 capabilities)
2. Board checked → no items existed → manual gap → 3 issues created
3. `docs/spec/conversations.md` updated (Capabilities, Invariants, API
   surface, 6 `spec()` tags) — **before** touching code
4. Implemented across Protocol → Store → Manager → Route → CLI → UI,
   respecting the layer matrix
5. 14 new `@pytest.mark.spec()` tests written; 84/84 in scope green
6. `black`, `ruff` clean on touched files
7. Committed and pushed direct to `main` (`b14b263..fd7e6c1`)
8. CI picked it up automatically

---

## See Also

- `CLAUDE.md` — operational guardrails loaded into every Claude session
- `.github/PULL_REQUEST_TEMPLATE.md` — PR checklist (Clean Architecture
  compliance + quality gates)
- `docs/spec/README.md` — spec layer overview
- `docs/architecture.md` — Clean Architecture entry point
- `docs/adr/index.md` — Architecture Decision Records
- `docs/testing.md` — test strategy and conventions
