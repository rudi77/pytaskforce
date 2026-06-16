# Agent-Loop Profiling — Where the time actually goes

**Status:** measurement complete (Deliverable 1).
**Harness:** `tests/benchmarks/profile_agent_loop.py`
**Method:** scripted N-step ReAct mission against a deterministic, zero-latency
mock LLM (injected by patching `InfrastructureBuilder.build_llm_provider`), so
the measured wall-clock is *pure framework overhead*. cProfile gives
function-level attribution; an fsod-style ~15-line loop driving the same mock +
the same real tool is the baseline. No production code was changed to measure.

Reproduce:

```bash
uv run python tests/benchmarks/profile_agent_loop.py --steps 10 --runs 3
uv run python tests/benchmarks/profile_agent_loop.py --steps 5 --latency 1.2
TASKFORCE_WORKSPACE_ROOT=$(pwd) uv run python tests/benchmarks/profile_agent_loop.py --steps 10
# logs go to stdout; pipe through: | grep -vE '^\s*20[0-9]{2}-'  to see only the report
```

## Headline

**The ReAct loop's per-step CPU overhead is NOT the problem.** Measured at
**~1.7 ms per step** (≈1 ms between tool calls), it is ~0.1 % of a single real
LLM round-trip (~1.2 s). The perceived slowness comes from three other places,
in priority order:

1. **Cold process startup: ~1.5–1.8 s** on every `taskforce chat` / `taskforce run`.
2. **The number of LLM round-trips** the framework adds (nudges, stall-salvage,
   compression, post-mission learning) — each is a full ~1 s+ call.
3. **Prompt size sent on every call** — ~5.6 k tokens of system prompt + 16 tool
   schemas before any conversation, vs the fsod loop's tiny prompt.

## Measured numbers (profile=`default`, 10 steps, mock LLM, zero latency)

| Metric | Value | Notes |
|---|---|---|
| COLD build (first agent in a fresh process) | **~1550 ms** | tool imports + plugin discovery + profile YAML |
| WARM build (subsequent agents in same process) | ~5.3 ms | classes already imported |
| RUN, 10 steps / 11 LLM calls | ~18 ms | total framework CPU for the whole loop |
| **per-step framework CPU** | **~1.7 ms** | run / llm_calls |
| fsod-style baseline (same 10 steps, same tool) | ~0.4 ms | minimal loop + dispatch |
| **framework overhead over minimal loop** | **~18 ms total (~1.8 ms/step)** | the cost of all the machinery |
| With `--latency 1.2` (realistic TTFT) | per-step ≈ 1204.6 ms | framework adds ~1.7 ms ≈ **0.14 %** |

### cProfile hotspots (one run, cumulative)

- `profile_loader.load` → `yaml.safe_load` ≈ **22 ms** — the profile YAML is
  parsed **twice** per build and is the single largest CPU item.
- structlog `_proxy_to_logger` / `_process_event` ≈ **14 ms** across the run —
  logging is *more* expensive than `prepare_for_llm`. At DEBUG it is far worse.
- `context_manager.prepare_for_llm` ≈ **9 ms for 11 calls (~0.8 ms each)** — the
  per-step prep we suspected is cheap, because its sections are cache-keyed.
- `_run_post_mission_learning` ≈ **12 ms** even when it no-ops.

## What the measurements confirm / refute

- **Refuted:** per-step `prepare_for_llm` (system-prompt rebuild, token
  estimation, message capping) is a hotspot. The section caches in
  `prompt_builder.py` and the `id()`-keyed token cache make it ~0.8 ms/call.
- **Refuted (CPU-wise):** the big CLAUDE.md / WORKSPACE injection adds per-step
  CPU. With `TASKFORCE_WORKSPACE_ROOT` set, RUN was 18.5 ms vs 18.2 ms — the
  workspace section is cached by `(root, mtime)`. **But** it still inflates the
  *prompt bytes sent on every call*, which only shows up as latency/cost against
  a real provider (not in this zero-latency harness).
- **Confirmed:** cold startup dominates first-response latency (~1.5–1.8 s).
- **Confirmed:** the framework readily adds extra LLM round-trips. In an early
  run where each scripted step repeated an identical tool call, the
  repeat/stall detector fired `repeat_file_read_nudge` → `pre_stall_nudge` →
  `react_loop_stalled` → **2 salvage LLM calls**, ending the mission at step 3.
  Real missions with legitimately similar steps can pay the same tax.

## Ranked optimization candidates (gated — to be done as separate surgical PRs)

Highest payoff first; each should ship with a test and be re-measured with this
harness.

1. **Cut cold startup (~1.5 s).** Biggest single user-facing win for CLI.
   - Lazy-import heavy tool modules (Playwright/`browser`, `git`, office tools)
     so building a default agent doesn't import everything up front.
   - Cache / single-parse the profile YAML (parsed twice today).
   - *Files:* `application/tool_builder.py`, `infrastructure/tools/registry.py`,
     `application/profile_loader.py`, `application/factory.py`.
2. **Reduce LLM round-trips.** Each avoided call saves ~1 s+.
   - Make the nudge / circuit-breaker / pre-stall / salvage machinery less
     trigger-happy (tighten thresholds; don't salvage on benign repetition).
   - Confirm post-mission learning / compression only run when they add value.
   - *Files:* `core/domain/planning/react_loop.py`,
     `application/learning_service.py`, `message_history_manager.py`.
3. **Shrink the per-call prompt** (latency + cost on real providers).
   - ~5.6 k tokens of system prompt + 16 tool schemas are sent on **every**
     call. Consider trimming the default tool set, shortening tool schemas, and
     not re-sending the full static CLAUDE.md each turn (rely on provider prompt
     caching / a once-only system turn).
   - *Files:* `prompt_builder.py`, `configs/default.yaml` (tool list),
     tool `parameters_schema` definitions.
4. **Lower logging overhead** on the hot path (INFO→structured-but-cheaper, or
   gate the chatty per-step `debug`/`info` events). Minor but free.

## Notes / limitations

- The harness isolates **framework CPU**; it deliberately removes network/model
  latency. Items 2–3 above are about *reducing the count and size of real LLM
  calls*, which this harness models via `--latency` and the round-trip count,
  not by calling a real provider.
- Streaming is the path all real entrypoints use (`hasattr(provider,
  "complete_stream")`); `--no-stream` exists for comparison.
