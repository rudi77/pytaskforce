# Configuration Profiles

Taskforce uses YAML-based configuration profiles. The unified CLI resolves
profiles across the framework and any installed agent packages, so a profile
shipped by `taskforce-butler` or `taskforce-coding-agent` is found
transparently once the package is installed.

## Profile Locations

Profiles are discovered from multiple roots:

| Root | Source | Used for |
|------|--------|----------|
| `src/taskforce/configs/` | Framework (always present) | Framework profiles & `llm_config.yaml` |
| `agents/butler/configs/` | `taskforce-butler` package | `butler`, butler roles & custom roles |
| `agents/coding-agent/configs/` | `taskforce-coding-agent` package | `coding_agent`, sub-agent profiles |
| `agents/rag-agent/configs/` | `taskforce-rag-agent` package | `rag_agent` |
| `./.taskforce/configs/` (if configured) | Project overrides | Project-specific profiles |

`taskforce_cli.agent_discovery.register_agent_config_dirs()` adds the
installed agent packages' `configs/` directories to the profile loader. If you
run the framework-only fallback CLI (`src/taskforce/api/cli/main.py`), only
the framework root is searched and `--profile butler` will fail unless you
explicitly extend the search path.

## Available Profiles

### Framework Profiles (always available)

| Profile | Description |
|---------|-------------|
| `default` | General-purpose profile with essential tools (file, shell, python, web, git, memory, ask_user, llm) |
| `dev` | Resolved from built-in defaults — no YAML file, useful when running without any agent package |
| `acp_peer` | Profile for agents exposed over the ACP protocol |
| `showcase_coder`, `showcase_orchestrator`, `showcase_researcher` | Demo profiles used by examples |

### Agent-Package Profiles (optional)

Install the matching package to unlock these profiles.

**`taskforce-butler`** — profiles in `agents/butler/configs/`:

| Profile | File | Description |
|---------|------|-------------|
| `butler` | `butler.yaml` | Event-driven personal assistant daemon |
| `butler_roles/accountant` | `roles/accountant.yaml` | Financial document processing |
| `butler_roles/personal_assistant` | `roles/personal_assistant.yaml` | General personal assistant tasks |
| `accountant`, `pc-agent`, `research_agent`, `vision_ocr` | `custom/*.yaml` | Butler custom-role profiles |

**`taskforce-coding-agent`** — profiles in `agents/coding-agent/configs/`:

| Profile | File | Description |
|---------|------|-------------|
| `coding_agent` | `coding_agent.yaml` | Multi-agent coding orchestrator (planner/worker/reviewer) |
| `coding_analysis` | `coding_analysis.yaml` | Code analysis specialist |
| `coding_planner`, `coding_worker`, `coding_reviewer`, `code_reviewer`, `test_engineer`, `doc_writer`, `swe_analyzer`, `swe_coder` | `custom/*.yaml` | Sub-agent profiles used by the orchestrator |

**`taskforce-rag-agent`** — profiles in `agents/rag-agent/configs/`:

| Profile | File | Description |
|---------|------|-------------|
| `rag_agent` | `rag_agent.yaml` | RAG-enabled agent (Azure AI Search integration) |

## Selecting a Profile

1. **Environment Variable**: `export TASKFORCE_PROFILE=<name>`
2. **CLI Flag**: `taskforce run mission "..." --profile <name>`

**Default profile:** The unified CLI picks `butler` when `taskforce_butler`
is importable, otherwise falls back to `dev`. The framework-only fallback CLI
always defaults to `dev`. Override any time with `--profile`.

## Deployment Manifest (visible-agents allowlist)

A *deployment manifest* controls which agents surface in user-facing
listings — `GET /api/v1/agents`, the UI Agents page, and
`taskforce config profiles`. Agents that are not on the manifest stay
**fully loadable by id** so master agents can still extend them as
sub-agents; they simply don't appear in the catalog.

The framework ships a default manifest at
`src/taskforce/configs/deployment.yaml` that lists Butler + its
sub-agents (coding pipeline, research, accountant, …), `rag_agent`,
and the standalone `accounting_agent`.

```yaml
# src/taskforce/configs/deployment.yaml
version: 1
visible_agents:
  - butler
  - coding_agent
  - rag_agent
  - accounting_agent
  # …see file for the full default list
```

**Override at runtime:**

| Mechanism | Use case |
|-----------|----------|
| `TASKFORCE_DEPLOYMENT_MANIFEST=/path/to/your.yaml` | Self-hosted operator picks a different shipping list |
| `set_deployment_manifest_override(...)` (`taskforce.application.infrastructure_overrides`) | Plugin code (e.g. `taskforce-enterprise`) supplies a per-tenant manifest |
| Edit `deployment.yaml` directly | Permanent change in this checkout |

**Bypass for power users:** `GET /api/v1/agents?include_hidden=true`
returns every discovered agent including the hidden ones. The UI uses
this for the upcoming visible-agents editor.

When no manifest can be resolved, the registry falls back to its
legacy unfiltered behaviour, so embedded users that don't ship a
manifest are unaffected.

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

### ACP Peers

Profiles that include `call_acp_agent` can declare remote peers:

```yaml
acp:
  peers:
    - name: researcher
      base_url: http://localhost:8801
      agent: researcher
      tenant_id: default
      allow_cross_tenant: false
      auth:
        type: none
```

`tenant_id` and `allow_cross_tenant` are optional and default to `default` and `false`. Enterprise runtimes can provide the caller tenant dynamically; cross-tenant ACP calls are denied unless the peer explicitly opts in with `allow_cross_tenant: true`.

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
  default_timezone: Europe/Vienna   # IANA name, used when a job omits timezone
```

Per-job fields on `ScheduleJob` (issue #158 edge cases):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `timezone` | IANA name (e.g. `Europe/Vienna`) | scheduler `default_timezone` (then `UTC`) | Cron expressions and naive ISO datetimes are evaluated in this zone. The same `0 8 * * *` therefore stays at 08:00 local across DST transitions. |
| `coalesce` | `skip` \| `run_once` | `skip` | Catch-up policy when the scheduler has been down. `skip` (default) ignores missed firings and waits for the next upcoming occurrence. `run_once` fires exactly one catch-up at startup if any occurrence was missed — useful for "make sure this happened today" jobs but **not** for high-frequency intervals where dozens of catch-ups are undesirable. |
| `last_fired_at` | ISO datetime, internal | `null` | Set by the scheduler **before** the action runs, so a crash mid-fire cannot cause a duplicate firing on restart. One-shot jobs whose `last_fired_at` is non-null are dropped on startup. |

DST handling is automatic: cron candidates that fall in a non-existent
local hour (forward jump) are skipped to the next valid match;
ambiguous local times (backward jump) resolve to the first occurrence
(`fold=0`) so the slot fires exactly once.

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
