# Taskforce

Production-grade multi-agent orchestration framework built with Clean Architecture principles.

## 🚀 Quick Start (Windows/PowerShell)

### 1. Install uv
```powershell
# Install the uv package manager if you haven't already
pip install uv
```

### 2. Setup Environment
```powershell
# Clone and enter the repo
# cd pytaskforce

# Create virtual environment and install dependencies
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync

# Setup environment variables
Copy-Item .env.example .env
# Now edit .env and add your OPENAI_API_KEY
```

### 3. Run Your First Mission
```powershell
# CLI Mode
taskforce run mission "Describe the current weather in Vienna"

# API Mode
uvicorn taskforce.api.server:app --reload
# Documentation: `http://localhost:8000/docs`
```

### 4. Load a Plugin (Optional)
```powershell
# Run with the AccountingAgent plugin
taskforce chat --plugin examples/accounting_agent
```

---

## 📦 Features

- **Clean Architecture**: Strict layer separation (Core → Application → Infrastructure → API).
- **Dual Interfaces**: Full-featured CLI (Typer) and REST API (FastAPI).
- **Swappable Persistence**: File-based for dev, PostgreSQL for production.
- **LLM Agnostic**: Support for OpenAI, Azure OpenAI, and more via LiteLLM.
- **Plugin System**: Load custom agent plugins with specialized tools.
- **Advanced Tools**: Python, Git, RAG (Azure AI Search), and web search.
- **Long-Term Memory**: Session-persistent knowledge graphs via MCP Memory Server.

## 🧠 Architecture Overview

Taskforce follows a strict Hexagonal/Clean Architecture pattern:

```
taskforce/
├── src/taskforce/
│   ├── core/              # LAYER 1: Pure Domain Logic (Protocols, Agent, Plans)
│   ├── infrastructure/    # LAYER 2: Adapters (DB, LLM, Tools, Memory)
│   ├── application/       # LAYER 3: Use Cases (Factory, Executor, Profiles)
│   └── api/               # LAYER 4: Entrypoints (CLI, REST Routes)
```

## 📚 Documentation & Next Steps

Detailed guides are available in the [docs/](docs/) directory:

- **[Quickstart & Setup](docs/setup.md)**: Detailed environment setup.
- **[Architecture Deep Dive](docs/index.md)**: Understanding the layers.
- **[CLI Guide](docs/cli.md)**: Master the `taskforce` command.
- **[REST API Guide](docs/api.md)**: Integrating Taskforce into your apps.
- **[Profiles & Config](docs/profiles.md)**: Managing dev/prod environments.
- **[Long-Term Memory](docs/features/longterm-memory.md)**: Session-persistent knowledge graphs.

---

## 🛠 Development

### Run Tests
```powershell
uv run pytest
uv run pytest --cov=taskforce --cov-report=html
```

### Code Quality
```powershell
uv run black src/taskforce tests
uv run ruff check src/taskforce tests
uv run mypy src/taskforce
```

## 📜 License
MIT - see [LICENSE](LICENSE) for details.
