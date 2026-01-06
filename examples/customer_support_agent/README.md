# Customer Support Agent Example

This example demonstrates how to create a **custom specialized agent** using the Taskforce framework. It shows you how to:

1. **Develop custom tools** that integrate with Taskforce's Clean Architecture
2. **Configure an agent** using YAML for specific use cases
3. **Define custom system prompts** for specialized behavior
4. **Use the AgentFactory** to wire everything together

---

## 📋 What This Example Includes

```
examples/customer_support_agent/
├── tools/
│   └── ticket_tool.py              # Custom ticket management tool
├── configs/
│   └── support_agent.yaml          # Agent configuration
├── run_support_agent.py            # Runnable example script
└── README.md                       # This file
```

---

## 🎯 Use Case: Customer Support Automation

This example implements a **customer support agent** that can:

- **Create and manage support tickets** (custom tool)
- **Troubleshoot technical issues** using LLM reasoning
- **Search knowledge bases** for solutions
- **Track ticket status** (open → in_progress → resolved)
- **Set appropriate priorities** (low/medium/high/critical)
- **Communicate professionally** with customers

---

## 🏗️ Architecture Overview

### 1. Custom Tool: `TicketTool`

The `TicketTool` class demonstrates how to create a custom tool that follows Taskforce's `ToolProtocol`:

```python
class TicketTool:
    @property
    def name(self) -> str:
        return "ticket_manager"

    @property
    def description(self) -> str:
        return "Manage customer support tickets..."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {...}  # JSON Schema for parameters

    async def execute(self, **params) -> Dict[str, Any]:
        # Tool logic here
        ...
```

**Key Features:**
- **File-based persistence** (simple JSON storage)
- **CRUD operations** (create, read, update, list, search)
- **Validation** of required parameters
- **Structured logging** with structlog
- **Clean error handling** with detailed error messages

**Operations:**
- `create_ticket`: Create new support tickets
- `get_ticket`: Retrieve ticket details by ID
- `update_ticket`: Update status or add notes
- `list_tickets`: List all tickets (with optional status filter)
- `search_tickets`: Search by email or keywords

### 2. YAML Configuration

The `configs/support_agent.yaml` file shows how to configure an agent:

```yaml
profile: support_agent
specialist: null  # Custom system prompt instead

persistence:
  type: file
  work_dir: .taskforce_support

agent:
  max_steps: 40
  planning_strategy: plan_and_react
  planning_strategy_params:
    max_plan_steps: 10

llm:
  config_path: configs/llm_config.yaml
  default_model: main

tools:
  - web_search
  - web_fetch
  - python
  - file_read
  - file_write
  - ask_user
  # - ticket_manager  # Would need tool registry integration
```

**Configuration Sections:**
- **profile**: Unique identifier for this agent configuration
- **specialist**: Set to `null` to use custom system prompt
- **persistence**: Where to store agent state
- **agent**: Behavior settings (max_steps, planning strategy)
- **llm**: Which LLM model to use
- **tools**: List of available tools for the agent

### 3. Custom System Prompt

The example shows how to define specialized behavior through prompts:

```python
SUPPORT_SYSTEM_PROMPT = """You are a professional customer support agent...

Your responsibilities:
1. Handle customer inquiries with empathy
2. Create and manage support tickets
3. Troubleshoot technical problems
...

Communication Style:
- Be friendly and professional
- Use clear language
- Provide ticket IDs for reference
...
"""
```

---

## 🚀 How to Run This Example

### Prerequisites

1. **Install Taskforce** (from project root):
   ```bash
   cd /home/user/pytaskforce
   uv sync
   source .venv/bin/activate  # Linux/Mac
   ```

2. **Set OpenAI API Key**:
   ```bash
   export OPENAI_API_KEY='your-key-here'
   ```

### Option 1: Run the Complete Example

```bash
python examples/customer_support_agent/run_support_agent.py
```

This will prompt you to choose:
1. **Demonstrate ticket tool only** (no LLM needed - fast)
2. **Run full support agent mission** (requires LLM API)
3. **Both**

### Option 2: Demo the Ticket Tool

This runs quickly without LLM calls:

```bash
python -c "
import asyncio
from examples.customer_support_agent.tools.ticket_tool import TicketTool

async def demo():
    tool = TicketTool()

    # Create ticket
    result = await tool.execute(
        operation='create_ticket',
        customer_email='[email protected]',
        subject='Test issue',
        description='Testing the ticket system',
        priority='medium'
    )
    print(f'Created ticket: {result[\"ticket\"][\"ticket_id\"]}')

    # List tickets
    result = await tool.execute(operation='list_tickets')
    print(f'Total tickets: {result[\"count\"]}')

asyncio.run(demo())
"
```

### Option 3: Run Full Mission

Example mission that the agent will execute:

```python
mission = '''
A customer (email: [email protected]) cannot log in.
They tried resetting their password but the email never arrives.
This has been ongoing for 2 hours.

Please:
1. Create a support ticket with appropriate priority
2. Troubleshoot the issue
3. Search for similar past issues
4. Provide a solution or escalation plan
5. Update the ticket with findings
'''
```

---

## 🔧 How to Adapt This Example

### 1. Modify for Your Use Case

**Change the Tool:**
- Edit `tools/ticket_tool.py`
- Implement your own operations (e.g., CRM integration, Slack notifications)
- Adjust the `parameters_schema` for your needs

**Change the System Prompt:**
- Edit `SUPPORT_SYSTEM_PROMPT` in `run_support_agent.py`
- Customize tone, responsibilities, and instructions
- Add domain-specific knowledge

**Change the Configuration:**
- Edit `configs/support_agent.yaml`
- Add/remove tools from the `tools` list
- Adjust `max_steps`, `planning_strategy`, etc.

### 2. Register Your Custom Tool

To use custom tools in the main Taskforce CLI, you need to register them:

**Option A: Add to Tool Registry** (`src/taskforce/infrastructure/tools/registry.py`):

```python
# In resolve_tool_spec()
TOOL_REGISTRY = {
    # ... existing tools ...
    "ticket_manager": {
        "type": "TicketTool",
        "module": "examples.customer_support_agent.tools.ticket_tool",
        "params": {"tickets_dir": ".taskforce_tickets"}
    }
}
```

**Option B: Use `create_lean_agent_from_definition()`** (shown in example):

```python
from examples.customer_support_agent.tools.ticket_tool import TicketTool

agent_definition = {
    "system_prompt": SUPPORT_SYSTEM_PROMPT,
    "tool_allowlist": ["web_search", "python", "ask_user"],
    "mcp_servers": [],
    "mcp_tool_allowlist": []
}

agent = await factory.create_lean_agent_from_definition(
    agent_definition=agent_definition,
    profile="dev"
)

# Manually inject custom tool
agent.tools.append(TicketTool())
```

### 3. Integrate with External Systems

Replace the file-based storage with real systems:

```python
class TicketTool:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    async def _create_ticket(self, params):
        # Call real ticketing API (Zendesk, Jira, etc.)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/tickets",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=params
            ) as response:
                return await response.json()
```

---

## 📊 Example Output

### Ticket Tool Demonstration

```
================================================================================
TICKET TOOL DEMONSTRATION
================================================================================

1. Creating a new ticket...
   Created: a7f3c912

2. Retrieving ticket a7f3c912...
   Status: open
   Priority: high

3. Updating ticket status and adding notes...
   Updated status: in_progress
   Notes added: 1

4. Listing all open tickets...
   Found 1 ticket(s) in progress

5. Searching for tickets by email...
   Found 1 matching ticket(s)

================================================================================
```

### Full Agent Mission

```
================================================================================
MISSION RESULT
================================================================================

Success: True
Steps Taken: 12

Final Answer:
I've handled the customer's login issue:

1. Created support ticket #a7f3c912 (Priority: HIGH)
2. Investigated the issue:
   - Checked email delivery logs - no blocks found
   - Verified account status - account is active
   - Found similar issue in past tickets (Ticket #xyz123)
3. Root cause: Email provider's spam filter was blocking reset emails
4. Solution applied:
   - Added customer's email to whitelist
   - Manually sent password reset link via alternative method
   - Sent follow-up instructions to customer
5. Updated ticket status to "resolved"
6. Recommended monitoring email delivery for next 24 hours

Customer should now be able to receive the reset email.
================================================================================
```

---

## 🎓 Learning Takeaways

### Framework vs. Application

**Taskforce is BOTH:**
- **Framework**: Reusable architecture for building AI agents
- **Application**: Ready-to-use agents (coding, RAG) with CLI/API

### Three Ways to Extend Taskforce

1. **YAML Configuration** (easiest)
   - No code changes needed
   - Just configure `tools`, `llm`, `persistence`
   - Great for: Using existing tools in new combinations

2. **Custom Agent Definition** (flexible)
   - Define `system_prompt` and `tool_allowlist` programmatically
   - Use `create_lean_agent_from_definition()`
   - Great for: Custom prompts with existing tools

3. **Custom Tools** (most powerful)
   - Implement `ToolProtocol` interface
   - Full control over tool behavior
   - Great for: Integrating with external systems

### Clean Architecture Benefits

The example demonstrates Clean Architecture principles:

- **Domain Logic** (`TicketTool`) is independent of framework
- **Infrastructure** (file storage) is swappable
- **Configuration** (YAML) is separate from code
- **Dependency Injection** via `AgentFactory`

You can take `TicketTool` and use it in any Python project, not just Taskforce!

---

## 🔗 Related Documentation

- **Main README**: `/home/user/pytaskforce/README.md`
- **CLAUDE.md**: `/home/user/pytaskforce/CLAUDE.md` (detailed framework guide)
- **Architecture Docs**: `/home/user/pytaskforce/docs/architecture/`
- **Tool Development**: See "Adding a New Tool" in CLAUDE.md

---

## 💡 Next Steps

1. **Run this example** to understand the pattern
2. **Modify the ticket tool** for your use case
3. **Create your own specialized agent** using this as a template
4. **Share your agent** with the community!

---

## 🤝 Contributing

Have you built a cool agent? Consider contributing it as an example:

1. Create a new directory under `examples/`
2. Follow the structure of this example
3. Add comprehensive documentation
4. Submit a pull request

---

## 📝 License

This example is part of the Taskforce project and follows the same MIT license.
