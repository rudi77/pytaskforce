# Taskforce Documentation

Welcome to the Taskforce documentation. Taskforce is a production-grade multi-agent orchestration framework built with Clean Architecture principles.

## 🗺 Documentation Map

### 🚀 Getting Started
- **[Setup & Installation](setup.md)**: How to get Taskforce running on your machine.
- **[CLI Guide](cli.md)**: Comprehensive guide to the `taskforce` command-line tool.
- **[Slash Commands](slash-commands.md)**: Extending the chat interface with custom commands.
- **[Plugin Development](plugins.md)**: Creating and loading custom agent plugins.
- **[REST API Guide](api.md)**: Integrating Taskforce via FastAPI and OpenAPI.
- **[Integration Guide](integration-guide.md)**: Embed Taskforce as library, CLI, or webservice (sidecar/embedded) — start here if you're building an app on top of Taskforce.
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
- **[Generative Dreaming](features/generative-dreaming.md)**: Offline generative consolidation loop (ADR-014).
- **[Agent Communication Protocol (ACP)](features/acp.md)**: Invoke remote agents over the IBM/Linux Foundation ACP (ADR-018).

### 🏢 Enterprise Extension Model
- **[Enterprise Integration Surface](features/enterprise.md)**: What remains in core (`pytaskforce`) and how external enterprise packages integrate via interfaces, middleware, and UI manifests.

### Optional Agent Packages
Agent-specific capabilities live in separate packages under `agents/` and are
wired into the unified CLI when installed. See [Profiles & Config](profiles.md)
for the full profile list.

- **[Butler Roles](features/butler-roles.md)**: `taskforce-butler` role specialization (accountant, personal assistant).
- **Coding Agent** (`taskforce-coding-agent`): Epic orchestration and coding sub-agents — see [Epic Orchestration](architecture/epic-orchestration.md).
- **RAG Agent** (`taskforce-rag-agent`): Azure AI Search tools and the `rag_agent` profile.

### Development & Community
- **[Testing Guide](testing.md)**: How to run and write tests for Taskforce.
- **[Examples & Tutorials](examples.md)**: Real-world use cases and code samples.
- **[Contributing](https://github.com/rudi77/pytaskforce)**: Join the development on GitHub.

---

*Note: This documentation is maintained in Markdown format directly within the repository.*
