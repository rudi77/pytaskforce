# Exploratory Test Suite — AP-Ledger Agent

This is **not** a pytest suite. It's a living test plan that Claude works
through autonomously in a `/loop`: execute a scenario → record result →
fix bugs found → commit + push → next scenario.

> **Note:** this directory is a concrete instance of the reusable
> template under `tests/explorer-template/`. If you want to run the
> same pattern against a different agent, copy that template to the
> agent's tree and implement the single agent-specific function
> (`make_fresh_env`). The AP-Ledger harness here is a worked example.

## Layout

| File | Purpose |
|---|---|
| `test_plan.md` | Living plan — scenarios as a checklist. Claude appends new ones as the suite matures. |
| `test_report.md` | Append-only findings journal. Every iteration adds an entry. |
| `scenarios/_harness.py` | Python helpers: fresh customer, send-message-to-agent, DB query. |
| `fixtures/` | Sample receipt images / PDFs for vision-path tests. |

## Running the loop (human-initiated)

From a Claude Code session:

```
/loop Work through examples/ap_ledger_agent/tests/explorer/test_plan.md,
record in test_report.md, fix bugs on the current branch, stop at 15
iterations or when the plan is complete.
```

Claude self-paces the iteration cadence and stops at the first
architectural question it can't resolve alone.

## Design constraints

- **Real LLM calls** — no mocking of the agent's reasoning.
- **Isolated state** — every scenario provisions a fresh customer in a
  temp dir; no shared state between tests.
- **Branch-only work** — fixes land on the exploration branch, never
  directly on `main`. User reviews the eventual PR.
- **Token budget** — soft cap ~50k tokens per iteration, hard cap ~500k
  across the whole loop. If exceeded, Claude stops and reports.
- **Architectural changes stop the loop** — if a finding needs a
  design decision, Claude halts and writes a clear question into the
  report.

## Adding a new scenario manually

Append to `test_plan.md`:

```markdown
- [ ] **S09 — <Kurztitel>** — <1-Satz Szenario-Beschreibung>
  **Setup:** `fresh customer, country: AT`
  **Steps:** 1) send `"..."` 2) ...
  **Expected:** `invoices.count == 1, total_gross == 186`
```

The `[ ]` is the checklist marker — Claude flips to `[x]` when done.
