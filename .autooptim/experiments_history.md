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

## Campaign: evolve-session-2 (2026-03-23 06:46 UTC)

Method: /evolve skill (Teacher-Student evolutionary optimization with 3-worktree tournament)
Branch: experiments/evolve-session-2

### Cycle 1 — delegation reliability: file access refusal + activate_skill overhead (3 experiments)

- ✅ **Variant B** [prompt] **WINNER — MERGED** (fixes activate_skill overhead)
  - **Change:** Butler prompt — "Your FIRST tool call must be call_agents_parallel — nothing else before it"
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** Correct delegation, no activate_skill before delegation
  - **Commit:** baafb45

- ✅ **Variant A** [prompt] **RECOMBINED** (fixes file access refusal)
  - **Change:** Butler prompt — "You CAN access local files via pc-agent. NEVER refuse."
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** Butler delegates instead of refusing. Answer "0.1.0" correct.
  - **Commit:** c4829b1

- ❌ **Variant C** [prompt] **DISCARDED** (combined A+B as "CRITICAL" section)
  - **Result:** All 3 delegated correctly, but C had highest tokens (14,348). No advantage over separate A+B.

### Cycle 2 — multi_source quality: Tagesplanung answer quality (3 experiments)

- ✅ **Variant A** [prompt] **WINNER — MERGED** (quality 0.1 → 0.4)
  - **Change:** Butler output style — structured Kalender/E-Mails/Prioritäten template for multi-source answers
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** Quality 0.4 (4x improvement), structured output with 3 clear sections
  - **Commit:** cdfa370

- ❌ **Variant B** [prompt] **DISCARDED** (CRASHED)
  - **Change:** Butler — "Antworte in der Sprache des Benutzers"
  - **Result:** Butler delegated to research_agent instead of using direct tools. Timed out.

- ❌ **Variant C** [prompt] **DISCARDED** (quality unchanged)
  - **Change:** Butler — explicit "Daily planning" task pattern
  - **Result:** Quality 0.1 (unchanged despite good-looking answer). Fewest tokens (9,830).

### Cycle 3 — delegation efficiency: Recherche re-delegation (3 experiments)

- ✅ **Variant C** [prompt] **WINNER — MERGED** (tokens -14%, no re-delegation)
  - **Change:** Butler — specify exact output format in research delegation
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** 20,832 tokens (was 24,179), single delegation, 5 numbered points with Relevanz
  - **Commit:** 8c21589

- ✅ **Variant B** [config] **RECOMBINED** (research agent efficiency)
  - **Change:** Research agent — max 3 tool calls per task
  - **Files:** src/taskforce/configs/custom/research_agent.yaml
  - **Result:** 39,562 tokens (still re-delegated but research agent more focused)
  - **Commit:** d6d7faf

- ❌ **Variant A** [prompt] **DISCARDED** (tokens 3.5x worse)
  - **Change:** Research agent — briefing output template
  - **Result:** 84,392 tokens. Butler re-delegated ("Ergänze..."), doubling work.

### Infrastructure fixes

- **fix:** Memory benchmark error/timeout dicts missing fields (22b01fe)
- **refactor:** Removed automated LLM quality judge — /evolve Teacher acts as Judge directly (a852228)

### Memory Benchmark Baseline (established, not optimized)

| Sequence | Recall | Steps | Tokens |
|----------|:------:|------:|-------:|
| Preference Recall | PASS | 14 | 70,966 |
| Fact Retention | FAIL | 13 | 83,480 |
| Contradiction Handling | PASS | 14 | 87,847 |
| Memory Search | FAIL | 20 | 90,786 |
| Proactive Suggestion | FAIL | 8 | 35,923 |
| **Total** | **40%** | **69** | **369,002** |

### Iteration 4 — PC-Agent: Deterministisches DocReport Pattern (3 experiments)

- ✅ **Variant B** [prompt] **WINNER — MERGED** (tokens stabilized)
  - **Change:** PC-Agent — deterministic Python/pathlib pattern for directory scans
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** 21,504 tokens (baseline was 14k-112k variance). Consistent.
  - **Commit:** 39ee6cc

- ❌ **Variant A** [prompt] **DISCARDED** (good but slightly more tokens)
  - **Change:** PC-Agent — explicit 2-step PowerShell pattern
  - **Result:** 23,748 tokens, 84s. Good but not best.

- ❌ **Variant C** [config+prompt] **DISCARDED** (no improvement)
  - **Change:** max_steps 20→8 + error handling rule
  - **Result:** 32,333 tokens, 201s. TimeoutException still occurred.

### Iteration 5 — Diverse Mission Testing (3 experiments, same code)

Tested Top10-Files, Space-Usage, PDF-List missions on current code:
- **Top10 (21k tok, 42s):** PASS — perfect table
- **Space (15k tok, 47s):** PASS — correct 2.3GB, Top 5 folders
- **PDF-List (46k tok, 115s):** PARTIAL — Butler re-delegated 3x (identified as re-delegation problem)

### Iteration 6 — Butler Re-Delegation Fix (3 experiments)

- ✅ **Variant C** [prompt] **WINNER — MERGED** (re-delegation eliminated)
  - **Change:** Butler — "Include ALL requirements in one comprehensive mission. No second delegation."
  - **Files:** src/taskforce/core/prompts/autonomous_prompts.py
  - **Result:** PDF-List: 1 delegation, 20,321 tokens (was 46,351 with 3 delegations). -57%.
  - **Commit:** 6a7d782

- ❌ **Variant A** [prompt] **DISCARDED** (works but too strict)
  - **Change:** "EXACTLY ONE call_agents_parallel per task. No exceptions."
  - **Result:** 21,513 tokens. Works but may be too restrictive for complex tasks.

- ❌ **Variant B** [prompt] **DISCARDED** (works but less principled)
  - **Change:** "If result covers most of the question, that is good enough."
  - **Result:** 21,291 tokens. Similar to C but less sustainable approach.

### Iteration 7 — Advanced Mission Testing (3 experiments, same code)

Tested harder missions (cross-source, multi-agent, reasoning):
- **Wochenübersicht (10k tok, 46s):** PASS — calendar+gmail parallel, structured synthesis
- **Meeting-Vorbereitung (8.5k tok, 21s):** PASS — calendar+email, honest "no email from Peter"
- **PDF-Katalog cross-agent (FAILED):** PC-Agent stalled on PDF parsing error → react_loop_stalled

### Iteration 8 — PC-Agent Error Recovery (3 experiments)

- ✅ **Variant A** [prompt] **WINNER — MERGED** (fixes stalling)
  - **Change:** PC-Agent — "On tool failure: answer IMMEDIATELY with partial results. Do NOT retry."
  - **Files:** src/taskforce/configs/custom/pc-agent.yaml
  - **Result:** PDF-Katalog now completes: 24,826 tokens, 87s. Cross-agent (pc+research) parallel works.
  - **Commit:** f5aa83d

- Not tested: Variants B (no-PDF-content rule) and C (explicit error chain) — Variant A already fixed the problem.

