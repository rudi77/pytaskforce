# AutoOptim Experiment History
Persistent log of all experiments across campaigns and runs.
The proposer uses this to avoid repeating failed approaches.

## Campaign: butler-quality (2026-03-22 14:12 UTC)

- ⚠️ **Exp #8** [config] **ERROR** (-0.8781)
  - **Change:** Configure the scheduler block explicitly in butler.yaml so reminder/schedule tools stop failing due to missing scheduler configuration.
  - **Hypothesis:** The only broken mission is the reminder task, and the trace shows both reminder and schedule fail with the same root cause: "Scheduler not configured." Since notifications are already 0 and baseline/s
  - **Files:** src/taskforce/configs/butler.yaml
  - **Composite:** 0.0000 (baseline: 0.8781)

- ❌ **Exp #9** [prompt] **DISCARDED** (-0.1457)
  - **Change:** Revise the Butler specialist prompt so reminder/calendar/email tasks are handled by Butler directly, delegation is only used for true file/web/doc/code work, and Butler responds immediately after sufficient tool output.
  - **Hypothesis:** The only clearly broken mission is reminder_completed=0, while notification_spam is already 0, so the highest-value prompt experiment is to fix routing/ownership confusion for reminders. The current s
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Composite:** 0.7324 (baseline: 0.8781)

- ❌ **Exp #10** [prompt] **DISCARDED** (-0.0910)
  - **Change:** Tighten Butler delegation rules for local filesystem tasks and add a strong 'no ask-user after successful delegation' synthesis rule.
  - **Hypothesis:** The trace shows Butler is incorrectly refusing/delegating filesystem-heavy inspection tasks: Document Report fails in 1 step by asking the user for access instead of delegating, and Dateiverwaltung fa
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Composite:** 0.7871 (baseline: 0.8781)

