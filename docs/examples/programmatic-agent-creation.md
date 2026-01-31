# Programmatic Agent Creation with Tools

This guide demonstrates how to create and run Taskforce agents programmatically in Python, including custom tool implementation.

## Quick Start

The simplest way to create and run an agent:

```python
import asyncio
from taskforce.application.factory import AgentFactory

async def main():
    factory = AgentFactory()

    # Option 1: From config file
    agent = await factory.create_agent(config="dev")

    # Execute a mission
    result = await agent.execute(
        mission="What is 2 + 2?",
        session_id="quick-start-001"
    )

    print(f"Status: {result.status}")
    print(f"Response: {result.final_message}")

asyncio.run(main())
```

## Two Ways to Create Agents

The `create_agent()` method supports two mutually exclusive modes:

### Option 1: Config File Path

Load all settings from a YAML configuration file:

```python
# Use a profile name (resolves to configs/{name}.yaml)
agent = await factory.create_agent(config="dev")

# Or use a full path
agent = await factory.create_agent(config="configs/custom/my_agent.yaml")
```

### Option 2: Inline Parameters

Specify settings programmatically:

```python
agent = await factory.create_agent(
    system_prompt="You are a helpful coding assistant. Be concise.",
    tools=["python", "file_read", "file_write"],
    persistence={"type": "file", "work_dir": ".taskforce_coding"},
    max_steps=20,
)
```

**Important:** You cannot mix both modes. Either provide `config` OR inline parameters.

## Creating Agents with Specific Tools

```python
import asyncio
from taskforce.application.factory import AgentFactory

async def main():
    factory = AgentFactory()

    # Create agent with specific tools
    agent = await factory.create_agent(
        system_prompt="You are a helpful coding assistant. Be concise.",
        tools=["python", "file_read", "file_write"],
        work_dir=".taskforce_coding"
    )

    result = await agent.execute(
        mission="Write a Python function that calculates fibonacci numbers",
        session_id="coding-001"
    )

    print(result.final_message)

asyncio.run(main())
```

### Available Native Tools

| Tool Name | Description |
|-----------|-------------|
| `web_search` | Search the web using DuckDuckGo |
| `web_fetch` | Fetch and parse web page content |
| `python` | Execute Python code |
| `file_read` | Read file contents |
| `file_write` | Write content to files |
| `git` | Execute git commands |
| `github` | Interact with GitHub API |
| `powershell` | Execute shell commands |
| `ask_user` | Request information from user |

## Creating a Custom Tool

Custom tools must implement `ToolProtocol`. Here's a complete example:

```python
from typing import Any
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class CalculatorTool(ToolProtocol):
    """A simple calculator tool for basic arithmetic."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Perform basic arithmetic operations (add, subtract, multiply, divide)."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "The arithmetic operation to perform",
                    "enum": ["add", "subtract", "multiply", "divide"]
                },
                "a": {
                    "type": "number",
                    "description": "First operand"
                },
                "b": {
                    "type": "number",
                    "description": "Second operand"
                }
            },
            "required": ["operation", "a", "b"]
        }

    @property
    def requires_approval(self) -> bool:
        return False  # Safe, read-only operation

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True  # No side effects, safe for parallel execution

    def get_approval_preview(self, **kwargs: Any) -> str:
        op = kwargs.get("operation", "unknown")
        a = kwargs.get("a", 0)
        b = kwargs.get("b", 0)
        return f"Tool: {self.name}\nOperation: {op}({a}, {b})"

    async def execute(
        self,
        operation: str,
        a: float,
        b: float,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Execute the calculation."""
        try:
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                if b == 0:
                    return {"success": False, "error": "Division by zero"}
                result = a / b
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

            return {
                "success": True,
                "result": result,
                "expression": f"{a} {operation} {b} = {result}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        required = ["operation", "a", "b"]
        for param in required:
            if param not in kwargs:
                return False, f"Missing required parameter: {param}"

        if kwargs["operation"] not in ["add", "subtract", "multiply", "divide"]:
            return False, f"Invalid operation: {kwargs['operation']}"

        return True, None
```

## Using Custom Tools with an Agent

Inject custom tools when creating an agent:

```python
import asyncio
from taskforce.application.factory import AgentFactory

# Import your custom tool
from my_tools import CalculatorTool


async def main():
    factory = AgentFactory()

    # Create agent with minimal tools
    agent = await factory.create_agent(
        system_prompt="You are a math tutor. Use the calculator tool for computations.",
        tools=[],  # Start with no native tools
    )

    # Add custom tool to agent's toolset
    calculator = CalculatorTool()
    agent.tools.append(calculator)

    # Execute mission using the custom tool
    result = await agent.execute(
        mission="Calculate 15 * 7 + 23",
        session_id="math-001"
    )

    print(result.final_message)

asyncio.run(main())
```

## Combining Native and Custom Tools

Mix built-in tools with custom implementations:

```python
import asyncio
from taskforce.application.factory import AgentFactory

from my_tools import CalculatorTool


async def main():
    factory = AgentFactory()

    # Create agent with native tools
    agent = await factory.create_agent(
        system_prompt="""You are a helpful assistant with access to:
- Calculator for math operations
- Python for complex computations
- File operations for reading/writing data""",
        tools=["python", "file_read"],
    )

    # Add custom tools
    agent.tools.append(CalculatorTool())

    result = await agent.execute(
        mission="Read numbers.txt and calculate their sum using the calculator",
        session_id="combined-001"
    )

    print(result.final_message)

asyncio.run(main())
```

## Streaming Execution with Progress Updates

For long-running tasks, use streaming to get real-time updates:

```python
import asyncio
from taskforce.application.factory import AgentFactory


async def main():
    factory = AgentFactory()
    agent = await factory.create_agent(config="dev")

    # Stream execution events
    async for event in agent.execute_stream(
        mission="Analyze the Python files in the current directory",
        session_id="stream-001"
    ):
        if event.event_type == "thought":
            print(f"Thinking: {event.content}")
        elif event.event_type == "tool_call":
            print(f"Using tool: {event.tool_name}")
        elif event.event_type == "tool_result":
            print(f"Tool result received")
        elif event.event_type == "complete":
            print(f"\nFinal: {event.content}")

asyncio.run(main())
```

## Using the AgentExecutor Service

For production use, the `AgentExecutor` provides additional orchestration:

```python
import asyncio
from taskforce.application.factory import AgentFactory
from taskforce.application.executor import AgentExecutor


async def main():
    factory = AgentFactory()
    executor = AgentExecutor(factory=factory)

    # Execute with progress callback
    def on_progress(update):
        print(f"[{update.event_type}] {update.message}")

    result = await executor.execute_mission(
        mission="Summarize the README.md file",
        profile="dev",
        session_id="executor-001",
        progress_callback=on_progress
    )

    print(f"\nStatus: {result.status}")
    print(f"Result: {result.final_message}")

asyncio.run(main())
```

## Handling Execution Results

The `ExecutionResult` provides detailed information about the execution:

```python
from taskforce.core.domain.models import ExecutionResult

async def handle_result(result: ExecutionResult):
    # Check status
    if result.status == "completed":
        print("Mission completed successfully!")
        print(f"Response: {result.final_message}")
    elif result.status == "failed":
        print(f"Mission failed: {result.final_message}")
    elif result.status == "paused":
        print(f"Waiting for user input: {result.pending_question}")

    # Review execution history
    for event in result.execution_history:
        if event.event_type == "thought":
            print(f"  Thought: {event.content[:100]}...")
        elif event.event_type == "action":
            print(f"  Action: {event.tool_name}({event.tool_args})")

    # Check token usage
    if result.token_usage:
        print(f"Tokens used: {result.token_usage}")
```

## Planning Strategies

Configure how the agent approaches complex tasks:

```python
async def main():
    factory = AgentFactory()

    # Native ReAct (default) - immediate tool use
    agent_react = await factory.create_agent(
        config="dev",
        planning_strategy="native_react"
    )

    # Plan-and-Execute - creates plan first, then executes steps
    agent_plan = await factory.create_agent(
        config="dev",
        planning_strategy="plan_and_execute",
        planning_strategy_params={
            "max_plan_steps": 10,
            "max_step_iterations": 3
        }
    )

    # Plan-and-React - hybrid approach
    agent_hybrid = await factory.create_agent(
        tools=["python", "file_read"],
        planning_strategy="plan_and_react"
    )
```

## Complete Example: Data Analysis Agent

A full example combining concepts:

```python
import asyncio
from typing import Any
from taskforce.application.factory import AgentFactory
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class DataSummaryTool(ToolProtocol):
    """Summarize numeric data from a list."""

    @property
    def name(self) -> str:
        return "data_summary"

    @property
    def description(self) -> str:
        return "Calculate statistics (mean, min, max, count) for a list of numbers."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "numbers": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of numbers to analyze"
                }
            },
            "required": ["numbers"]
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        numbers = kwargs.get("numbers", [])
        return f"Tool: {self.name}\nAnalyzing {len(numbers)} numbers"

    async def execute(self, numbers: list[float], **kwargs: Any) -> dict[str, Any]:
        if not numbers:
            return {"success": False, "error": "Empty number list"}

        return {
            "success": True,
            "count": len(numbers),
            "sum": sum(numbers),
            "mean": sum(numbers) / len(numbers),
            "min": min(numbers),
            "max": max(numbers)
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "numbers" not in kwargs:
            return False, "Missing required parameter: numbers"
        if not isinstance(kwargs["numbers"], list):
            return False, "Parameter 'numbers' must be a list"
        return True, None


async def main():
    factory = AgentFactory()

    # Create agent with file reading + custom analysis tool
    agent = await factory.create_agent(
        system_prompt="""You are a data analyst assistant.
You can read data files and perform statistical analysis.
Always show your calculations and explain the results.""",
        tools=["file_read", "python"],
    )

    # Add custom analysis tool
    agent.tools.append(DataSummaryTool())

    # Run analysis
    result = await agent.execute(
        mission="Analyze the sales data: [100, 250, 175, 300, 225, 150]",
        session_id="analysis-001"
    )

    print("=" * 50)
    print("DATA ANALYSIS RESULT")
    print("=" * 50)
    print(result.final_message)


if __name__ == "__main__":
    asyncio.run(main())
```

## API Reference

### `create_agent()` Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `str` | Path to YAML config file (mutually exclusive with inline params) |
| `system_prompt` | `str` | Custom system prompt for the agent |
| `tools` | `list[str]` | List of tool names to enable |
| `llm` | `dict` | LLM configuration |
| `persistence` | `dict` | Persistence configuration |
| `mcp_servers` | `list[dict]` | MCP server configurations |
| `max_steps` | `int` | Maximum execution steps |
| `planning_strategy` | `str` | Planning strategy name |
| `planning_strategy_params` | `dict` | Planning strategy parameters |
| `context_policy` | `dict` | Context policy configuration |
| `work_dir` | `str` | Override for work directory |
| `user_context` | `dict` | User context for RAG tools |
| `specialist` | `str` | Specialist profile ("coding", "rag", "wiki") |

## Environment Setup

Before running these examples, ensure you have:

1. **API Key**: Set `OPENAI_API_KEY` environment variable
2. **Dependencies**: Install with `uv sync`
3. **Profile**: A valid profile in `src/taskforce_extensions/configs/`

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Install dependencies
uv sync

# Run example
uv run python my_agent_script.py
```

## Next Steps

- **[Custom Tool Tutorial](custom-tool-and-profile-tutorial.ipynb)**: Interactive Jupyter notebook walkthrough
- **[Plugin Development](../plugins.md)**: Package tools as reusable plugins
- **[Profiles Configuration](../profiles.md)**: Configure agent behavior via YAML
- **[Architecture Guide](../architecture.md)**: Understand the Clean Architecture design
