# Add LLM Interaction Tracing - Brownfield Addition

Status: Ready for Review

## User Story

As a Developer,
I want to trace all communications with the LLM (requests and responses),
So that I can debug issues, analyze token usage, and audit agent behavior either via local files or Arize Phoenix.

## Story Context

**Existing System Integration:**

- Integrates with: `OpenAIService` in `taskforce/infrastructure/llm/openai_service.py`
- Technology: Python, Arize Phoenix (optional), File I/O
- Follows pattern: Decorator or Middleware pattern for interception
- Touch points: `OpenAIService.complete` and `OpenAIService.generate` methods

## Acceptance Criteria

**Functional Requirements:**

1. Implement a tracing mechanism that captures:
   - Timestamp
   - Model used
   - Full prompt/messages (input)
   - Full response (output)
   - Token usage stats
   - Latency
2. Support File-based Tracing:
   - Write traces to a local JSONL file (configurable path)
   - Append mode to keep history
3. Support Arize Phoenix Tracing:
   - Integrate with Arize Phoenix using their OpenTelemetry or SDK if configured
   - Allow toggling via configuration (enabled/disabled)
4. Configuration:
   - Allow enabling/disabling tracing in `configs/llm_config.yaml`
   - Allow selecting trace mode: `file`, `phoenix`, or `both`

**Integration Requirements:**
5. Existing `OpenAIService` continues to work unchanged for consumers
6. New functionality follows existing configuration pattern
7. Integration with `litellm` remains stable

**Quality Requirements:**
8. Change is covered by appropriate tests (mocking external services)
9. Documentation is updated (config options)
10. No regression in existing functionality verified

## Tasks

- [x] Update configuration in `llm_config.yaml` to support tracing options (`enabled`, `mode`, `file_path`, `phoenix_endpoint`)
- [x] Implement File-based tracing logic in `OpenAIService`
- [x] Implement Arize Phoenix tracing integration in `OpenAIService`
- [x] Add `_trace_interaction` method to `OpenAIService` and integrate into `complete`
- [x] Add unit tests for tracing logic (mocking file IO and Phoenix)
- [x] Verify integration and graceful failure of Phoenix

## File List

- taskforce/src/taskforce/infrastructure/llm/openai_service.py
- taskforce/configs/llm_config.yaml
- taskforce/tests/unit/infrastructure/test_llm_service.py

## Technical Notes

- **Integration Approach:**
  - Modify `OpenAIService` to include a private `_trace_interaction` method.
  - Call `_trace_interaction` in `complete` (and `generate` if it doesn't call `complete` internally, but it does).
  - Use `phoenix.trace.openai` or similar if using the Phoenix SDK directly, or manual instrumentation if using `litellm`'s callbacks.
  - Ensure the tracing is non-blocking or lightweight to avoid impacting latency significantly.

- **Existing Pattern Reference:**
  - Similar to how `logging` is currently handled in `OpenAIService`.

- **Key Constraints:**
  - Must handle cases where Arize Phoenix is not installed or not reachable gracefully.
  - File writing should be async or fast enough.

## Definition of Done

- [x] Functional requirements met
- [x] Integration requirements verified
- [x] Existing functionality regression tested
- [x] Code follows existing patterns and standards
- [x] Tests pass (existing and new)
- [x] Documentation updated if applicable

