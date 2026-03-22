# Butler Agent Optimization Report

**Started:** 2026-03-22
**Method:** AutoOptim (LLM-driven iterative optimization)
**Benchmark:** Butler Benchmark Suite (efficiency, quality, memory missions)

---

## Optimization Session 1 — 2026-03-22

### Baseline (before optimization)

Daily Benchmark (9 missions), measured at 10:27 UTC:

| Mission | Steps | Tokens | Tools | Wall | Quality | Completed |
|---------|------:|-------:|------:|-----:|--------:|:---------:|
| Baseline | 1 | 3,496 | 0 | 8.9s | - | ✅ |
| Single Tool | 2 | 5,971 | 0 | 14.6s | - | ✅ |
| Doc Report | 13 | 120,239 | 17 | 364.6s | - | ✅ |
| Multi-Step | 3 | 10,313 | 1 | 18.5s | - | ✅ |
| Tagesplanung | 2 | 8,049 | 2 | 47.8s | 0.2 | ✅ |
| Dateiverwaltung | 12 | 249,201 | 62 | 570.1s | 0.7 | ✅ |
| Recherche | 5 | 33,765 | 11 | 132.1s | 0.2 | ✅ |
| Erinnerung | 3 | 10,996 | 2 | 44.3s | 0.6 | ✅ |
| Präferenz | 3 | 10,893 | 2 | 19.5s | 1.0 | ✅ |

**Aggregates:** task_completion=1.0 | answer_quality=0.54 | avg_steps=4.9 | avg_tokens=50,325 | avg_wall=135.6s

### Changes Applied

#### 1. PC-Agent Prompt Optimization (Efficiency Campaign, Exp #1)

**Source:** AutoOptim efficiency campaign, KEPT (+37.6% composite)
**File:** `src/taskforce/configs/custom/pc-agent.yaml`
**Commit:** `72822a4`

**Problem:** PC-Agent used PowerShell trial-and-error for simple file reads (e.g., reading `pyproject.toml` via `Get-Content` instead of `file_read`), causing unnecessary steps and token overhead.

**Change:** Added explicit tool selection hierarchy to PC-Agent system prompt:
- `file_read` first for known single files (not PowerShell)
- No trial-and-error sequences when the task is clear
- One-pass directory scans instead of multiple follow-up queries
- No planning for simple 1-2 tool call tasks
- Compact result format (only requested information)

**Impact on efficiency missions:**

| Metric | Before | After | Change |
|--------|-------:|------:|:-------|
| Doc Report Wall | 364.6s | 84.2s | **-77%** |
| Multi-Step Wall | 18.5s | 5.9s | **-68%** |
| Total Wall (4 missions) | 406.6s | 101.6s | **-75%** |

#### 2. Butler max_steps Increase (Quality Campaign, Exp #5)

**Source:** AutoOptim quality campaign, KEPT (+21.1% composite)
**File:** `src/taskforce/configs/butler.yaml`
**Commit:** `8a84acb`

**Problem:** Butler with `max_steps: 12` would stall prematurely when tool calls failed (e.g., reminder tool without scheduler backend), leaving no room for fallback behavior.

**Change:** Increased `max_steps` from 12 to 16.

**Impact:** Reminder mission and other tasks with recoverable failures now complete instead of stalling.

### Summary of Improvements

| Metric | Before | After | Change |
|--------|-------:|------:|:-------|
| Efficiency composite | 1.0000 | 1.3762 | **+37.6%** |
| Doc Report Wall | 364.6s | 84.2s | **-77%** |
| Total Wall (4 efficiency missions) | 406.6s | 101.6s | **-75%** |
| task_completion | 1.0 | 1.0 | maintained |
| notification_spam | 0 | 0 | maintained |

### Experiments Attempted but Discarded

| Category | Attempts | Discarded | Key Learnings |
|----------|:--------:|:---------:|---------------|
| Butler prompt (delegation rules) | 6 | 6 | Changing Butler coordinator prompt consistently regresses singletool or docreport; delegation behavior is already well-tuned |
| Config (max_step_iterations) | 1 | 1 | Reducing from 3→2 broke docreport completion |
| Config (context_policy) | 3 | 3 | Tightening context limits breaks sub-agent result visibility |
| Config (max_steps increase to 16) | 1 | 1 | In efficiency campaign, extra steps added overhead without benefit |
| Code (planning_strategy hooks) | 2 | 2 | Preflight failures on Windows; approach too invasive |

### Infrastructure Fixes (same session)

| Fix | Files Changed | Impact |
|-----|:------------:|--------|
| UTF-8 encoding audit | 34 locations | Eliminated all Windows charmap codec errors |
| AutoOptim eval_mode routing | runner.py | Custom modes (daily, memory) now work correctly |
| Baseline inflation fix | runner.py | Full-eval validation now reverts inflated baselines |
| Quality grading fix | eval_butler.py | answer_quality was always 0.0 due to complete_json wrapper |
| Per-mission timeout | eval_butler.py | Single slow mission no longer kills entire eval |
| Runner crash handling | runner.py | Unexpected errors skip experiment instead of crashing run |
| Preflight env fix | base.py | Windows asyncio import works in code mutator preflight |
| Persistent experiment history | runner.py | Proposer sees all past experiments across runs |
| Stable TSV log | runner.py | Campaign-based log path survives crashes |
| Campaign system | 3 new configs | Focused optimization (efficiency, quality, memory) |

---

## Planned Next Steps

- [ ] Memory campaign — evaluate and optimize recall, fact retention, contradiction handling
- [ ] Quality campaign re-run — with scheduler whitelist fix and autonomous_prompts.py blocked
- [ ] Extract prompts from .py to .md files — enable safe prompt mutation by text mutator
