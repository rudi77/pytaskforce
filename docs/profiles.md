# Configuration Profiles

Taskforce uses YAML-based configuration profiles to manage settings across different environments. Profiles are located in `src/taskforce/configs/`.

## Profile Location

```
src/taskforce/configs/{profile_name}.yaml
src/taskforce/configs/custom/{sub_agent_name}.yaml
src/taskforce/configs/butler_roles/{role_name}.yaml
```

## Available Profiles

### Main Profiles

| Profile | Description |
|---------|-------------|
| `butler` | **Default.** Event-driven personal assistant daemon with scheduling, rules, Google Workspace integration |
| `dev` | Development profile with file-based persistence, basic toolset |
| `coding_agent` | Multi-agent coding orchestrator with planner/worker/reviewer sub-agents |
| `coding_analysis` | Code analysis specialist |
| `rag_agent` | RAG-enabled agent (Azure AI Search integration) |
| `security` | Security-hardened profile with restricted tools |
| `swe_bench` | SWE-Bench evaluation profile |

### Butler Roles

Butler role specializations in `src/taskforce/configs/butler_roles/`:

| Role | Description |
|------|-------------|
| `accountant` | Financial document processing and bookkeeping |
| `personal_assistant` | General personal assistant tasks |

### Custom Sub-Agent Profiles

Sub-agent profiles in `src/taskforce/configs/custom/`:

| Profile | Description |
|---------|-------------|
| `coding_planner` | Task decomposition and planning |
| `coding_worker` | Implementation with full tooling access |
| `coding_reviewer` | Code review specialist |
| `code_reviewer` | Alternative code review agent |
| `test_engineer` | Test writing and validation |
| `doc_writer` | Documentation creation |
| `doc-agent` | Document extraction/transformation |
| `pc-agent` | Windows system automation |
| `research_agent` | Web research and fact-checking |
| `swe_analyzer` | SWE-Bench analysis |
| `swe_coder` | SWE-Bench solving |

## Selecting a Profile

1. **Environment Variable**: `export TASKFORCE_PROFILE=dev`
2. **CLI Flag**: `taskforce run mission "..." --profile dev`

> **Note:** The default profile is `butler`, not `dev`. To use the simpler development profile, specify `--profile dev` explicitly.

## Planning Strategies

Configure how the agent plans its tasks in the profile YAML:

```yaml
agent:
  planning_strategy: native_react  # Options: native_react, plan_and_execute, plan_and_react, spar
  planning_strategy_params:
    max_parallel_tools: 4
```

### Available Strategies

| Strategy | Description |
|----------|-------------|
| `native_react` | Traditional Reason + Act loop (default) |
| `plan_and_execute` | Generates a full plan first, then executes sequentially |
| `plan_and_react` | Creates a plan, then iterates through steps with re-planning |
| `spar` | Sense-Plan-Act-Reflect loop with explicit reflection phases |

## Profile Configuration Reference

### Agent Settings

```yaml
agent:
  planning_strategy: native_react
  planning_strategy_params:
    max_parallel_tools: 4
    max_step_iterations: 3
    max_plan_steps: 12
    reflect_every_step: true
  max_steps: 30
```

### Persistence

```yaml
persistence:
  type: file          # file or postgres
  work_dir: .taskforce
```

### Runtime Tracking

```yaml
runtime:
  enabled: true       # default: false
  store: file          # file or memory
  work_dir: .taskforce
```

When enabled, Taskforce records heartbeats for active sessions and checkpoints for recovering state after restarts.

### LLM Configuration

```yaml
llm:
  config_path: src/taskforce/configs/llm_config.yaml
  default_model: main
```

### Memory

```yaml
memory:
  type: file
  store_dir: ".taskforce/memory"
```

### Context Policy

```yaml
context_policy:
  max_items: 10
  max_chars_per_item: 3000
  max_total_chars: 15000
```

### Context Management

```yaml
context_management:
  summary_threshold: 20
  compression_trigger: 15000
  max_input_tokens: 100000
```

### Tools

```yaml
tools:
  - web_search
  - web_fetch
  - file_read
  - file_write
  - python
  - bash
  - ask_user
  - memory
```

Sub-agents are declared using `type: sub_agent`:

```yaml
tools:
  - type: sub_agent
    name: coding_planner
```

### MCP Servers

```yaml
mcp_servers:
  - type: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-memory"]
    env:
      MEMORY_FILE_PATH: ".taskforce/.memory/knowledge_graph.jsonl"
    description: "Long-term knowledge graph memory"
```

### Security

```yaml
security:
  auto_approve_risk_levels: [low]
  require_confirmation: true
  autonomous_mode: false
```

### Consolidation (Memory)

```yaml
consolidation:
  auto_capture: true
  strategy: default
  max_sessions: 10
  model_alias: main
  work_dir: .taskforce/consolidation
```

### Notifications

```yaml
notifications:
  default_channel: telegram
  default_recipient_id: "123456789"
```

### Scheduler (Butler)

```yaml
scheduler:
  enabled: true
  store: file
```

### Event Sources (Butler)

```yaml
event_sources:
  - type: calendar
    poll_interval: 300
    lookahead_minutes: 30
  - type: webhook
    port: 8081
```

### Trigger Rules (Butler)

```yaml
rules:
  - name: calendar_reminder
    source: calendar
    event_type: calendar.upcoming
    action: notify
```

### Logging

```yaml
logging:
  level: DEBUG        # DEBUG, INFO, WARNING, ERROR
  format: console     # console or json
```

## Auto-Epic Orchestration

Profiles can enable automatic detection of complex missions:

```yaml
orchestration:
  auto_epic:
    enabled: true                 # default: false
    confidence_threshold: 0.7     # minimum classifier confidence (0.0-1.0)
    classifier_model: fast        # LLM model alias for classification
    default_worker_count: 3       # workers for epic runs (1-10)
    default_max_rounds: 3         # max rounds (1-10)
```

## Dynamic LLM Routing

The LLM Router enables using different models for different agent phases.
Routing is configured in `llm_config.yaml` (alongside model aliases, not in the profile YAML).

```yaml
# In llm_config.yaml
routing:
  enabled: true
  default_model: main          # fallback when no rule matches
  rules:
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
    - condition: "message_count > 20"
      model: powerful
    - condition: has_tools
      model: main
    - condition: no_tools
      model: fast
```

**Rule evaluation order:** First matching rule wins (top-to-bottom).

**Supported conditions:**

| Condition | Matches when |
|-----------|-------------|
| `hint:<name>` | Strategy passes `<name>` as the model parameter |
| `has_tools` | Tools list is non-empty |
| `no_tools` | Tools list is empty or None |
| `message_count > N` | Conversation has more than N messages |

When routing is disabled (default), phase hints are silently mapped back to `default_model`.

See [ADR-012](adr/adr-012-dynamic-llm-selection.md) for design rationale.

## Coding Agent Multi-Agent Workflow

The `coding_agent` profile delegates work to specialist sub-agents defined in `src/taskforce/configs/custom/`:

- `coding_planner`: Task decomposition and priorities
- `coding_worker`: Implementation with tooling access
- `coding_reviewer`: Code review and quality checks

Runtime tuning:
- Orchestrator: `planning_strategy: native_react`, `max_steps: 50`, broader context budget
- Worker: Narrower context budget to keep execution lean
- Sub-agent results are truncated by default (`summarize_results: true`)

```bash
taskforce run mission "Implement feature X and review quality" --profile coding_agent
```

## Long-Term Memory Configuration

```yaml
memory:
  type: file
  store_dir: ".taskforce/memory"

tools:
  - memory
```

See [Long-Term Memory Documentation](features/longterm-memory.md) for details on the human-like memory model with forgetting curves, consolidation, and associative networks.
