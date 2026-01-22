# Taskforce Documentation

Welcome to the Taskforce documentation. Taskforce is a production-grade multi-agent orchestration framework built with Clean Architecture principles.

## 🗺 Documentation Map

### 🚀 Getting Started
- **[Setup & Installation](setup.md)**: How to get Taskforce running on your machine.
- **[CLI Guide](cli.md)**: Comprehensive guide to the `taskforce` command-line tool.
- **[Slash Commands](slash-commands.md)**: Extending the chat interface with custom commands.
- **[Plugin Development](plugins.md)**: Creating and loading custom agent plugins.
- **[REST API Guide](api.md)**: Integrating Taskforce via FastAPI and OpenAPI.

### 🏗 Architecture & Design
- **[Architecture Overview](architecture.md)**: The core design principles and layer structure.
- **[Plugin System](architecture/plugin-system.md)**: Entry-Point-basiertes Erweiterungssystem.
- **[Configuration Profiles](profiles.md)**: Managing dev, staging, and production settings.
- **[ADRs (Architecture Decision Records)](adr/index.md)**: Why we made certain technical choices.

### 🏢 Enterprise Features (Optional)
> Enterprise-Features sind als separates Paket `taskforce-enterprise` verfügbar.
> Installation: `pip install taskforce-enterprise` - Features werden automatisch aktiviert.

- **[Enterprise Features](features/enterprise.md)**: Multi-tenant identity, RBAC, compliance, and governance.
- **[Long-Term Memory](features/longterm-memory.md)**: Persistent knowledge graph memory for agents.

### 🛠 Development & Community
- **[Testing Guide](testing.md)**: How to run and write tests for Taskforce.
- **[Examples & Tutorials](examples.md)**: Real-world use cases and code samples.
- **[Contributing](https://github.com/rudi77/pytaskforce)**: Join the development on GitHub.

---

*Note: This documentation is maintained in Markdown format directly within the repository.*

