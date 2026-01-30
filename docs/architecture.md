# Architecture Overview

Taskforce is designed using **Clean Architecture** (also known as Hexagonal or Onion Architecture). This ensures that the core business logic is isolated from external dependencies like databases, LLM providers, and APIs.

## 📐 Layer Structure

The system is organized into four distinct layers:

1.  **[Core Layer](architecture/section-5-components.md)**: Pure business logic (Agent ReAct loop, TodoList logic). Zero dependencies on external libraries.
2.  **[Infrastructure Layer](architecture/section-5-components.md)**: External integrations (PostgreSQL, LiteLLM, Tool implementations).
3.  **[Application Layer](architecture/section-5-components.md)**: Orchestration and Dependency Injection (Agent Factory, Executor).
4.  **[API Layer](architecture/section-5-components.md)**: Entrypoints (Typer CLI, FastAPI REST routes).

## 🔄 Unified Agent Architecture (2026-01 Refactoring)

The agent definition system has been unified to provide a single, consistent model for all agent types:

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **AgentDefinition** | `core/domain/agent_definition.py` | Unified model for all agent types (custom, profile, plugin, command) |
| **AgentRegistry** | `application/agent_registry.py` | Aggregates agents from all sources with unified CRUD API |
| **ToolResolver** | `application/tool_resolver.py` | Resolves tool names to instances with dependency injection |
| **InfrastructureBuilder** | `application/infrastructure_builder.py` | Builds state managers, LLM providers, and MCP tools |
| **ConfigSchema** | `core/domain/config_schema.py` | Pydantic validation for agent and profile configs |

### Agent Sources

```
AgentSource (Enum)
├── CUSTOM   → configs/custom/*.yaml (mutable, user-created)
├── PROFILE  → configs/*.yaml (read-only, project config)
├── PLUGIN   → examples/, plugins/ (read-only, external)
└── COMMAND  → .taskforce/commands/**/*.md (read-only, slash commands)
```

### Tool Configuration

Tools are now configured as **string lists only** (no dict format):

```yaml
# ✅ New unified format
tools:
  - python
  - file_read
  - web_search

# ❌ Legacy dict format (deprecated)
tools:
  - type: PythonTool
    module: taskforce.infrastructure.tools.native.python_tool
```

### Factory API

The `AgentFactory` now provides a unified `create()` method:

```python
from taskforce.core.domain.agent_definition import AgentDefinition
from taskforce.application.factory import AgentFactory

definition = AgentDefinition.from_custom(
    agent_id="my-agent",
    name="My Agent",
    tools=["python", "file_read"],
)

factory = AgentFactory()
agent = await factory.create(definition)
```

## 🤝 Multi-Agent Runtime & Messaging (2026-02)

Taskforce supports long-running, multi-agent workflows with clean separation between
core interfaces and infrastructure adapters:

- **Message Bus Protocols** live in `core/interfaces` and provide publish/subscribe
  contracts for queue-backed coordination.
- **Infrastructure Adapters** live under `taskforce_extensions/infrastructure/` and
  include in-memory message buses plus file-backed runtime stores.
- **Runtime Tracking** records heartbeats and checkpoints to support recovery and
  long-lived sessions.
- **Sub-Agent Spawning** uses a dedicated spawner to create isolated sessions for
  planners and specialist workers.

See **[Epic Orchestration](architecture/epic-orchestration.md)** for the
planner → worker → judge pipeline.

## 📊 Architecture Diagrams

For visual representations of the architecture, see **[Architecture Diagrams](architecture/architecture-diagrams.md)** which includes:
- High-Level Layer Architecture (Clean Architecture)
- Component Dependency Diagram
- ReAct Loop Execution Flow (Sequence Diagram)
- Tool Ecosystem Overview
- State Management & Persistence
- Configuration System (including Unified Agent Model)
- MCP Server Integration
- API Layer Architecture
- Complete System Overview
- Import Rules & Layer Dependencies

## Agent Skills System (2026-01)

The Skills System provides modular, domain-specific capabilities that extend agent functionality. Skills follow Clean Architecture principles with strict layer separation.

```
┌─────────────────────────────────────────────────────────────┐
│                    System Prompt                             │
│  ┌─────────────────┐  ┌─────────────────────────────────┐   │
│  │ Available Skills │  │ Active Skills (full instructions)│   │
│  │ (metadata only)  │  │ Loaded on-demand when triggered  │   │
│  └─────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Skill Service                           │
│  • Discovery & Registration    • Activation Management       │
│  • Resource Access             • Prompt Section Generation   │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     ~/.taskforce/    .taskforce/skills/   taskforce_extensions/
        skills/       (project-level)         skills/
     (user-level)                          (built-in)
```

### Progressive Loading Pattern

Skills use three-level loading to minimize token usage:

| Level | Content | Loaded When | Token Cost |
|-------|---------|-------------|------------|
| 1 | Metadata (name, description) | Discovery | ~100 tokens/skill |
| 2 | Instructions (SKILL.md body) | Skill triggered | <5k tokens |
| 3 | Resources (scripts, templates) | On-demand | Unlimited |

### Available Built-in Skills

- **code-review**: Structured code analysis for bugs, security, and quality
- **data-analysis**: EDA, statistical analysis, and visualization
- **documentation**: Technical documentation creation
- **pdf-processing**: PDF manipulation with bundled Python scripts

See **[Skills Documentation](features/skills.md)** for creating custom skills.

## Plugin System (2026-01)

Taskforce verwendet ein Entry-Point-basiertes Plugin-System für Erweiterbarkeit:

```
taskforce (Base)              taskforce-enterprise (Optional)
      │                                │
      │  ◄──── Entry Points ────────  │
      │                                │
      ▼                                ▼
┌─────────────────┐          ┌─────────────────┐
│ Plugin Discovery│  ◄────── │ EnterprisePlugin│
│ Plugin Registry │          │ Auth Middleware │
│ Factory Extens. │          │ Admin Routes    │
└─────────────────┘          └─────────────────┘
```

Siehe **[Plugin System Architecture](architecture/plugin-system.md)** für Details.

## Enterprise Capabilities (Optional)

> **Hinweis**: Enterprise-Features sind als separates Paket `taskforce-enterprise` verfügbar.
> Nach Installation werden Features automatisch via Plugin-Discovery aktiviert.

```bash
pip install taskforce-enterprise
```

| Capability | Components | Paket |
|------------|------------|-------|
| **Identity & RBAC** | TenantContext, UserContext, PolicyEngine | `taskforce-enterprise` |
| **Admin API** | /api/v1/admin/users, roles, tenants | `taskforce-enterprise` |
| **Evidence Tracking** | Evidence, RAGCitations | `taskforce-enterprise` |
| **Memory Governance** | Encryption, MemoryACL | `taskforce-enterprise` |
| **Operations** | Metrics, Usage, Cost, Compliance | `taskforce-enterprise` |

Siehe **[Enterprise Features](features/enterprise.md)** und **[ADR-003](adr/adr-003-enterprise-transformation.md)** für Details.

## 📄 Detailed Documentation

The architecture documentation is sharded into specialized sections:

- **[Introduction & Goals](architecture/section-1-introduction.md)**
- **[High-Level Architecture](architecture/section-2-high-level-architecture.md)**
- **[Tech Stack](architecture/section-3-tech-stack.md)**
- **[Data Models](architecture/section-4-data-models-revised-python.md)**
- **[Components & Layers](architecture/section-5-components.md)**
- **[External APIs](architecture/section-6-external-apis.md)**
- **[Core Workflows](architecture/section-7-core-workflows.md)**
- **[Security](architecture/section-8-security.md)**
- **[Performance & Scalability](architecture/section-9-performance-scalability.md)**
- **[Deployment](architecture/section-10-deployment.md)**
- **[Testing Strategy](architecture/section-11-testing-strategy.md)**

## 📜 Legacy Reference

> [!NOTE]
> There is a legacy monolithic architecture file at `docs/architecutre.md` (note the typo). This file is kept for historical reference but is superseded by the sharded documentation linked above.

---
*For a high-level view of the source tree, see [docs/architecture/source-tree.md](architecture/source-tree.md).*
