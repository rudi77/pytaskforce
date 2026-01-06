# Taskforce Examples

This directory contains **practical examples** demonstrating how to use and extend the Taskforce framework.

---

## 🎯 Purpose

These examples show you:

1. **How Taskforce works as a framework** - not just an application
2. **How to create custom specialized agents** for specific use cases
3. **How to develop custom tools** that integrate with Clean Architecture
4. **Best practices** for agent configuration and deployment
5. **Real-world patterns** you can adapt for your needs

---

## 📚 Available Examples

### 1. Customer Support Agent

**Location**: `customer_support_agent/`

**What it demonstrates:**
- Creating a custom tool (`TicketTool`) for ticket management
- Configuring an agent with YAML for specialized behavior
- Defining custom system prompts for domain-specific tasks
- Using `AgentFactory` for dependency injection
- File-based persistence with JSON storage

**Use case**: Automated customer support with ticket tracking, troubleshooting, and knowledge base search.

**Complexity**: ⭐⭐ (Intermediate)

**[Read full documentation →](customer_support_agent/README.md)**

---

## 🚀 Quick Start

### Prerequisites

```bash
# Install Taskforce
cd /home/user/pytaskforce
uv sync
source .venv/bin/activate  # Linux/Mac
# .\.venv\Scripts\Activate.ps1  # Windows

# Set API key
export OPENAI_API_KEY='your-key-here'
```

### Run an Example

```bash
# Customer Support Agent
python examples/customer_support_agent/run_support_agent.py
```

---

## 🏗️ Example Structure

Each example follows this consistent structure:

```
example_name/
├── tools/                    # Custom tools
│   └── custom_tool.py
├── configs/                  # YAML configurations
│   └── agent_config.yaml
├── run_example.py           # Runnable script
├── README.md                # Detailed documentation
└── __init__.py              # Package marker
```

This makes examples:
- **Easy to understand** - consistent layout
- **Easy to run** - self-contained scripts
- **Easy to adapt** - copy and modify for your needs

---

## 🎓 Learning Path

**If you're new to Taskforce**, we recommend this progression:

1. **Read the main README** (`/home/user/pytaskforce/README.md`)
   - Understand what Taskforce is
   - Learn the CLI basics
   - Try the built-in agents

2. **Read CLAUDE.md** (`/home/user/pytaskforce/CLAUDE.md`)
   - Understand Clean Architecture
   - Learn the four-layer structure
   - Study dependency injection patterns

3. **Study Customer Support Agent** (`customer_support_agent/`)
   - See how to create custom tools
   - Learn YAML configuration
   - Understand agent specialization

4. **Build your own agent**
   - Copy an example as a template
   - Adapt it for your use case
   - Share it with the community!

---

## 💡 Understanding Framework vs. Application

**Taskforce is BOTH a framework and an application:**

### As a Framework

Taskforce provides:
- **Clean Architecture** foundation (4-layer separation)
- **Protocol-based** interfaces (swappable components)
- **Dependency injection** via `AgentFactory`
- **Extensible tooling** system
- **Configuration management** with YAML
- **State persistence** (file or database)
- **LLM provider** abstraction (OpenAI, Azure, etc.)

You can use Taskforce to build your own AI agents from scratch.

### As an Application

Taskforce includes:
- **Ready-to-use agents** (coding agent, RAG agent)
- **CLI interface** (`taskforce` command)
- **REST API** (FastAPI-based)
- **Pre-built tools** (web search, file operations, Python, Git, etc.)
- **Session management** and state tracking
- **Production deployment** support (Docker, K8s)

You can use Taskforce out-of-the-box without writing code.

---

## 🔧 Three Ways to Extend Taskforce

### 1. YAML Configuration (Easiest)

**When to use:** Combine existing tools in new ways, change agent behavior

**Example:**
```yaml
# configs/my_agent.yaml
profile: my_agent
specialist: null

tools:
  - web_search
  - python
  - file_read
  - ask_user

agent:
  max_steps: 50
  planning_strategy: plan_and_react
```

**Usage:**
```bash
taskforce run mission "Do something" --profile my_agent
```

### 2. Custom Agent Definition (Flexible)

**When to use:** Custom system prompts, dynamic tool selection

**Example:**
```python
from taskforce.application.factory import AgentFactory

agent_definition = {
    "system_prompt": "You are a specialized agent for...",
    "tool_allowlist": ["web_search", "python"],
    "mcp_servers": [],
    "mcp_tool_allowlist": []
}

factory = AgentFactory()
agent = await factory.create_lean_agent_from_definition(
    agent_definition=agent_definition,
    profile="dev"
)
```

### 3. Custom Tools (Most Powerful)

**When to use:** Integrate with external systems, custom business logic

**Example:**
```python
class MyCustomTool:
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something specific"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {...}  # JSON Schema

    async def execute(self, **params) -> Dict[str, Any]:
        # Your logic here
        return {"success": True, "result": ...}
```

See **Customer Support Agent** example for full implementation.

---

## 📊 Example Comparison

| Example | Complexity | Custom Tools | Custom Prompt | External APIs | Best For |
|---------|-----------|--------------|---------------|---------------|----------|
| **Customer Support** | ⭐⭐ | Yes (Ticket) | Yes | No (file-based) | Learning patterns |
| *More coming soon* | | | | | |

---

## 🎯 Example Ideas (Future)

We're planning to add more examples. Vote for what you'd like to see next:

- [ ] **Data Analysis Agent** - Pandas, visualization, statistical analysis
- [ ] **DevOps Agent** - Deployment, monitoring, log analysis
- [ ] **Research Agent** - Academic paper search, summarization
- [ ] **Code Review Agent** - Static analysis, style checking, suggestions
- [ ] **Sales Automation Agent** - CRM integration, email campaigns
- [ ] **Content Writer Agent** - Blog posts, social media, SEO optimization
- [ ] **Testing Agent** - Test generation, coverage analysis, bug reproduction
- [ ] **Documentation Agent** - API docs, user guides, tutorials

**Want to contribute?** Submit a pull request with your example!

---

## 🤝 Contributing Examples

### Guidelines

1. **Follow the structure** - Use the standard example layout
2. **Be self-contained** - Example should run independently
3. **Document thoroughly** - Explain what, why, and how
4. **Keep it focused** - One clear use case per example
5. **Provide real value** - Show patterns others can adapt

### Checklist

- [ ] Creates a new directory under `examples/`
- [ ] Includes `README.md` with comprehensive docs
- [ ] Has at least one custom tool or configuration
- [ ] Includes runnable script (`run_example.py`)
- [ ] Follows Clean Architecture principles
- [ ] Has clear comments and docstrings
- [ ] Works with current Taskforce version
- [ ] Includes example output

### Submission Process

1. Fork the repository
2. Create your example in `examples/your_example_name/`
3. Test thoroughly
4. Update this README to list your example
5. Submit a pull request

---

## 📖 Related Documentation

- **Main README**: `/home/user/pytaskforce/README.md`
- **Development Guide**: `/home/user/pytaskforce/CLAUDE.md`
- **Architecture Docs**: `/home/user/pytaskforce/docs/architecture/`
- **API Reference**: Run `taskforce --help`

---

## 💬 Community

- **Issues**: Report bugs or request examples on GitHub
- **Discussions**: Share your use cases and learnings
- **Pull Requests**: Contribute your own examples

---

## 📝 License

All examples are part of the Taskforce project and follow the MIT license.

---

**Happy building!** 🚀
