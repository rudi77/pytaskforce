# Taskforce Documentation

Welcome to the Taskforce documentation. Taskforce is a production-grade multi-agent orchestration framework built with Clean Architecture principles.

## 🗺 Documentation Map

### 🚀 Getting Started
- **[Setup & Installation](setup.md)**: How to get Taskforce running on your machine.
- **[CLI Guide](cli.md)**: Comprehensive guide to the `taskforce` command-line tool.
- **[Slash Commands](slash-commands.md)**: Extending the chat interface with custom commands.
- **[Plugin Development](plugins.md)**: Creating and loading custom agent plugins.
- **[REST API Guide](api.md)**: Integrating Taskforce via FastAPI and OpenAPI.
- **[External Integrations](integrations.md)**: Connect Taskforce to Telegram or MS Teams.

### 🏗 Architecture & Design
- **[Architecture Overview](architecture.md)**: The core design principles and layer structure.
- **[Epic Orchestration](architecture/epic-orchestration.md)**: Planner → worker → judge workflow.
- **[Sub-Agent Communication](architecture/sub-agent-communication.md)**: Technischer Deep-Dive: Session-Hierarchie, State-Isolation, Datenfluss.
- **[Plugin System](architecture/plugin-system.md)**: Entry-Point-basiertes Erweiterungssystem.
- **[Configuration Profiles](profiles.md)**: Managing profiles and configuration settings.
- **[ADRs (Architecture Decision Records)](adr/index.md)**: Why we made certain technical choices.

### 🧠 Agent Capabilities
- **[Sub-Agent Orchestration](features/sub-agent-orchestration.md)**: Aufgaben an spezialisierte Sub-Agents delegieren (Tool-Config, Patterns, Fehlerbehandlung).
- **[Agent Skills](features/skills.md)**: Modular domain-specific capabilities for agents (code review, data analysis, PDF processing).
- **[Long-Term Memory](features/longterm-memory.md)**: Persistent Markdown-based memory for agents.
- **[Memory Consolidation](features/memory-consolidation.md)**: LLM-powered experience consolidation into long-term memory.

### 🏢 Enterprise Features (Optional)
> Enterprise-Features sind als separates Paket `taskforce-enterprise` verfügbar.
> Installation: `pip install taskforce-enterprise` - Features werden automatisch aktiviert.

- **[Enterprise Features](features/enterprise.md)**: Multi-tenant identity, RBAC, compliance, and governance.

### Butler Agent
- **[Butler Roles](features/butler-roles.md)**: Butler agent role specialization (accountant, personal assistant).

### Development & Community
- **[Testing Guide](testing.md)**: How to run and write tests for Taskforce.
- **[Examples & Tutorials](examples.md)**: Real-world use cases and code samples.
- **[Contributing](https://github.com/rudi77/pytaskforce)**: Join the development on GitHub.

---

*Note: This documentation is maintained in Markdown format directly within the repository.*
