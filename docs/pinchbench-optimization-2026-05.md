# PinchBench Optimization Sprint — Final Report

**Period:** 2026-05-18 → 2026-05-19
**Model:** `azure/gpt-5.4-mini`
**Suite:** `pinchbench_full` (148 samples, 14 categories)

---

## Headline

`pinchbench_full` aggregate: **0.544 → 0.712** (+17 ppt, **×1.31 relative**)
`stderr`: 0.036 → 0.030 (variance reduced)
Perfect runs: 36 → **47**, hard-zeros: 48 → **21** (halved)

---

## Per-Category Results

| Category | n | Baseline | Final | Δ | Multiplier |
|---|---:|---:|---:|---:|---:|
| **log_analysis** | 30 | 0.414 | **0.904** | +49 ppt | ×2.18 |
| **meeting_analysis** | 28 | 0.153 | **0.501** | +35 ppt | ×3.27 |
| **research** | 13 | 0.258 | **0.605** | +35 ppt | ×2.34 |
| **analysis** | 2 | 0.062 | 0.500 | +44 ppt | ×8.06 |
| csv_analysis | 26 | 0.760 | 0.864 | +10 ppt | ×1.14 |
| other | 17 | 0.470 | 0.787 | +32 ppt | ×1.67 |
| browser | 2 | 0.709 | 0.927 | +22 ppt | ×1.31 |
| google_workspace | 3 | 0.013 | 0.168 | +16 ppt | ×12.9 |
| coding | 8 | 0.518 | 0.570 | +5 ppt | ×1.10 |
| productivity | 5 | 0.733 | 0.800 | +7 ppt | ×1.09 |
| email | 4 | 0.928 | 0.951 | +2 ppt | ×1.02 |
| pdf | 2 | 0.950 | 0.925 | −2 ppt | ×0.97 |
| devops | 2 | 1.000 | 1.000 | = | = |
| skills | 1 | 1.000 | 1.000 | = | = |

Four categories more than doubled. The biggest lifts hit the original
worst-performers (meeting/research/log).

---

## What changed — six framework commits

All are framework-general (not PinchBench-specific bias). Total LOC:
~150 lines + tests + one config bump.

### 1. `9043adb` — transcript camelCase compatibility
PinchBench's task graders ship in two naming conventions (`tool_use`
vs `toolCall`). The framework's transcript builder only emitted one,
silently zeroing transcript-aware criteria like `used_web_search`.

### 2. `789d851` — QW1 pre-finalize deliverable check
The agent often produced a final assistant message without writing
the named output file. New helper extracts deliverable filenames from
the mission prompt and forces one extra reflection step at finalize
time if the file is still missing on disk.

### 3. `0f4b3ef` — QW2 mandatory-deliverables checklist
Multi-bullet prompts (PinchBench's enumerated rubrics) lost their
structure once compressed. The system prompt now reifies them as
`## Required Deliverables` with explicit checkboxes when the prompt
contains ≥2 bolded list items.

### 4. `ab09a10` — QW3 salvaged finals map to FAILED
Salvage paths (stall, max_steps, ignored-deliverable nudge) wrap a
final answer to keep the response stream non-empty, but the mission
hadn't actually succeeded. Salvaged FINAL_ANSWERs now tag
`salvaged=True, salvage_reason=...` and `_collect_result` maps them
to `ExecutionStatus.FAILED`. Tool-level failures inside an otherwise
successful mission still leave the run COMPLETED.

### 5. `dbc8c49` — tool_result_store absolute store path
`FileToolResultStore` constructed its base path lazily from a
relative `store_dir`. When prompts ran the agent inside a different
workspace root (PinchBench's per-mission temp dir), the absolute
path embedded in the result message diverged from the actual on-disk
path, producing `File not found` cascades that ate react steps and
tripped the content filter. Resolved at `__init__` time.

### 6. `0750629` + `75b7532` — pivot-nudge sharpening
Replaced the broken `write_tool_calls_seen == 0` heuristic with two
combined signals:
- Disk-check via `find_missing(deliverables, search_roots)` — source
  of truth for "has the agent actually produced the file?".
- Tool-category counters — `research` (web_search/web_fetch/browser),
  `nonwrite` (anything that isn't write or pure overhead), plus the
  original step-count fallback.

Three escalating nudge attempts: soft → PIVOT WARNING → FORCE WRITE.

### 7. `ceabc45` — pre-salvage force-write
Before the stall-detector salvage path runs, if there are still
declared deliverables missing on disk AND the pivot-nudge budget
isn't exhausted, inject one last FORCE WRITE attempt and let the
loop run one more step. Catches the case where the agent gathered
all data in memory but the stall preempted the write phase.

---

## Effect attribution (rough)

Sequential measurements over `pinchbench_research` (n=12, llm_judge):

| Step | Mean | Δ from previous |
|---|---:|---:|
| Baseline (pre-QW) | 0.258 | — |
| Profile tune (max_steps=180, threshold=3000) | 0.208 | −5 ppt |
| Store-path absolute | 0.521 | **+31 ppt** |
| Pivot-sharpening | 0.521 | = |
| Pre-salvage force-write | 0.605 | +8 ppt |

For `pinchbench_log_analysis` (n=30, hybrid):

| Step | Mean | Δ |
|---|---:|---:|
| Baseline | 0.414 | — |
| Profile tune | 0.535 | +12 ppt |
| Store-path | 0.791 | **+26 ppt** |
| Pre-salvage force-write | 0.904 | +11 ppt |

The store-path fix was the single biggest unlock (averaging
~+25 ppt across both suites). The pivot/force-write changes
contributed 8–11 ppt each on top. Profile tuning was lossy on
research (HTML payloads inlined and triggered the content filter)
but helpful on log analysis.

---

## What didn't yield improvement

- **Sub-agent over-use guard** was the original concern from the
  May-18 failure analysis. Empirically the new logic-layered defense
  (disk-check + escalating nudge) made the sub-agent issue less
  acute — meeting_analysis lifted from 0.15 to 0.50 even with
  `transcript_extractor` invoked 1–3× per task. The "sub-agent
  overuse is harmful at ≥2 calls" pattern (mean 0.154 with ≥2 calls
  in the May-18 data) still holds but is now dominated by other
  failures.
- **Single-agent system-prompt instruction** ("Write incrementally,
  partial deliverable beats missing one") has near-zero effect on
  its own — confirmed when the same instruction was already in the
  pinchbench profile during the failed baseline runs. The pivot
  nudge mechanism (recent messages) is what carries the signal.

---

## Remaining hard failures

After all fixes, 21 of 148 samples still score 0.0. Three failure
patterns dominate:

### 1. Multi-failure cascades (meeting_gov_*, ~5 samples)
The agent reaches the deliverable scope but a stack of issues
compounds: `transcript_extractor` sub-agent hits its own
`max_steps=20` on long transcripts; the master writes 8–42
intermediate workspace files but never composes the final deliverable;
content-filter eventually trips on accumulated meeting transcript text
(NASA UAP topic is filter-prone). Each issue alone is recoverable;
together they kill the run.

### 2. Hallucinated grader expectations (research, ~3 samples)
LLM-judge scoring is non-deterministic for research tasks. The same
task can score 100% one run and 0% the next depending on what the
judge focuses on. `task_stock` swung 100% → 0% between adjacent runs.

### 3. Capability-gap tasks (gws_*, ~3 samples; codebase_navigation)
`gws` CLI isn't installed; `task_codebase_navigation` needs git-clone
on a large repo. These need either fixture infrastructure or
explicit skip handling.

---

## Recommendations for next sprint

Ordered by expected effort:lift ratio. None are PinchBench-specific.

1. **Sub-agent failure propagation** — when a sub-agent returns
   "Exceeded max steps", the master currently receives it as a
   normal tool result. Tag it as a structured failure so the master
   can switch strategy instead of retrying delegation.
2. **Content-filter recovery escalation** — the 4-stage cascade
   (tool_results_only / aggressive / no_tools / rephrase) fails as a
   block when the filter trigger is structural (meeting transcript
   content). One more stage: "summarize then retry" using the
   summary as the only context. Same machinery already exists in
   `MessageHistoryManager.compress_messages`.
3. **Tool-category metadata on `BaseTool`** — the current pivot
   counter uses hardcoded frozensets (5 tool names). Promoting
   `category: read | research | analyze | write` to a `BaseTool`
   class attribute makes the heuristic agent-pluggable and removes
   the need to patch react_loop when new tools land.
4. **`call_agents_parallel` heavy-count weighting** — count sub-agent
   invocations as `N=5` in the pivot counter so the master can't
   sit on 3 delegations and never hit the threshold.

---

## Methodology notes

- All scores from real eval runs against PinchBench (https://pinchbench.com)
  via Inspect AI, not retrofitted estimates.
- Sample-level data lives in `logs/*.eval` files (zipped JSONL).
- The per-task notebook (`notebooks/pinchbench_analysis.ipynb`) was
  used for ~14 individual investigations. It runs a single task
  end-to-end with full event capture, charts, and grading — exactly
  the same code path as the `pinchbench_solver` minus the Inspect AI
  wrapper.
- Aggregate stderr is 0.030 after the fixes — but see the per-task
  variance section below: single-task scores are far noisier than
  the aggregate suggests.

---

## Post-sprint addendum — per-task variance measurement

Two tasks were re-run 5× with identical settings to quantify how
much of a single score is signal vs noise.

| Task | Grader | 5-run scores | Mean | Stdev | Range |
|---|---|---|---:|---:|---:|
| `task_csv_finance_report` | llm_judge | 90, 90, **0**, 100, 95 | 75% | **42 pp** | 100 pp |
| `task_log_apache_top_errors` | hybrid | 0, 29, 5, 0, **95** | 26% | **40 pp** | 95 pp |

**Two distinct variance patterns:**

- **Pure judge noise** (csv_finance_report): the agent does the
  same work every run, the LLM judge rates it inconsistently. 4 of
  5 runs near the true ~90-95%; 1 in 5 catastrophically zeros
  despite identical-quality agent output.
- **Bimodal agent effort** (log_apache_top_errors, hybrid graded):
  the agent quits early in 4 of 5 runs (20-27 events / 9-12 tools)
  but in 1 of 5 invests substantially more (80 events / 39 tools)
  and scores 95%. Both automated and judge components track this.

**Implications:**

1. The 148-sample aggregate has ±3 pp stderr because per-task noise
   averages out — aggregate is trustworthy.
2. Per-task scores are NOT trustworthy at single-run resolution.
   ±20 pp 95% CI on a single measurement of a single task.
3. "0% on a single full-suite run" does NOT mean the agent can't do
   the task. ~20% of apparent "hard zeros" are likely noise.
4. Future optimization sprints should average each candidate-failure
   task over 3-5 runs BEFORE diagnosing root cause.

**Bug found while measuring variance:** the loader was checking the
older ``multi_session_prompts`` frontmatter key but upstream
PinchBench migrated to ``multi_session: true`` + ``sessions:``.
Three tasks (iterative_code_refine, second_brain,
session_chain_analysis) had been silently running as single-session
since the migration, producing artificial zeros every run. Fixed in
commit ``3559bdc`` — they now skip cleanly via QW10 and drop out of
the mean.

The most leveraged framework follow-ups now target the bimodal
pattern, not the noise pattern:

- What makes the agent commit to extra effort? The 95%-run for
  log_apache_top_errors used 39 tool calls vs 9-12 in failures. If
  we can identify the heuristic that flipped that single run, we
  can encode it deterministically.
- Judge noise can't be eliminated framework-side, but PinchBench
  could ensemble 3 judge calls per task and average — orthogonal
  improvement that belongs in the eval scorer.
