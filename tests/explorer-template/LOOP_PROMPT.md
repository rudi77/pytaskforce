# /loop prompt

Paste this into Claude Code to start an exploration session.
**Substitute** `<BRANCH>` and `<PLAN_PATH>` / `<REPORT_PATH>` /
`<HARNESS_PATH>` with your copy's locations.

---

```
/loop Autonomous exploratory testing of <AGENT NAME> on branch <BRANCH>.

Per-iteration work:
1. Read <PLAN_PATH> → find next `[ ]` scenario.
2. Read <REPORT_PATH> to see which iteration number we're on (count completed blocks).
3. Write a short one-shot Python driver for the scenario. Import from <HARNESS_PATH> (provides make_fresh_env, send_message, db_query, run_scenario). Run it via `.venv/Scripts/python.exe` (or `.venv/bin/python` on POSIX).
4. Compare actual output vs the scenario's Expected section.
5. Append a full iteration block to <REPORT_PATH> using the template at the top of that file (Scenario, Env dir, What happened, Expected vs actual, Verdict, Root cause if fail, Fix, Nice-to-have).
6. Update the Findings summary table at the bottom of <REPORT_PATH>.
7. Resolution:
   - PASS: flip `[ ]` → `[x]` in <PLAN_PATH>. Commit BOTH updated files with message "Explorer iter N — S0x PASS" and push to <BRANCH>.
   - FAIL with a clear fix: make the minimal code fix. Run the unit-test suite (`PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/unit/ -q --no-cov`). If green, commit the fix separately ("Explorer iter N — fix: <short>"), then commit the plan+report update ("Explorer iter N — S0x PASS after fix"). Push both. Flip `[ ]` → `[x]`.
   - Architectural blocker: leave the checkbox, change it to `[!]`, write the question under "Open architectural questions" in <REPORT_PATH>, commit + push, STOP the loop (do not schedule next wakeup).

Termination conditions (STOP if any):
- All scenarios `[x]` or `[!]`.
- You've completed 15 iterations (count entries in <REPORT_PATH>).
- Any `[!]` appears in the plan.
- Soft-cap 50k tokens exceeded this iteration → finish current scenario then stop.

Self-pacing between iterations: 90-180 seconds (keep prompt cache warm, don't need longer pauses).

If something goes wrong (harness crashes, an upstream API returns 500, etc.) — record it as a finding in <REPORT_PATH> with verdict ⚠ INFRA, don't treat it as an agent bug, and move to the next scenario. If all scenarios fail due to infra, STOP after iteration 3 and flag the infra issue.

Rules you must follow:
- Only work on branch <BRANCH>. Never switch to main.
- Never force-push.
- Never delete tests or skip them silently; always record in the report.
- Don't add "niceties" to the code unprompted — fixes must trace back to a scenario failure.

Kick off by reading the plan and report now; then run the first unchecked scenario.
```

---

## Heads-up

- **LLM cost** — every iteration makes real LLM calls. Budget roughly
  €0.50–2 per full Round-1 run. Stop with Ctrl+C if you see iterations
  accumulate without finishing (rare, but possible).
- **Ctrl+C during the loop** — interrupts the current tool call but
  doesn't cancel the schedule. To fully stop, also issue `CronDelete`
  for the scheduled wakeup (Claude will tell you the job ID at
  start-up), or just close the Claude Code session.
- **Watch for `[!]`** — a blocker means the loop stopped and is
  waiting for your architectural decision. Resolve in the report, then
  /loop again to continue.
