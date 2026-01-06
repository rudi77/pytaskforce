# Architecture Overview

Taskforce is designed using **Clean Architecture** (also known as Hexagonal or Onion Architecture). This ensures that the core business logic is isolated from external dependencies like databases, LLM providers, and APIs.

## 📐 Layer Structure

The system is organized into four distinct layers:

1.  **[Core Layer](architecture/section-5-components.md)**: Pure business logic (Agent ReAct loop, TodoList logic). Zero dependencies on external libraries.
2.  **[Infrastructure Layer](architecture/section-5-components.md)**: External integrations (PostgreSQL, LiteLLM, Tool implementations).
3.  **[Application Layer](architecture/section-5-components.md)**: Orchestration and Dependency Injection (Agent Factory, Executor).
4.  **[API Layer](architecture/section-5-components.md)**: Entrypoints (Typer CLI, FastAPI REST routes).

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

