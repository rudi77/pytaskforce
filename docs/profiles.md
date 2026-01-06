# Configuration Profiles

Taskforce uses YAML-based configuration profiles to manage settings across different environments. Profiles are located in the `configs/` directory.

## 📁 Profile Location
`configs/{profile_name}.yaml`

## 🌟 Standard Profiles

- **`dev`**: (Default) Uses file-based persistence and local/OpenAI LLM settings.
- **`staging`**: Uses PostgreSQL persistence and Cloud LLM (e.g., Azure OpenAI).
- **`prod`**: Production settings with structured logging and high-performance persistence.

## 🛠 LeanAgent Planning Strategies

You can configure how the agent plans its tasks in the profile YAML:

```yaml
agent:
  planning_strategy: native_react  # Options: native_react, plan_and_execute
  planning_strategy_params:
    max_parallel_tools: 4
```

### Available Strategies
- **`native_react`**: Traditional Reason + Act loop.
- **`plan_and_execute`**: Generates a full plan first, then executes it sequentially.

## 🔑 Selecting a Profile
1. **Environment Variable**: `SET TASKFORCE_PROFILE=prod`
2. **CLI Flag**: `taskforce run mission "..." --profile prod`

