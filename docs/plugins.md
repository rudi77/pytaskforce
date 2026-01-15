# Plugin Development Guide

Taskforce supports external plugins that provide custom tools for specialized agent capabilities. This guide explains how to create, structure, and use plugins.

## Overview

Plugins are Python packages that contain tool implementations compatible with `ToolProtocol`. They allow you to:

- Add domain-specific tools (e.g., accounting, legal, medical)
- Package reusable tool sets for different projects
- Share specialized agents with others

## Using Plugins

### CLI Usage

Load a plugin with the `--plugin` option:

```powershell
# Load the accounting_agent example plugin
taskforce chat --plugin examples/accounting_agent

# Combine with a profile for infrastructure settings
taskforce chat --plugin examples/accounting_agent --profile prod

# Run a mission with a plugin
taskforce run mission "Prüfe Rechnung" --plugin examples/accounting_agent
```

The plugin's tools become available to the agent alongside any native tools specified in the plugin config.

### API Usage

Plugin agents are **automatically discovered** from the `examples/` and `plugins/` directories. You can use them via the API without specifying the plugin path:

```python
import requests

# List all agents (including discovered plugins)
response = requests.get("http://localhost:8000/api/v1/agents")
agents = response.json()["agents"]

# Plugin agents have source: "plugin"
plugin_agents = [a for a in agents if a["source"] == "plugin"]

# Execute with a plugin agent (plugin_path is automatically resolved)
response = requests.post(
    "http://localhost:8000/api/v1/execution/execute",
    json={
        "mission": "Prüfe die Rechnung invoice.pdf",
        "agent_id": "accounting_agent"  # Plugin automatically loaded
    }
)
```

**Plugin Discovery:**
- Plugins in `examples/` and `plugins/` directories are automatically scanned
- Each plugin directory becomes an agent with `agent_id` matching the directory name
- Plugin agents appear in `/api/v1/agents` with `source: "plugin"`
- When executing with `agent_id` matching a plugin, the plugin is automatically loaded

**Note:** The CLI `--plugin` argument still works as before and loads plugins directly. The API discovery is an additional convenience feature.

## Plugin Structure

A plugin must follow this directory structure:

```
{plugin_path}/
├── {package_name}/           # Python package (required)
│   ├── __init__.py
│   └── tools/
│       └── __init__.py       # Exports tools via __all__
├── configs/
│   └── {package_name}.yaml   # Plugin configuration (optional)
└── requirements.txt          # Dependencies (optional)
```

### Example: accounting_agent

```
examples/accounting_agent/
├── accounting_agent/
│   ├── __init__.py
│   ├── domain/
│   │   └── models.py
│   └── tools/
│       ├── __init__.py
│       ├── docling_tool.py
│       ├── compliance_checker_tool.py
│       ├── rule_engine_tool.py
│       ├── tax_calculator_tool.py
│       └── audit_log_tool.py
├── configs/
│   ├── accounting_agent.yaml
│   └── accounting/
│       └── rules/
│           ├── compliance_rules.yaml
│           └── kontierung_rules.yaml
└── requirements.txt
```

## Creating a Tool

Each tool must implement the `ToolProtocol` interface:

```python
# my_plugin/tools/my_tool.py
from typing import Any

class MyTool:
    """Description of what the tool does."""

    @property
    def name(self) -> str:
        """Unique tool identifier (snake_case)."""
        return "my_tool"

    @property
    def description(self) -> str:
        """Human-readable description for the LLM."""
        return "Performs X operation on Y input"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """OpenAI function calling compatible JSON schema."""
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "The input data to process"
                }
            },
            "required": ["input"]
        }

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute the tool (must be async)."""
        input_data = kwargs.get("input", "")

        # Your tool logic here
        result = process(input_data)

        return {
            "success": True,
            "result": result
        }

    def validate_params(self, **kwargs) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "input" not in kwargs:
            return False, "Missing required parameter: input"
        return True, None
```

### Optional Properties

Tools can also implement these optional properties:

```python
@property
def requires_approval(self) -> bool:
    """Whether user approval is needed before execution."""
    return False  # Default

@property
def approval_risk_level(self) -> str:
    """Risk level: 'low', 'medium', 'high'."""
    return "low"

@property
def supports_parallelism(self) -> bool:
    """Whether tool can run in parallel with others."""
    return True
```

## Exporting Tools

In your `tools/__init__.py`, export tool classes via `__all__`:

```python
# my_plugin/tools/__init__.py
from my_plugin.tools.my_tool import MyTool
from my_plugin.tools.another_tool import AnotherTool

__all__ = [
    "MyTool",
    "AnotherTool",
]
```

Tools not listed in `__all__` will not be loaded.

## Plugin Configuration

Create a YAML config at `configs/{package_name}.yaml`:

```yaml
# configs/my_plugin.yaml

# Specialist prompt instructions (optional)
specialist: my_domain

# Agent settings (optional)
agent:
  max_steps: 50
  planning_strategy: plan_and_execute

# Native tools to include alongside plugin tools (optional)
tools:
  - file_read
  - ask_user

# Persistence settings (optional)
persistence:
  work_dir: .my_plugin_workspace

# MCP servers (optional)
mcp_servers:
  - type: stdio
    command: python
    args: ["my_mcp_server.py"]
```

### Configuration Merging

When using `--plugin` with `--profile`:

- **Infrastructure** (LLM, persistence type): From base profile
- **Agent settings** (max_steps, planning_strategy): Plugin overrides profile
- **Tools**: Plugin tools + native tools from plugin config
- **Work directory**: Plugin can override
- **MCP servers**: Combined (additive)

## Error Handling

Plugins should handle errors gracefully:

```python
async def execute(self, **kwargs) -> dict[str, Any]:
    try:
        result = await do_something(kwargs["input"])
        return {"success": True, "result": result}
    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "ValueError"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "error_type": type(e).__name__
        }
```

## Testing Your Plugin

1. **Unit test individual tools:**

```python
import pytest
from my_plugin.tools import MyTool

@pytest.mark.asyncio
async def test_my_tool_executes():
    tool = MyTool()
    result = await tool.execute(input="test data")
    assert result["success"]
```

2. **Test plugin discovery:**

```python
from taskforce.application.plugin_loader import PluginLoader

def test_plugin_discovery():
    loader = PluginLoader()
    manifest = loader.discover_plugin("path/to/my_plugin")
    assert manifest.name == "my_plugin"
    assert "MyTool" in manifest.tool_classes
```

3. **Integration test with agent:**

```python
from taskforce.application.factory import AgentFactory

@pytest.mark.asyncio
async def test_agent_with_plugin():
    factory = AgentFactory()
    agent = await factory.create_agent_with_plugin(
        plugin_path="path/to/my_plugin",
        profile="dev"
    )
    assert any(t.name == "my_tool" for t in agent.tools)
```

## Example: AccountingAgent

The `examples/accounting_agent` directory contains a complete plugin for German accounting:

- **DoclingTool**: PDF/image to Markdown extraction
- **ComplianceCheckerTool**: §14 UStG invoice validation
- **RuleEngineTool**: YAML-based account assignment (Kontierung)
- **TaxCalculatorTool**: VAT and depreciation calculations
- **AuditLogTool**: GoBD-compliant audit logging

Use it as a template for your own plugins:

```powershell
# Try the accounting agent
taskforce chat --plugin examples/accounting_agent

# Example prompt (German)
> Prüfe die Rechnung invoice.pdf auf Vollständigkeit und erstelle einen Buchungsvorschlag
```

## Best Practices

1. **Keep tools focused**: Each tool should do one thing well
2. **Validate inputs**: Use `validate_params()` to catch errors early
3. **Return structured data**: Use consistent result dictionaries
4. **Document thoroughly**: Good descriptions help the LLM use tools correctly
5. **Handle errors gracefully**: Return error dicts instead of raising exceptions
6. **Make tools async**: All `execute()` methods must be async
7. **Use meaningful names**: Tool names should be descriptive and snake_case
