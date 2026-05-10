# ADR-025: Tool-result context isolation and content-filter recovery

**Status:** Accepted
**Date:** 2026-05-10

## Context

Multi-step research agents (web search → web fetch → synthesise) had
two failure modes that both traced back to the same root cause:
*tool-result snippets accumulating in the LLM message log across many
turns*.

1. **Token bloat** — Each `web_search` returned ~3–10 KB of raw snippet
   text, each `web_fetch` up to 5 KB of stripped HTML. After a few
   research rounds the message history had tens of thousands of
   characters of freeform text the agent had already conceptually
   used. The historical `TOOL_RESULT_STORE_THRESHOLD = 10_000` only
   spilled to the result store when a *single* result exceeded 10 KB,
   which almost never happened — so accumulation went unchecked.

2. **Provider content-filter triggers** — Azure OpenAI's safety
   classifier inspects the *whole* prompt context, not just the latest
   user turn. A benign "count ORF articles per day on the Iran-USA
   crisis" mission accumulated dozens of war / weapons / politics
   snippets across turns. Azure blocked the synthesis call with
   `ContentPolicyViolationError`. The existing recovery stripped
   `len(messages) → 3` (system + last 2 user/assistant) but *also*
   failed because the user's mission text itself carried the loaded
   framing.

The user-facing symptom was a hallucinated fallback message
("triggers Statistiken zu Körpermaßen, BMI") that did not match the
actual cause.

## Decision

Adopt a four-layer **context-engineering pipeline** for tool results
plus a **staged content-filter recovery** that gracefully degrades.

### 1. Per-tool `tool_result_store_threshold`

`BaseTool` exposes a class-level
`tool_result_store_threshold: int | None` (default `None`, i.e. fall
back to the framework default). The `ToolResultMessageFactory` looks
up the tool by name and prefers the per-tool override when set.

The framework default drops from `10_000` chars to `2_000` chars.
Tools that produce snippet-heavy or filter-prone content set their
own much lower thresholds:

| Tool | Per-tool threshold |
|------|---------------------|
| `web_search` | `800` |
| `web_fetch` | `1_500` |

The override is also profile-configurable: `agent.tool_result_store_threshold`
in YAML overrides the framework default for an entire agent.

### 2. Structured, neutral inline output for web tools

`WebSearchTool` returns `{title, url, snippet}` per result with the
snippet **truncated to a configurable preview** (default 160 chars,
`snippet_max_chars=0` drops snippets entirely). Full payloads land
in the `ToolResultStore` for on-demand retrieval via `fetch_result`.

`WebFetchTool` keeps its 5 KB content cap but the low per-tool
threshold sends nearly every fetch directly to the result store —
the agent calls `fetch_result` / `file_read` only when it actually
needs the body.

### 3. Role-aware hard caps in `MessageHistoryManager`

Before the existing LLM-summary compression, `MessageHistoryManager`
runs a deterministic `cap_oversized_messages` pass that hard-caps
individual messages by role:

* `tool_message_max_chars` (default 1500) — for `role="tool"` entries
* `assistant_message_max_chars` (default 4000) — for `role="assistant"`

Truncated messages get an explicit `[truncated N chars …]` marker.
Both caps are configurable via YAML (`agent.tool_message_max_chars`,
`agent.assistant_message_max_chars`) and passed through `LeanAgent`.

### 4. Staged content-filter recovery

`LiteLLMService.complete_stream` recovers from
`ContentPolicyViolationError` by retrying the call with progressively
more aggressive context stripping. Stages run in order; the first
successful one terminates the recovery:

1. **`tool_results_only`** — drop every `role="tool"` message and any
   assistant turn whose content is purely `tool_calls`. Cheapest
   stage; preserves multi-turn conversation flow.
2. **`aggressive`** — keep system prompt plus the last
   `recovery_keep_last_n` (default 2) plain user/assistant turns.
3. **`rephrase`** *(opt-in)* — when
   `LiteLLMService(recover_via_rephrase=True)`, run a small
   no-tools / no-streaming LLM call to neutralise the latest user
   turn ("Strip politically loaded, violent, or weapons-related
   framing. Preserve the actual information goal."), then re-stream
   the rebuilt messages once. Off by default — costs one extra small
   LLM call and rewrites the user's wording.

When all stages fail the recovery surfaces a clean
`error_kind=content_filter, non_retryable=True` event and the agent
emits a **factual** German user message that names accumulated
research context as the likely cause (no more BMI / Körpermaße
hallucination).

### 5. Research/Writer separation profile

`agents/butler/configs/custom/research_specialist.yaml` ships a
context-isolated research sub-agent with a strict JSON output
contract (`{summary, findings: [{date,title,url,fact}], stored_handles}`).
Master agents (Butler, Coding-Agent, custom orchestrators) reference
it as a `specialist:` and synthesise their final answer from the
structured payload — never from raw snippets.

Combined with point 1, this means a Butler delegating a research
mission inherits *zero* freeform snippet text in its own message
log: snippets stay inside the specialist's session and the
`ToolResultStore`.

## Consequences

### Positive

* **Smaller message logs.** A 5-round research session that used to
  carry ~20 KB of freeform text now carries <2 KB of structured
  references plus stored handles.
* **Filter blocks become recoverable.** Two cheap stripping stages
  catch most blocks; the opt-in rephrase stage handles the rare case
  where the mission text itself carries the trigger language.
* **Honest user messaging.** The fallback names the real cause
  (accumulated context) instead of a hallucinated topic.
* **Profile-level tuning.** Agents can tighten or loosen caps without
  touching framework code.

### Negative / risks

* **Lower default threshold (10 000 → 2 000) changes behaviour for
  any tool without an explicit override.** Tools whose payloads land
  between 2–10 KB will now spill to the result store. Mitigation:
  per-tool overrides for tools where this matters; the threshold is
  also configurable per profile.
* **The optional rephrase stage costs one extra small LLM call per
  filter trigger and changes the user's wording.** Off by default;
  operators must opt in explicitly.
* **`web_search` snippet output shape changed.** Snippets are now
  truncated. Tests and downstream consumers that depended on full
  snippet text need to either pass `snippet_max_chars=0` (strict
  structured output) or call `fetch_result` on the stored handle.

## Alternatives considered

* **Background context summariser running every N turns.** Higher
  LLM cost, no help against the content-filter trigger that already
  blocks the next call.
* **Filter-trigger keyword scrubbing on the message log.** Brittle
  and culture-dependent; the rephrase stage solves the same problem
  with the model's own paraphrase.
* **Eliminate the result store; always inline.** Works against the
  whole point — the message log is the wrong place for raw payloads.

## References

* Implementation:
  * `src/taskforce/core/domain/lean_agent_components/tool_executor.py`
  * `src/taskforce/core/domain/lean_agent_components/message_history_manager.py`
  * `src/taskforce/infrastructure/tools/native/web_tools.py`
  * `src/taskforce/infrastructure/llm/litellm_service.py`
  * `src/taskforce/core/domain/planning/react_loop.py`
* Profile: `agents/butler/configs/custom/research_specialist.yaml`
* Branch: `claude/improve-context-engineering-guFt1`
