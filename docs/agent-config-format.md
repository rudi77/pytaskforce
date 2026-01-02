# Agent Configuration Format

## Overview

This document describes the two agent configuration formats used in the Taskforce system:

1. **API Format** - Simplified format for Custom Agent API (CRUD operations)
2. **Profile Format** - Full configuration format for YAML files

## API Format (Custom Agents)

Used for API requests/responses when creating or updating custom agents.

### Request Schema (CustomAgentCreate / CustomAgentUpdate)

```json
{
  "agent_id": "web-agent",
  "name": "Web Agent",
  "description": "Search and scrapes the web",
  "system_prompt": "You are a web research agent...",
  "tool_allowlist": ["web_search", "web_fetch", "python", "ask_user"],
  "mcp_servers": [],
  "mcp_tool_allowlist": []
}
```

### Response Schema (CustomAgentResponse)

```json
{
  "source": "custom",
  "agent_id": "web-agent",
  "name": "Web Agent",
  "description": "Search and scrapes the web",
  "system_prompt": "You are a web research agent...",
  "tool_allowlist": ["web_search", "web_fetch", "python", "ask_user"],
  "mcp_servers": [],
  "mcp_tool_allowlist": [],
  "created_at": "2025-12-12T18:44:54.868576+00:00",
  "updated_at": "2025-12-12T18:45:47.565992+00:00"
}
```

## Profile Format (YAML Files)

Used for YAML configuration files in `configs/` directory.

### Example: `configs/custom/web-agent.yaml`

```yaml
# Web Agent Configuration
# Agent specialized for web search and scraping

profile: web-agent
specialist: generic

# Agent configuration
agent:
  enable_fast_path: true
  router:
    use_llm_classification: true
    max_follow_up_length: 100

# Persistence configuration
persistence:
  type: file
  work_dir: .taskforce_web

# LLM configuration
llm:
  config_path: configs/llm_config.yaml
  default_model: main

# Logging configuration
logging:
  level: DEBUG
  format: console

# Tool configuration
tools:
  - type: WebSearchTool
    module: taskforce.infrastructure.tools.native.web_tools
    params: {}

  - type: WebFetchTool
    module: taskforce.infrastructure.tools.native.web_tools
    params: {}

  - type: PythonTool
    module: taskforce.infrastructure.tools.native.python_tool
    params: {}

  - type: AskUserTool
    module: taskforce.infrastructure.tools.native.ask_user_tool
    params: {}

# MCP Server Configuration
mcp_servers: []

# Internal metadata (for custom agents)
agent_id: web-agent
name: Web Agent
description: Search and scrapes the web
system_prompt: "You are a web research agent..."
created_at: "2025-12-12T18:44:54.868576+00:00"
updated_at: "2025-12-12T18:45:47.565992+00:00"
```

## Tool Name Mapping

The `ToolMapper` service converts simplified tool names to full tool definitions:

| Tool Name | Tool Type | Module |
|-----------|-----------|--------|
| `web_search` | `WebSearchTool` | `taskforce.infrastructure.tools.native.web_tools` |
| `web_fetch` | `WebFetchTool` | `taskforce.infrastructure.tools.native.web_tools` |
| `python` | `PythonTool` | `taskforce.infrastructure.tools.native.python_tool` |
| `file_read` | `FileReadTool` | `taskforce.infrastructure.tools.native.file_tools` |
| `file_write` | `FileWriteTool` | `taskforce.infrastructure.tools.native.file_tools` |
| `git` | `GitTool` | `taskforce.infrastructure.tools.native.git_tools` |
| `github` | `GitHubTool` | `taskforce.infrastructure.tools.native.git_tools` |
| `powershell` | `PowerShellTool` | `taskforce.infrastructure.tools.native.shell_tool` |
| `ask_user` | `AskUserTool` | `taskforce.infrastructure.tools.native.ask_user_tool` |
| `llm` | `LLMTool` | `taskforce.infrastructure.tools.native.llm_tool` |

## API to Profile Conversion

When a custom agent is created or updated via API:

1. **API receives** simplified format with `tool_allowlist`
2. **ToolMapper** converts tool names to full tool definitions
3. **FileAgentRegistry** saves in Profile Format with:
   - Full tool definitions (`tools`)
   - Complete agent configuration (`agent`, `persistence`, `llm`, `logging`)
   - Metadata fields (`agent_id`, `name`, `description`, timestamps)

### Example Conversion

**API Input:**
```json
{
  "tool_allowlist": ["web_search", "python"]
}
```

**YAML Output:**
```yaml
tools:
  - type: WebSearchTool
    module: taskforce.infrastructure.tools.native.web_tools
    params: {}
  - type: PythonTool
    module: taskforce.infrastructure.tools.native.python_tool
    params: {}
```

## Loading Custom Agents

When loading a custom agent from YAML:

1. **FileAgentRegistry** reads YAML file
2. Extracts tool definitions from `tools` array
3. **ToolMapper** converts tool types back to tool names
4. Returns **CustomAgentResponse** with `tool_allowlist`

This ensures the API always works with simplified tool names, while YAML files use the full profile format.

## Benefits

1. **Consistency**: All YAML configs use the same format
2. **Compatibility**: Custom agents work with existing AgentFactory
3. **Simplicity**: API users work with simple tool names
4. **Flexibility**: Full control in YAML files
5. **Maintainability**: Single source of truth for tool definitions

## Related Files

- `taskforce/src/taskforce/application/tool_mapper.py` - Tool name mapping
- `taskforce/src/taskforce/infrastructure/persistence/file_agent_registry.py` - YAML persistence
- `taskforce/src/taskforce/api/schemas/agent_schemas.py` - API schemas
- `taskforce/tests/unit/test_tool_mapper.py` - Unit tests

