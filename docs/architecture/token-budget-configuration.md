# Token Budget Configuration

**Story:** 9.3 - TokenBudgeter + Safe Compression  
**Date:** 2025-12-13  
**Status:** Implemented

## Overview

The TokenBudgeter provides budget management for prompt length to prevent "input tokens exceed limit" errors. It uses heuristic token estimation and enforces hard caps on message content.

## Default Budget Settings

### Token Limits

| Setting | Default Value | Description |
|---------|--------------|-------------|
| `max_input_tokens` | 100,000 | Maximum input tokens allowed for LLM calls |
| `compression_trigger` | 80,000 | Token count that triggers message compression (80% of max) |

### Content Caps (Safety Limits)

| Setting | Default Value | Description |
|---------|--------------|-------------|
| `MAX_MESSAGE_CONTENT_CHARS` | 50,000 | Maximum characters per message content (~12.5k tokens) |
| `MAX_TOOL_OUTPUT_CHARS` | 20,000 | Maximum characters per tool output preview (~5k tokens) |
| `MAX_CONTEXT_PACK_CHARS` | 10,000 | Maximum characters for context pack (~2.5k tokens) |

### Heuristic Constants

| Setting | Value | Description |
|---------|-------|-------------|
| `CHARS_PER_TOKEN` | 4 | Conservative estimate (real: 3-5 chars per token) |
| `MESSAGE_OVERHEAD_TOKENS` | 10 | Per message overhead (role, structure) |
| `TOOL_SCHEMA_OVERHEAD_TOKENS` | 50 | Per tool definition overhead |
| `SYSTEM_PROMPT_OVERHEAD_TOKENS` | 100 | System prompt structure overhead |

## Token Estimation Formula

```python
total_tokens = (
    SYSTEM_PROMPT_OVERHEAD_TOKENS +
    sum(MESSAGE_OVERHEAD_TOKENS + len(content) / CHARS_PER_TOKEN for each message) +
    sum(TOOL_SCHEMA_OVERHEAD_TOKENS + len(schema) / CHARS_PER_TOKEN for each tool) +
    len(context_pack) / CHARS_PER_TOKEN
)
```

## Compression Behavior

### Budget-Based Trigger (Primary)

Compression is triggered when:
```python
estimated_tokens > compression_trigger  # Default: 80,000
```

### Message Count Trigger (Fallback)

For backward compatibility, compression also triggers when:
```python
message_count > SUMMARY_THRESHOLD  # Default: 20 messages
```

### Safe Compression Process

1. **Extract old messages** (skip system prompt)
2. **Build safe summary input** using `_build_safe_summary_input()`:
   - Extracts message role and sanitized content (max 1000 chars)
   - For tool calls: extracts tool names only (not full arguments)
   - For tool results: creates previews (not raw outputs)
3. **Call LLM** to create summary
4. **Replace old messages** with summary + keep recent messages
5. **Fallback**: If LLM fails, keep system prompt + recent messages only

## Preflight Budget Check

Before each LLM call, `_preflight_budget_check()` runs:

1. **Check budget**: If `estimated_tokens <= max_input_tokens`, proceed
2. **Emergency sanitization**: If over budget, sanitize all message content
3. **Emergency truncation**: If still over budget, keep only system prompt + last 10 messages

## Configuration

### LeanAgent Initialization

```python
agent = LeanAgent(
    state_manager=state_manager,
    llm_provider=llm_provider,
    tools=tools,
    max_input_tokens=100000,      # Optional: override default
    compression_trigger=80000,     # Optional: override default
)
```

### TokenBudgeter Direct Usage

```python
from taskforce.core.domain.token_budgeter import TokenBudgeter

budgeter = TokenBudgeter(
    max_input_tokens=50000,
    compression_trigger=40000,
)

# Check if over budget
if budgeter.is_over_budget(messages, tools, context_pack):
    # Handle overflow

# Check if compression recommended
if budgeter.should_compress(messages, tools, context_pack):
    # Trigger compression

# Sanitize individual message
sanitized = budgeter.sanitize_message(message, max_chars=10000)

# Get budget statistics
stats = budgeter.get_budget_stats(messages, tools, context_pack)
```

## Rationale for Defaults

### Why 100k tokens max?

- GPT-4 Turbo: 128k context window
- GPT-4: 8k-32k context window
- 100k provides safety margin for output tokens and system overhead
- Conservative default works across most models

### Why 80k compression trigger?

- Triggers at 80% of max budget
- Provides buffer before hitting hard limit
- Allows room for context pack and tool schemas

### Why 50k chars per message?

- ~12.5k tokens per message
- Prevents single message from dominating prompt
- Allows multiple large messages before compression

### Why 20k chars per tool output?

- ~5k tokens per tool result
- Balances context preservation with budget constraints
- Large enough for substantial outputs, small enough to prevent overflow

## Monitoring

Use `get_budget_stats()` for diagnostics:

```python
stats = agent.token_budgeter.get_budget_stats(messages, tools, context_pack)

print(f"Estimated tokens: {stats['estimated_tokens']}")
print(f"Remaining tokens: {stats['remaining_tokens']}")
print(f"Utilization: {stats['utilization_percent']}%")
print(f"Over budget: {stats['over_budget']}")
print(f"Should compress: {stats['should_compress']}")
```

## Testing

- **Unit tests**: `tests/unit/core/test_token_budgeter.py` (23 tests)
- **Integration tests**: `tests/unit/core/test_safe_compression.py` (11 tests)
- **Regression tests**: All existing LeanAgent tests pass (222 total)

## Related Files

- Implementation: `taskforce/src/taskforce/core/domain/token_budgeter.py`
- Integration: `taskforce/src/taskforce/core/domain/lean_agent.py`
- Tests: `taskforce/tests/unit/core/test_token_budgeter.py`
- Tests: `taskforce/tests/unit/core/test_safe_compression.py`

