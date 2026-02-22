# Configuration Profiles

Taskforce uses YAML-based configuration profiles to manage settings across different environments. Profiles are located in the `configs/` directory.

## 📁 Profile Location
`configs/{profile_name}.yaml`

## 🌟 Standard Profiles

- **`dev`**: (Default) Uses file-based persistence and local/OpenAI LLM settings.
- **`staging`**: Uses PostgreSQL persistence and Cloud LLM (e.g., Azure OpenAI).
- **`prod`**: Production settings with structured logging and high-performance persistence.
- **`planner`**: Epic planner profile for generating task lists.
- **`worker`**: Epic worker profile for executing assigned tasks.
- **`judge`**: Epic judge profile for consolidation and optional commits.

## 🛠 LeanAgent Planning Strategies

You can configure how the agent plans its tasks in the profile YAML:

```yaml
agent:
  planning_strategy: native_react  # Options: native_react, plan_and_execute, plan_and_react, spar
  planning_strategy_params:
    max_parallel_tools: 4
```

### Available Strategies
- **`native_react`**: Traditional Reason + Act loop.
- **`plan_and_execute`**: Generates a full plan first, then executes it sequentially.
- **`plan_and_react`**: Creates a plan, then iterates through steps with re-planning as needed.
- **`spar`**: Sense-Plan-Act-Reflect loop with explicit reflection phases.

## 🚀 Auto-Epic Orchestration

Profiles can enable automatic detection of complex missions. When enabled, the
executor classifies each mission before execution and escalates to Epic
Orchestration (planner/worker/judge) when warranted.

```yaml
orchestration:
  auto_epic:
    enabled: true                 # default: false
    confidence_threshold: 0.7     # minimum classifier confidence (0.0-1.0)
    classifier_model: fast        # LLM model alias for classification (null = default)
    default_worker_count: 3       # workers for epic runs (1-10)
    default_max_rounds: 3         # max rounds (1-10)
    planner_profile: planner      # profile for the planner agent
    worker_profile: worker        # profile for worker agents
    judge_profile: judge          # profile for the judge agent
```

The `--auto-epic` / `--no-auto-epic` CLI flag overrides the profile setting per invocation.

## Dynamic LLM Routing

Profiles can configure dynamic LLM routing to use different models for
different agent phases. For example, use a powerful reasoning model for
planning and reflection, and a fast/cheap model for summarization.

The LLM Router wraps the LLM provider and intercepts each call, selecting
the appropriate model based on configurable rules. Planning strategies emit
phase hints (`planning`, `reasoning`, `acting`, `reflecting`, `summarizing`)
that the router matches against.

```yaml
llm:
  config_path: src/taskforce_extensions/configs/llm_config.yaml
  default_model: main

  routing:
    enabled: true
    default_model: main          # fallback when no rule matches
    rules:
      # Phase-hint rules (emitted by planning strategies)
      - condition: "hint:planning"
        model: powerful           # strong model for task decomposition
      - condition: "hint:reasoning"
        model: powerful           # strong model for ReAct loop reasoning
      - condition: "hint:reflecting"
        model: powerful           # strong model for SPAR self-critique
      - condition: "hint:acting"
        model: main               # standard model for plan step execution
      - condition: "hint:summarizing"
        model: fast               # cheap model for final answer synthesis

      # Context-based rules
      - condition: "message_count > 20"
        model: powerful           # use strong model for long conversations
      - condition: has_tools
        model: main               # tool-calling steps
      - condition: no_tools
        model: fast               # no-tool calls (simple generation)
```

**Rule evaluation order:** First matching rule wins. Rules are evaluated
top-to-bottom. If no rule matches, `routing.default_model` is used.

**Supported conditions:**

| Condition | Matches when |
|-----------|-------------|
| `hint:<name>` | Strategy passes `<name>` as the model parameter |
| `has_tools` | Tools list is non-empty |
| `no_tools` | Tools list is empty or None |
| `message_count > N` | Conversation has more than N messages |

**Without routing:** When `routing.enabled` is `false` or omitted, phase
hints are silently mapped back to `default_model`. No behavior change.

**See:** [ADR-012](adr/adr-012-dynamic-llm-selection.md) for design rationale.

## ⏱ Runtime Tracking (Heartbeats & Checkpoints)

Profiles can enable runtime tracking to support long-running, recoverable sessions:

```yaml
runtime:
  enabled: true
  store: file  # Options: file, memory
  work_dir: .taskforce
```

When enabled (disabled by default), Taskforce records:
- **Heartbeats** for active sessions
- **Checkpoints** for recovering session state after restarts

## 📂 Example Multi-Agent Templates

The repository includes a document extraction multi-agent template set under:

```
configs/custom/document_extraction/
```

Prompt and tool sketches are documented in:

```
docs/templates/document_extraction/
```

## 🤖 Coding Agent Multi-Agent Workflow

The `coding_agent` profile now defines sub-agents as explicit tools and delegates
work to specialist sub-agents defined in `src/taskforce_extensions/configs/custom/`.
The `name` field is the sub-agent identifier and is used for resolution:

- `coding_planner`: breaks down missions into tasks and priorities
- `coding_worker`: implements scoped tasks with tooling access
- `coding_reviewer`: reviews changes and test coverage

Run it via:

```powershell
taskforce run mission "Implement feature X and review quality" --profile coding_agent
```

You can tune the orchestrator's planning strategy (e.g., `spar`) or
parallelism via the profile's `agent` settings. Sub-agents are declared in the
profile's `tools` list using `type: sub_agent`.

Example snippet:

```yaml
tools:
  - type: sub_agent
    name: coding_planner
```

## 🧠 Long-Term Memory Configuration

Profiles enable session-persistent memory by adding the `memory` tool and
configuring a file-backed store:

```yaml
# configs/coding_agent.yaml
memory:
  type: file
  store_dir: ".taskforce_coding/memory"

tools:
  - memory
```

**Benefits:**
- Remember user preferences across sessions
- Track project context and decisions
- Build cumulative knowledge over time

**See:** [Long-Term Memory Documentation](features/longterm-memory.md)

## 🔑 Selecting a Profile
1. **Environment Variable**: `SET TASKFORCE_PROFILE=prod`
2. **CLI Flag**: `taskforce run mission "..." --profile prod`
