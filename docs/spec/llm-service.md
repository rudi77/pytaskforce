---
feature: llm-service
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
---

# LiteLLM Service

The provider-agnostic LLM service powering every model call in the framework.
Operators configure short aliases (`main`, `fast`, `powerful`, …) in
`llm_config.yaml` and the service routes them to OpenAI, Anthropic, Azure
OpenAI, Google Gemini, Ollama, or any LiteLLM-supported provider based on the
mapped model string's prefix. Both blocking (`complete`) and streaming
(`complete_stream`) calls are first-class; both apply default + per-model
parameters, both report token usage, and both classify provider exceptions as
retryable or terminal so transient failures don't leak to the agent.

## Capabilities (what the operator / agent can do)

- map short aliases (`main`, `fast`, `powerful`, …) to concrete provider model strings via `llm_config.yaml`
- switch provider per alias by changing the model-string prefix (`anthropic/`, `azure/`, `gemini/`, `ollama/`, `openai/`) — no code change
- set per-model defaults (`temperature`, `max_tokens`, `reasoning_effort`, …) under `model_params` and have them merged with caller kwargs
- call the LLM blocking via `complete()` and get one normalized result dict, or streaming via `complete_stream()` and get a typed event stream
- pass OpenAI-format `tools` + `tool_choice` to either call style and receive structured tool-call output (assembled progressively when streaming)
- request JSON-formatted output via `complete_json()`, which parses the response and returns `{success, data}` or a structured parse-error dict
- consume native Microsoft `AZURE_OPENAI_*` env vars transparently (auto-mapped to LiteLLM's `AZURE_API_*` names at import time)
- get automatic retry with exponential backoff for transient errors (rate limits, timeouts, 5xx) without writing retry code at the call site

## Invariants (what must always be true)

- Provider exceptions are never raised to the caller of `complete()`: they are returned as `{success: false, error, error_type, model}`. Streaming surfaces them as `{type: "error", message, ...}` events instead of raising.
- Every successful `complete()` result carries `success`, `content` (or `null`), `tool_calls` (or `null`), `usage`, `model`, `actual_model`, and `latency_ms`.
- Every `complete_stream()` consumer sees exactly one terminal event per attempt — either `done` (success) or `error` (failure). Tool calls arrive as a `tool_call_start` followed by zero or more `tool_call_delta` events and one `tool_call_end`.
- `tool_call_start` is emitted as soon as either an `id` or `name` is known for that index, even if the provider front-loads arguments before metadata — otherwise the consumer would drop every subsequent delta and the tool would silently never run.
- HTTP 401, 402, 403, 404, 410 and the auth/quota phrase set (`invalid api key`, `authentication`, `unauthorized`, `permission denied`, `insufficient_quota`, `quota exceeded`, `invalid model`, `invalid request`) are classified non-retryable and fail immediately — they never burn the retry budget.
- Retry backoff is `backoff_multiplier ** attempt` (deterministic; see Known gaps re: jitter).
- The retry loop runs at most `retry_policy.max_attempts` attempts per call; once exhausted the call fails terminally even if the error was retryable.
- The streaming path enforces a per-chunk timeout equal to `retry_policy.timeout`; a mid-stream stall yields an `error` event with a "Stream timed out … between chunks" message instead of hanging indefinitely.
- Model alias resolution falls through: an unknown alias is passed straight to LiteLLM as a literal model string (so `complete(model="anthropic/claude-haiku-4-5")` works without an entry in `models:`).
- A successful call logs the provider-reported `actual_model` alongside the requested model; a mismatch (after stripping provider prefix and version suffix) emits an `llm_response.model_mismatch` warning but does not fail the call.
- `complete_stream()` yields a `done` event whose `usage` dict reflects what the provider sent — empty `{}` if the provider didn't include usage on the final chunk.

## Configuration surface (the YAML keys + env vars operators rely on)

`llm_config.yaml` (path configurable via the service constructor; framework default `src/taskforce/configs/llm_config.yaml`):

- `default_model: <alias>` — alias used when a caller passes `model=None`
- `models: { alias: "<litellm-model-string>" }` — required, must contain at least one entry; provider determined by the model string prefix
- `model_params: { key: { … } }` — per-model parameter overrides. Key match order: exact alias → exact resolved model → bare model name (prefix stripped) → longest-prefix match on resolved → longest-prefix match on bare
- `default_params: { … }` — parameters applied to every call before model-specific overrides and caller kwargs
- `retry: { max_attempts: int=3, backoff_multiplier: float=2.0, timeout: int=60 }` — also accepted under legacy key `retry_policy`
- `logging.log_token_usage: bool` (default `true`) — emit per-call token/latency log lines
- `tracing.enabled: bool` (default `false`), `tracing.mode: file|phoenix|both`, `tracing.file_config.path` — JSONL trace destination

Environment variables (read natively by LiteLLM per provider; the service does not parse them itself):

- `OPENAI_API_KEY` — OpenAI (no model prefix)
- `ANTHROPIC_API_KEY` — `anthropic/…` models
- `GEMINI_API_KEY` — `gemini/…` models
- `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` — `azure/…` models (LiteLLM convention)
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` — auto-mapped at module import to the `AZURE_*` names above (Microsoft convention)

## Event stream contract (`complete_stream`)

Events are members of `LLMStreamEventType` in `core/domain/enums.py`:

- `TOKEN` — `{type: "token", content: str}` — a chunk of assistant text
- `TOOL_CALL_START` — `{type, id, name, index}` — fired exactly once per tool-call index as soon as id or name is known
- `TOOL_CALL_DELTA` — `{type, id, arguments_delta, index}` — one or more per tool call, carrying argument-string fragments
- `TOOL_CALL_END` — `{type, id, name, arguments, index}` — emitted once per tool call when the provider signals `finish_reason`
- `DONE` — `{type, usage}` — always the last event on success; `usage` may be `{}` if the provider didn't report it
- `STREAM_RESTART` — `{type, reason, stage}` — emitted before a content-filter recovery retry; consumers must drop tokens accumulated since the previous `STREAM_RESTART` (or stream start). See `content-filter-recovery.md` for the recovery cascade.

An `error` event terminates the stream and carries `{type, message}` plus, when classifiable, `error_kind` and `non_retryable=True`.

## Tests (must exist and pass)

- spec("llm-service.complete_returns_error_dict_on_provider_exception")
- spec("llm-service.complete_stream_yields_error_event_not_exception")
- spec("llm-service.retry_exponential_backoff_until_max_attempts")
- spec("llm-service.auth_errors_are_non_retryable")
- spec("llm-service.transient_5xx_with_4xx_in_body_stays_retryable")
- spec("llm-service.model_alias_resolves_via_models_map")
- spec("llm-service.unknown_alias_passes_through_as_literal_model")
- spec("llm-service.model_params_merge_order_default_then_model_then_kwargs")
- spec("llm-service.azure_openai_env_vars_are_auto_mapped")
- spec("llm-service.stream_tool_call_start_emits_after_id_or_name_known")
- spec("llm-service.stream_chunk_timeout_yields_error_event")
- spec("llm-service.complete_json_returns_parsed_data_on_success")
- spec("llm-service.complete_json_returns_parse_error_on_invalid_json")
- spec("llm-service.usage_dict_present_on_successful_complete")

## Known gaps

- **Tiktoken estimator hard-fails on unknown model encodings.** The token estimator does not fall back to `cl100k_base` when LiteLLM returns a model whose encoding tiktoken doesn't know, so token-budget code paths can raise for new models. Tracked in #323.
- **Trace writes are fire-and-forget `asyncio.create_task`.** Streaming success/failure traces are scheduled without being awaited; if the event loop closes before they run, traces are silently lost. Tracked in #324.
- **Retry exception filter still uses a bare `except`-style classification in some legacy paths.** `_should_retry` correctly narrows transient vs. terminal errors, but a few call sites in higher layers swallow unrelated exceptions before reaching the classifier. Tracked in #326.
- **`LLMConfigLoader` is not race-safe on first async load.** Two concurrent `await llm.complete(...)` calls against a freshly constructed service can both enter `load_config_async`. The sync fallback in `__init__` makes this benign in practice (config is already loaded by the time async paths see it), but the async path itself has no lock. Tracked in #354.
- **`RetryPolicy` backoff has no jitter.** `backoff_multiplier ** attempt` is deterministic, so concurrent clients retrying after a shared 429 will all wake up at the same wall-clock time and hammer the provider in lock-step. Tracked in #355.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section asserts the target, not the current state. Spec-check will flag every marker as "asserted but missing test" on first run.

## Cross-references

- related_spec: llm-router.md (per-call model selection via phase hints, layered on top of this service)
- related_spec: content-filter-recovery.md (the multi-stage recovery cascade triggered from `complete()` / `complete_stream()`)
- related_spec: react-loop.md (consumer of `complete_stream` events; translates `STREAM_RESTART` into `LLM_STREAM_RESTART`)
- related_spec: context-manager.md (builds the `messages` list passed in)
- adr: ADR-012 (Dynamic LLM Selection)
- adr: ADR-025 (Tool-result context isolation + content-filter recovery)
- docs: CLAUDE.md → "LLM Integration" + `src/taskforce/configs/llm_config.yaml` (worked example)
