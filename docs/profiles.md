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

Profiles can enable session-persistent memory using MCP servers:

```yaml
# configs/coding_agent.yaml
mcp_servers:
  - type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-memory"
    env:
      MEMORY_FILE_PATH: ".taskforce_coding/.memory/knowledge_graph.jsonl"
    description: "Long-term knowledge graph memory"
```

**Benefits:**
- Remember user preferences across sessions
- Track project context and decisions
- Build cumulative knowledge over time

**See:** [Long-Term Memory Documentation](features/longterm-memory.md)

## 🔑 Selecting a Profile
1. **Environment Variable**: `SET TASKFORCE_PROFILE=prod`
2. **CLI Flag**: `taskforce run mission "..." --profile prod`
