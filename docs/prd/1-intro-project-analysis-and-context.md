# 1. Intro Project Analysis and Context

### Analysis Source
**IDE-based fresh analysis** with reference to existing brownfield-architecture.md documentation

### Current Project State

Based on analysis of the Agent V2 codebase (`capstone/agent_v2`):

**Current Capabilities:**
- **ReAct Execution Engine**: Thought → Action → Observation loop orchestrating LLM-driven reasoning
- **TodoList Planning**: LLM-based task decomposition with dependency tracking (`planning/todolist.py`)
- **Tool System**: 11+ tools including Python execution, file I/O, Git operations, web search, RAG semantic search
- **State Management**: File-based session persistence via `statemanager.py` with async I/O
- **Rich CLI Interface**: Typer-based CLI with 8 command groups (run, chat, missions, tools, sessions, rag, config, dev)
- **Multi-Provider LLM Support**: OpenAI and Azure OpenAI via LiteLLM abstraction (`services/llm_service.py`)
- **Agent Specialization**: Factory methods for generic agents and RAG agents with different system prompts
- **Memory System**: Cross-session learning via memory extraction (`memory/memory_manager.py`)

**Current Architecture (PoC Flat Structure):**
```
capstone/agent_v2/
├── agent.py                    # Core ReAct loop + factory (220 lines)
├── agent_factory.py            # Agent construction
├── statemanager.py             # File-based persistence
├── tool.py                     # Base tool class
├── planning/todolist.py        # Planning logic + persistence
├── services/llm_service.py     # LLM abstraction
├── tools/*.py                  # 11+ tool implementations
├── cli/                        # CLI interface (separate concern)
└── agent_service/              # Empty placeholder for microservice
```

**Key Observation:** The `agent_service/` directory structure (with `api/`, `core/`, `db/`, `models/` subdirectories) already exists but contains no implementation files - indicating the structure was scaffolded but the migration has not been executed.

### Available Documentation Analysis

**Available Documentation:**
- ✅ **Tech Stack Documentation**: Fully documented in `docs/brownfield-architecture.md` (Python 3.11, LiteLLM, Typer, Rich, structlog, Azure AI Search)
- ✅ **Source Tree/Architecture**: Comprehensive current-state documentation available (brownfield-architecture.md with 1,345 lines)
- ⚠️ **Coding Standards**: Partially documented via `.cursor/rules/python_coding_rules.mdc` and CLAUDE.md (PEP8, Black/Ruff, functional style, ≤30 line functions)
- ✅ **API Documentation**: Module docstrings and inline comments present in core files
- ⚠️ **External API Documentation**: Azure AI Search integration documented, some tool APIs partially documented
- ❌ **UX/UI Guidelines**: Not applicable (CLI and API only)
- ⚠️ **Technical Debt Documentation**: Scattered comments in brownfield-architecture.md about isolated Python namespaces and tool execution constraints
- ✅ **Clean Architecture Target**: User-provided detailed specification in the conversation (Hexagonal Architecture with core/infrastructure/application/api layers)

**Assessment:** The existing documentation provides excellent "as-is" analysis. The user's provided specification gives a clear "to-be" target architecture. This PRD will bridge the gap by defining the migration path.

### Enhancement Scope Definition

**Enhancement Type:**
- ☑️ **Technology Stack Upgrade** (architectural pattern upgrade)
- ☑️ **Major Feature Modification** (refactoring for production-readiness)

**Enhancement Description:**

Create the **Taskforce production framework** in a new top-level directory (`taskforce/`) by reorganizing and adapting proven code from Agent V2 (`capstone/agent_v2`) into a **production-ready microservice architecture** based on **Clean Architecture / Hexagonal Architecture** principles. The refactoring enforces strict separation of concerns by organizing code into four distinct layers:

1. **Core Layer** (domain logic): Pure business logic with zero dependencies on infrastructure
2. **Infrastructure Layer** (adapters): Database, LLM providers, tool implementations
3. **Application Layer** (use cases): Service orchestration and dependency injection via factory
4. **API Layer** (entrypoints): FastAPI REST API and CLI interfaces

The implementation maximizes code reuse from Agent V2 (≥75% of working logic relocated rather than rewritten) while establishing architectural boundaries that enable independent evolution of the agent engine, persistence layer, tool ecosystem, and API interfaces.

**Impact Assessment:** ☑️ **Major Impact (architectural changes required)**

**Rationale:**
- New directory structure at `taskforce/` with Clean Architecture layers (core, infrastructure, application, api)
- Agent V2 remains untouched - serves as reference implementation and operational fallback
- All existing modules require relocation to appropriate layers with protocol-based interfaces
- File-based `StateManager` coexists with new database-backed `DbStateManager` via shared protocol
- Agent factory evolves into comprehensive dependency injection container
- FastAPI service layer requires full implementation for microservice deployment
- Extensive test suite adapted to new module structure with protocol-based mocking
- **However:** The core ReAct algorithm, TodoList logic, and tool execution semantics remain unchanged - this is code reorganization with maximum reuse, not reimplementation

### Goals and Background Context

**Goals:**
- **G1:** Establish strict architectural boundaries preventing domain logic from depending on infrastructure (database, external APIs)
- **G2:** Enable swappable persistence backends (file-based for dev, PostgreSQL for production) via protocol-based abstractions
- **G3:** Support microservice deployment via production-ready FastAPI REST API with observability (logging, metrics, health checks)
- **G4:** Maintain 100% backward compatibility for CLI users through similar command structure
- **G5:** Improve testability by isolating core domain logic from I/O operations via protocol mocking
- **G6:** Prepare codebase for enterprise deployment with clear extension points for new tools, LLM providers, and persistence adapters

**Background Context:**

The current Agent V2 codebase is a successful **Proof of Concept** demonstrating ReAct agent capabilities with TodoList planning, tool execution, and state management. However, the flat module structure exhibits typical PoC characteristics:

1. **Tightly Coupled Layers**: `agent.py` (domain logic) directly imports `statemanager.py` (infrastructure), making it impossible to swap persistence backends without modifying core logic.

2. **Testability Challenges**: Testing the ReAct loop requires actual file I/O, LLM API calls, and tool execution - no clean seams for mocking.

3. **Circular Dependency Risk**: The factory imports everything, tools import helpers, and helpers import domain classes, creating fragile dependency graphs.

4. **Deployment Inflexibility**: The current structure doesn't support running as a stateless microservice - it assumes local filesystem access for state persistence.

**Why Clean Architecture / Hexagonal Architecture?**

The user correctly identified that for **production-grade enterprise deployment**, the system requires:

- **"Separation of Concerns"**: Core business logic must not know about PostgreSQL, FastAPI, or specific LLM providers
- **Testability**: The domain should be testable with zero external dependencies
- **Swappable Adapters**: Switch from file-based state to database state with configuration changes only
- **Extension Points**: Add MCP tool integration, new LLM providers, or API authentication without touching domain code
- **Team Scalability**: Multiple developers can work on API layer, tool implementations, and core logic independently

The migration to Clean Architecture transforms the codebase from a "working prototype" to an "enterprise-grade microservice" suitable for long-term maintenance and multi-team development. By creating Taskforce as a new framework rather than refactoring Agent V2 in place, we eliminate risk to the operational PoC while applying lessons learned.

### Change Log

| Change | Date | Version | Description | Author |
|--------|------|---------|-------------|--------|
| Initial PRD | 2025-11-22 | 1.0 | Clean Architecture migration planning | John (PM Agent) |

---
