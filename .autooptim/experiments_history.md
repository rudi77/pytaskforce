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

## Campaign: butler-dateiverwaltung (2026-03-22 15:47 UTC)

- ⚠️ **Exp #10** [prompt] **ERROR** (-0.5000)
  - **Change:** Tighten Butler specialist prompt to enforce single-shot delegation, correct filesystem-vs-document routing, and immediate synthesis after first usable sub-agent result.
  - **Hypothesis:** The trace shows the largest prompt-fixable efficiency loss is Butler's delegation wording and retry behavior on file tasks: Single Tool needlessly delegated twice with PowerShell-centric wording, and
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Composite:** 0.0000 (baseline: 0.5000)

## Campaign: evolve-session-1 (2026-03-22 21:36 UTC)

Method: /evolve skill (Teacher-Student evolutionary optimization with 3-worktree tournament)

### Cycle 1 — tool_usage: precise value extraction (3 experiments)

- ❌ **Variant A** [prompt] **DISCARDED** (answer correct but tokens worse)
  - **Change:** Butler prompt — craft precise delegation missions ("extract `version` field from `[project]` section")
  - **Hypothesis:** Butler forwards user prompt verbatim, pc-agent extracts wrong field (target-version instead of version)
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** Answer correct "0.1.0", but tokens UP 18,388 (baseline 16,359), wall 25.7s

- ✅ **Variant B** [prompt] **WINNER — MERGED** (answer fixed, tokens reduced)
  - **Change:** PC-agent prompt — add "precise value extraction" rule to distinguish similar fields in config files
  - **Hypothesis:** PC-agent needs explicit guidance to parse TOML/YAML carefully and find the exact requested field
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** Answer correct "0.1.0" (was "py311"), steps 2 (was 3), tokens 14,140 (was 16,359), wall 18.4s
  - **Commit:** f115c85

- ❌ **Variant C** [prompt] **DISCARDED** (regression — Butler refused to act)
  - **Change:** Combined A+B (Butler precise delegation + PC-agent extraction rule)
  - **Hypothesis:** Both changes together should compound the improvement
  - **Files:** autonomous_prompts.py + pc-agent.yaml
  - **Result:** Butler refused to act, asked user to upload file. Combined prompt changes confused the model.

### Cycle 2 — efficiency: Single Tool token reduction (3 experiments)

- ❌ **Variant A** [prompt] **DISCARDED** (marginal)
  - **Change:** PC-agent — force file_read over PowerShell for single known files
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** 14,039 tokens, 9.3s wall. Correct answer. Marginal improvement over baseline 14,140.

- ❌ **Variant B** [config] **DISCARDED** (no effect)
  - **Change:** PC-agent max_steps 20 → 10
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** 14,101 tokens, 10.2s wall. No measurable effect — agent already finishes in 2 steps.

- ❌ **Variant C** [prompt] **DISCARDED** (marginal)
  - **Change:** Butler — concise delegation without tool-specific instructions
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** 14,114 tokens, 14.8s wall. Marginal.

**Conclusion:** ~14k tokens is the structural floor for delegation pattern on this mission.

### Cycle 3 — efficiency: Document Report optimization (3 experiments)

- ❌ **Variant A** [prompt] **DISCARDED** (tokens worse)
  - **Change:** PC-agent — stronger PowerShell one-scan emphasis with example command
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** 30,455 tokens (baseline 22,884), 111s wall. Tokens went UP.

- ❌ **Variant B** [prompt] **DISCARDED** (tokens worse, quality better)
  - **Change:** Butler — explicit output format in delegation (Markdown table)
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** 29,952 tokens, 109s wall. Better output quality (table format) but more tokens.

- ❌ **Variant C** [prompt] **DISCARDED** (FAILED)
  - **Change:** PC-agent — Python-first report pattern with pathlib example
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** Butler tried Google Drive instead of delegating. FAILED.

**Conclusion:** DocReport ~22-30k tokens is inherent complexity (scanning 1200+ files). Not prompt-fixable.

