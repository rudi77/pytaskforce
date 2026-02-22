# ADR-012: Dynamic LLM Selection per Agent Step

**Status:** Accepted (Approach 3 implemented)
**Date:** 2026-02-22
**Deciders:** Team
**Context:** Taskforce multi-agent orchestration framework

---

## Context and Problem Statement

Currently, each Taskforce agent uses a **single model alias** (`agent.model_alias`) for all LLM calls during its entire execution. This alias is set at agent creation time via profile YAML (`llm.default_model`) and never changes.

This means a complex reasoning step (e.g., architectural planning) uses the same model as a simple step (e.g., summarizing a tool output). This is wasteful: strong reasoning models are expensive and slow, while many agent steps only need basic text generation.

**Goal:** Allow agents to use different LLMs for different purposes — strong models for complex reasoning, fast/cheap models for simple tasks — while keeping the implementation simple and aligned with the existing architecture.

### Current Architecture (What We Have)

| Component | Role | Key File |
|-----------|------|----------|
| `LLMProviderProtocol` | Accepts optional `model` alias per call | `core/interfaces/llm.py` |
| `LiteLLMService` | Resolves aliases → model strings, merges params | `infrastructure/llm/litellm_service.py` |
| `llm_config.yaml` | Defines alias→model mapping (`main`, `fast`, `powerful`) | `configs/llm_config.yaml` |
| `Agent.model_alias` | Single alias used for ALL calls | `core/domain/lean_agent.py:132` |
| `PlanningStrategy` | Calls `agent.llm_provider.complete(model=agent.model_alias)` | `core/domain/planning_strategy.py` |
| `AutoEpicConfig.classifier_model` | Already supports per-task model override | `core/domain/config_schema.py:232` |

**Key insight:** The `LLMProviderProtocol.complete()` method already accepts a `model` parameter per call. The `LiteLLMService` already resolves aliases and merges per-model params. The infrastructure for multi-model is already in place — we just need to tell the agent _when_ to use _which_ alias.

---

## Three Proposed Approaches

### Approach 1: Model Role Map (Config-Driven, Minimal Code Change)

**Idea:** Add a `model_roles` dictionary to the profile YAML that maps operation types to model aliases. The agent picks the appropriate alias based on what it's doing right now.

#### Configuration

```yaml
# Profile YAML
llm:
  config_path: src/taskforce_extensions/configs/llm_config.yaml
  default_model: main          # fallback for unmapped roles

  # NEW: role-based model mapping
  model_roles:
    planning: powerful          # Plan generation, task decomposition
    reasoning: powerful         # Complex ReAct reasoning steps (with tools)
    acting: fast                # Simple tool-calling steps
    reflecting: powerful        # SPAR reflect phase, self-critique
    summarizing: fast           # Final answer synthesis, compression
```

The `llm_config.yaml` aliases remain as-is:
```yaml
models:
  main: "azure/gpt-4.1"
  fast: "azure/gpt-4.1-mini"
  powerful: "azure/gpt-5.0-mini"
  local: "ollama/llama3"
```

#### Code Changes

1. **Agent receives `model_roles: dict[str, str]`** alongside `model_alias`:

```python
# core/domain/lean_agent.py
class Agent:
    def __init__(self, ..., model_alias: str = "main",
                 model_roles: dict[str, str] | None = None):
        self.model_alias = model_alias
        self.model_roles = model_roles or {}

    def resolve_model(self, role: str = "reasoning") -> str:
        """Return the model alias for a given operation role."""
        return self.model_roles.get(role, self.model_alias)
```

2. **Planning strategies use `agent.resolve_model(role)`** instead of `agent.model_alias`:

```python
# In planning_strategy.py

# _generate_plan(): planning phase
result = await agent.llm_provider.complete(
    messages=..., model=agent.resolve_model("planning"), ...
)

# NativeReActStrategy main loop: reasoning + acting
result = await agent.llm_provider.complete(
    messages=..., model=agent.resolve_model("reasoning"), ...
)

# _stream_final_response(): summarizing phase
async for chunk in agent.llm_provider.complete_stream(
    messages=..., model=agent.resolve_model("summarizing"), ...
)

# _run_reflection_cycle(): reflection phase
result = await agent.llm_provider.complete(
    messages=..., model=agent.resolve_model("reflecting"), ...
)
```

3. **Factory wires `model_roles`** from profile config:

```python
# application/factory.py
model_roles = llm_config.get("model_roles", {})
agent = Agent(..., model_alias=model_alias, model_roles=model_roles)
```

#### Reused Components

- `LiteLLMService._resolve_model()` — already resolves aliases to model strings
- `LiteLLMService._get_params()` — already merges per-model parameters
- `llm_config.yaml` alias system — just add more aliases
- Profile YAML loading — just read one more dict key

#### Pros and Cons

| Pros | Cons |
|------|------|
| Minimal code change (~30 lines in agent, ~15 lines in strategies, ~5 in factory) | Static mapping — can't adapt to input complexity at runtime |
| Fully config-driven, no code change to switch models | Must define roles upfront — new role types need code |
| Backward-compatible (empty `model_roles` = current behavior) | Doesn't distinguish "hard reasoning" from "easy reasoning" |
| Aligns with existing alias system | All calls in a phase use same model regardless of actual difficulty |
| Easy to understand and debug | — |

#### Complexity: **Low**

---

### Approach 2: Strategy-Aware Model Selection (Per-Phase in Planning Strategies)

**Idea:** Each `PlanningStrategy` defines which model to use for each of its phases. The SPAR strategy is the best fit since it already has explicit Sense → Plan → Act → Reflect phases. Strategies receive a `ModelSelector` that encapsulates the selection logic.

#### Configuration

```yaml
# Profile YAML
agent:
  planning_strategy: spar
  planning_strategy_params:
    max_step_iterations: 3
    reflect_every_step: true

    # NEW: per-phase model overrides
    phase_models:
      sense: fast            # Initial mission analysis
      plan: powerful         # Task decomposition
      act: main              # Tool-calling execution
      reflect: powerful      # Self-critique and validation
      final_answer: fast     # Summary generation
```

#### Code Changes

1. **New `ModelSelector` dataclass** (in `core/domain/`):

```python
# core/domain/model_selector.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ModelSelector:
    """Selects LLM model alias based on execution phase."""

    default: str = "main"
    phase_models: dict[str, str] = field(default_factory=dict)

    def for_phase(self, phase: str) -> str:
        """Return model alias for given phase, falling back to default."""
        return self.phase_models.get(phase, self.default)
```

2. **Planning strategies accept `ModelSelector`:**

```python
# core/domain/planning_strategy.py
class SparStrategy:
    def __init__(self, ..., model_selector: ModelSelector | None = None):
        self.model_selector = model_selector or ModelSelector()

    async def execute_stream(self, agent, mission, session_id):
        # Plan phase
        plan = await _generate_plan(
            agent, mission, logger,
            model_override=self.model_selector.for_phase("plan")
        )
        # Act phase
        result = await agent.llm_provider.complete(
            messages=...,
            model=self.model_selector.for_phase("act"),
            tools=agent._openai_tools, ...
        )
        # Reflect phase
        result = await agent.llm_provider.complete(
            messages=...,
            model=self.model_selector.for_phase("reflect"),
            tools=agent._openai_tools, ...
        )
```

3. **Factory builds `ModelSelector`** from strategy params and passes to strategy:

```python
# application/factory.py
phase_models = strategy_params.pop("phase_models", {})
model_selector = ModelSelector(default=model_alias, phase_models=phase_models)
strategy = SparStrategy(..., model_selector=model_selector)
```

#### Reused Components

- `LiteLLMService` — fully reused, just receives different aliases per call
- `PlanningStrategy` pattern — strategies already encapsulate phase logic
- Profile YAML `planning_strategy_params` — already supports arbitrary params
- Factory strategy construction — already builds strategies from params

#### Pros and Cons

| Pros | Cons |
|------|------|
| Natural fit for SPAR's explicit phases | Strategies that don't have explicit phases (NativeReAct) benefit less |
| Configuration lives alongside strategy params (cohesive) | Each strategy needs its own phase vocabulary |
| `ModelSelector` is a clean, testable abstraction | Slightly more code than Approach 1 (~50 lines new class + ~40 in strategies) |
| Can override per strategy independently | Still static — doesn't adapt to input complexity |
| No changes to Agent class needed | Need to thread `model_override` through shared helpers like `_generate_plan` |

#### Complexity: **Low–Medium**

---

### Approach 3: LLM Router Wrapper (Adaptive, Runtime Decision)

**Idea:** Introduce a lightweight `LLMRouter` that wraps `LLMProviderProtocol` and makes per-call model decisions based on context signals (message count, tool presence, explicit hints). The router itself implements `LLMProviderProtocol`, so it's a drop-in replacement — the agent and strategies don't change at all.

#### Configuration

```yaml
# Profile YAML
llm:
  config_path: src/taskforce_extensions/configs/llm_config.yaml
  default_model: main

  # NEW: routing rules
  routing:
    enabled: true
    rules:
      # Use powerful model when tools are provided (reasoning about which tool)
      - condition: has_tools
        model: powerful
      # Use fast model for no-tool calls (summaries, final answers)
      - condition: no_tools
        model: fast
      # Use powerful for long conversations (complex multi-step)
      - condition: message_count > 10
        model: powerful
      # Explicit hint from strategy
      - condition: hint:planning
        model: powerful
      - condition: hint:summarizing
        model: fast
```

#### Code Changes

1. **New `LLMRouter`** (in `infrastructure/llm/`):

```python
# infrastructure/llm/llm_router.py
from dataclasses import dataclass
from taskforce.core.interfaces.llm import LLMProviderProtocol

@dataclass
class RoutingRule:
    condition: str  # "has_tools", "no_tools", "message_count > N", "hint:X"
    model: str      # alias to use when condition matches

class LLMRouter:
    """Routes LLM calls to different models based on context.

    Wraps an existing LLMProviderProtocol and overrides model selection
    based on configurable rules. Implements LLMProviderProtocol itself,
    so it's a transparent drop-in.
    """

    def __init__(self, delegate: LLMProviderProtocol, rules: list[RoutingRule],
                 default_model: str = "main"):
        self._delegate = delegate
        self._rules = rules
        self._default = default_model

    def _select_model(self, model_hint: str | None, messages: list,
                      tools: list | None) -> str:
        """Evaluate rules and return the best model alias."""
        for rule in self._rules:
            if rule.condition == "has_tools" and tools:
                return rule.model
            if rule.condition == "no_tools" and not tools:
                return rule.model
            if rule.condition.startswith("message_count"):
                threshold = int(rule.condition.split(">")[1].strip())
                if len(messages) > threshold:
                    return rule.model
            if rule.condition.startswith("hint:"):
                hint = rule.condition.split(":")[1]
                if model_hint == hint:
                    return rule.model
        return model_hint or self._default

    async def complete(self, messages, model=None, tools=None, **kwargs):
        resolved = self._select_model(model, messages, tools)
        return await self._delegate.complete(messages, model=resolved,
                                              tools=tools, **kwargs)

    async def generate(self, prompt, context=None, model=None, **kwargs):
        return await self._delegate.generate(prompt, context, model, **kwargs)

    async def complete_stream(self, messages, model=None, tools=None, **kwargs):
        resolved = self._select_model(model, messages, tools)
        async for chunk in self._delegate.complete_stream(
            messages, model=resolved, tools=tools, **kwargs
        ):
            yield chunk
```

2. **Factory wraps `LiteLLMService` with `LLMRouter`** when routing is configured:

```python
# application/factory.py (or infrastructure_builder.py)
routing_config = llm_config.get("routing", {})
if routing_config.get("enabled"):
    rules = [RoutingRule(**r) for r in routing_config.get("rules", [])]
    llm_provider = LLMRouter(delegate=llm_provider, rules=rules,
                             default_model=model_alias)
```

3. **Strategies can pass hints** via the existing `model` parameter:

```python
# planning_strategy.py — no structural changes needed
# _generate_plan: pass hint
result = await agent.llm_provider.complete(
    messages=..., model="planning", ...  # "planning" is a hint, not an alias
)
# The router intercepts "planning" and maps it via rules
```

#### Reused Components

- `LLMProviderProtocol` — router implements same protocol (transparent wrapper)
- `LiteLLMService` — fully delegated to, no changes
- Factory wiring — just wrap the provider
- Profile YAML — just add a `routing` section

#### Pros and Cons

| Pros | Cons |
|------|------|
| Agent and strategies need zero changes (transparent wrapper) | Rule evaluation adds small overhead per call |
| Can make runtime decisions based on actual context | Rule language needs careful design to stay simple |
| Rules are configurable without code changes | Debugging which model was selected requires logging |
| Extensible — new conditions easy to add | More moving parts than Approach 1 |
| Hint-based approach works with any strategy | "has_tools" heuristic may not always correlate with complexity |
| Follows Decorator pattern (clean composition) | Slightly more complex to test (wrapper + delegate) |

#### Complexity: **Medium**

---

## Comparison Matrix

| Criterion | Approach 1: Model Role Map | Approach 2: Strategy-Aware | Approach 3: LLM Router |
|-----------|---------------------------|---------------------------|------------------------|
| **Code changes** | ~50 lines | ~90 lines | ~120 lines |
| **Files modified** | 3 (agent, strategies, factory) | 4 (new class, strategies, factory, config_schema) | 2 (new class, factory) |
| **Agent changes** | Add `model_roles` + `resolve_model()` | None | None |
| **Strategy changes** | Replace `agent.model_alias` refs | Add `model_selector` param, use per-phase | None (can optionally pass hints) |
| **Backward compat** | Full (empty dict = no change) | Full (no selector = no change) | Full (routing disabled = no change) |
| **Config location** | `llm.model_roles` in profile | `planning_strategy_params.phase_models` | `llm.routing` in profile |
| **Adaptivity** | Static per role | Static per phase | Runtime based on context |
| **Testability** | Simple (dict lookup) | Simple (dataclass method) | Medium (mock delegate) |
| **Best for** | Simple role separation | SPAR/PlanAndExecute users | Power users wanting smart routing |

---

## Recommendation

**Start with Approach 1 (Model Role Map)** for the initial implementation. It provides the highest value for the lowest complexity:

1. It covers the primary use case (strong model for reasoning, fast model for simple tasks)
2. It requires minimal code changes and is easy to understand
3. It's fully backward-compatible
4. It reuses all existing infrastructure (alias system, param merging, provider abstraction)

**Approach 2** is a natural evolution if SPAR becomes the primary strategy — the `ModelSelector` can be introduced later and coexist with Approach 1.

**Approach 3** can be added as an opt-in power feature later. Since it wraps the provider transparently, it can be layered on top of either Approach 1 or 2 without conflict.

### Phased Rollout

1. **Phase 1:** Implement Approach 1 — `model_roles` in profile config, `resolve_model()` on agent
2. **Phase 2 (optional):** Add `ModelSelector` to SPAR strategy for fine-grained phase control
3. **Phase 3 (optional):** Add `LLMRouter` wrapper for runtime-adaptive selection

---

## Implementation Checklist (Approach 1)

- [ ] Add `model_roles: dict[str, str]` to `Agent.__init__()` in `lean_agent.py`
- [ ] Add `Agent.resolve_model(role: str) -> str` method
- [ ] Update `_generate_plan()` to use `agent.resolve_model("planning")`
- [ ] Update `NativeReActStrategy` main loop to use `agent.resolve_model("reasoning")`
- [ ] Update `_stream_final_response()` to use `agent.resolve_model("summarizing")`
- [ ] Update `_run_reflection_cycle()` to use `agent.resolve_model("reflecting")`
- [ ] Update `SparStrategy` act phase to use `agent.resolve_model("acting")`
- [ ] Wire `model_roles` in `factory.py` from `llm.model_roles` config
- [ ] Add `model_roles` section to `dev.yaml` example (commented out)
- [ ] Write unit tests for `resolve_model()` (with and without roles)
- [ ] Write integration test verifying different models are passed per phase
- [ ] Update `docs/profiles.md` with `model_roles` documentation
