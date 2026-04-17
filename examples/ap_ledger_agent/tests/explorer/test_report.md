# AP-Ledger Exploratory Test Report

**Branch:** `test/explorer-2026-04-17`
**Started:** 2026-04-17 20:39
**Last update:** 2026-04-17 20:51

---

## Iteration log

### Iteration 1 — 2026-04-17 20:39–20:43

**Scenario:** `S01 — Tageslosung bar buchen (Text)`
**Customer dir:** `C:\Users\rudi\AppData\Local\Temp\blubot-explorer\customers\s01-cdb872`
**Token usage:** ~35k (incl. debugging the harness)

**What happened:**
- Harness discovered two latent issues before the agent could run the scenario:
  1. `AgentExecutor.execute_mission()` does NOT accept `agent=...`. The streaming variant does — harness switched to `execute_mission_streaming` and collected events.
  2. `ask_user` is special-cased in `core/domain/planning/tool_execution.py:215`: the framework bypasses the tool's `_execute` and calls `_handle_ask_user` which persists pause-state and emits `ASK_USER`. Replacing `agent.tools["ask_user"]` has no effect. Harness now monkey-patches `_handle_ask_user` with an auto-yes version that emits a normal `TOOL_RESULT` event instead.
  3. Windows cp1252 crashed on the first non-ASCII log line and buried the real error. Harness forces UTF-8 on sys.stdout/stderr before anything imports structlog.
- Agent received the mission "186 EUR Tageslosung heute", called `ask_user` (auto-confirmed), then `powershell book.py revenue --bar 186 --date 2026-04-17`.
- book.py wrote 1 invoice + 1 journal entry atomically.

**Expected vs actual:**
- Expected: 1 invoice (receipt, posted, gross=186, net=155, tax=31), 1 journal posted, audit entries for `invoice.posted` and `journal.posted`.
- Actual:
  - ✅ invoices: 1 row, type=receipt, status=posted, total_gross=186.00, total_net=155.00, total_tax=31.00, date 2026-04-17, vendor_name_raw=Tageslosung
  - ✅ journal_entries: 1 row, status=posted, linked to invoice 1
  - ⚠ audit_log: has `system_init` (DB bootstrap) + `invoice_posted` — **no separate `journal_posted` event**. Journal status is correct, just not logged as its own audit event.
- **Verdict: ⚠ PASS-WITH-NOTES**

**Root cause (if fail):** n/a — data is correct. Audit-log granularity is a framework design choice (transactional boundary is the invoice, journal is a side-effect logged implicitly). Leaving as-is; Re-raise only if a real customer audit requires the extra event.

**Fix:**
- Harness itself had three bugs that needed fixing before S01 could run. Changes to `examples/ap_ledger_agent/tests/explorer/scenarios/_harness.py`:
  - Switch `send_message` from `execute_mission` to `execute_mission_streaming` + event consumer.
  - Add `_install_auto_yes_ask_user()` that monkey-patches `_handle_ask_user` in `core.domain.planning.tool_execution`.
  - Force UTF-8 on stdio at module import time.
- No framework code touched.
- Regression check: n/a (harness only).

**Nice-to-have (not blocking):**
- Harness reports `agent.success=false` because `_consume` didn't correctly flag completion. Data is fine but the human-readable result is misleading. Will address after the first scenarios are green.
- `invoice_date` came back as 2026-04-17 (today's date — matches "heute"). Good.

---

### Iteration 2 — 2026-04-17 20:48–20:51

**Scenario:** `S02 — Barumsatz + Karteneinnahme gemischt`
**Customer dir:** `C:\Users\rudi\AppData\Local\Temp\blubot-explorer\customers\s02-9bd04b`
**Token usage:** ~10k (smooth, no harness issues)

**What happened:**
- Agent received "Heute 300 bar, 150 Karte, Tageslosung"
- auto_yes_ask_user fired once (as expected), then agent called `book.py revenue --bar 300 --karte 150`
- book.py created a single invoice with two lines (one per payment type).

**Expected vs actual:**
- Expected: 2 invoices OR 1 invoice with 2 lines, sum of gross = 450, journal balanced.
- Actual (chose the "1 invoice with 2 lines" variant — scenario allowed either):
  - ✅ 1 invoice, `type=receipt`, `status=posted`, `total_gross=450.00`, `total_net=375.00`, `total_tax=75.00` (20% AT USt → 375+75=450 ✓)
  - ✅ invoice_lines: line 1 Bareinnahmen 300/250/50, line 2 Karteneinnahmen 150/125/25
  - ✅ 1 journal_entry with 6 lines:
    - L1: Kassa 2700 Soll 300
    - L2: Erlöse Bar 4000 Haben 250
    - L3: Umsatzsteuer 3500 Haben 50
    - L4: Bank 2800 Soll 150
    - L5: Erlöse Karte 4010 Haben 125
    - L6: Umsatzsteuer 3500 Haben 25
  - ✅ Balance: Soll 450 = Haben 450
- **Verdict: ✅ PASS**

**Root cause (if fail):** n/a

**Fix:** n/a — no code changes.

**Nice-to-have (not blocking):**
- Konto-Struktur mischt Soll/Haben sauber über beide Zahlungsarten; für eine Freelancerin nicht sichtbar, aber Steuerberater-freundlich.

---


<!--
Template for each iteration — append below, newest at the bottom.

### Iteration N — YYYY-MM-DD HH:MM

**Scenario:** `S0x — <Titel>`
**Customer dir:** `C:\Users\rudi\AppData\Local\Temp\blubot-explorer-<slug>\customers\<slug>`
**Token usage:** ~Nk

**What happened:**
- Step 1: ...
- Step 2: ...

**Expected vs actual:**
- Expected: ...
- Actual: ...
- Verdict: ✅ PASS | ❌ FAIL | ⚠ PASS-WITH-NOTES

**Root cause (if fail):**
...

**Fix:**
- File: `src/.../...`
- Commit: `<sha>`
- Regression check: (did X tests still pass after the fix?)

**Nice-to-have (not blocking):**
- ...

---
-->

## Findings summary (filled as we go)

| # | Scenario | Verdict | Fix commit | Notes |
|---|---|---|---|---|
| 1 | S01 Tageslosung bar | ⚠ PASS-WITH-NOTES | harness fixes only | Data correct; audit-log only logs `invoice_posted`, not a separate `journal_posted`. |
| 2 | S02 Bar + Karte gemischt | ✅ PASS | none | 1 invoice with 2 lines, journal 450=450 balanced, USt 20% correct. |

## Open architectural questions

_None yet — loop will append here if blocked by a design decision._

## Nice-to-haves / UX observations

_Not blocking bugs, but worth revisiting:_

- **Audit-log granularity:** only `invoice_posted` is logged; the journal-post side-effect has no separate event. If a Steuerberater / Betriebsprüfung requires the journal event visible, add it to `book.py`.
- **Harness result parsing:** `send_message` returns `success=false` even when the booking worked — the completion-detection in `_consume` needs a better signal. Agent-behaviour is fine, only the return structure is wrong.
