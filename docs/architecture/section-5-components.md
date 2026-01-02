# Section 5: Components

Based on the Clean Architecture patterns, tech stack, and data models, here are the major components of Taskforce organized by layer:

---

### **Core Layer Components**

#### **Agent (Core Domain)**

**Responsibility:** Implements the ReAct (Reason + Act) execution loop. Pure business logic orchestrating thought generation, action decisions, and observation recording. Zero infrastructure dependencies.

**Key Interfaces:**
- `execute(mission: str, session_id: str) -> ExecutionResult` - Main execution entry point
- `_generate_thought() -> str` - LLM-based reasoning step
- `_decide_action(thought: str) -> Action` - Action selection logic
- `_execute_action(action: Action) -> Observation` - Delegates to tool execution
- `_should_continue() -> bool` - Loop termination conditions

**Dependencies:**
- `StateManagerProtocol` (injected) - For state persistence
- `LLMProviderProtocol` (injected) - For thought generation
- `Dict[str, ToolProtocol]` (injected) - For tool execution
- `TodoListManagerProtocol` (injected) - For plan management

**Technology Stack:** Pure Python 3.11, dataclasses, asyncio

**Code Location:** `taskforce/src/taskforce/core/domain/agent.py`

---

#### **PlanGenerator (Core Domain)**

**Responsibility:** Generates TodoList plans from mission descriptions using LLM-based decomposition. Validates task dependencies and ensures plan coherence.

**Key Interfaces:**
- `generate_plan(mission: str) -> TodoList` - Creates structured plan from mission text
- `validate_dependencies(plan: TodoList) -> bool` - Ensures no circular dependencies
- `update_task_status(item: TodoItem, status: TaskStatus) -> None` - Updates task execution state

**Dependencies:**
- `LLMProviderProtocol` (injected) - For plan generation prompts

**Technology Stack:** Pure Python 3.11, dataclasses for TodoList/TodoItem

**Code Location:** `taskforce/src/taskforce/core/domain/plan.py`

---

#### **Domain Events (Core Domain)**

**Responsibility:** Immutable event objects representing key moments in agent execution. Enable event-driven architecture and progress tracking.

**Key Interfaces:**
- `Thought(session_id, step_id, content, timestamp)` - Reasoning event
- `Action(session_id, step_id, action_type, action_data, timestamp)` - Decision event  
- `Observation(session_id, step_id, result, success, error, timestamp)` - Result event

**Dependencies:** None (pure dataclasses)

**Technology Stack:** Python dataclasses (frozen=True for immutability)

**Code Location:** `taskforce/src/taskforce/core/domain/events.py`

---

### **Core Interface Components (Protocols)**

#### **StateManagerProtocol**

**Responsibility:** Defines contract for session state persistence. Enables swappable file-based and database-backed implementations.

**Key Interfaces:**
```python
async def save_state(session_id: str, state_data: Dict[str, Any]) -> None
async def load_state(session_id: str) -> Optional[Dict[str, Any]]
async def delete_state(session_id: str) -> None
async def list_sessions() -> List[str]
```

**Dependencies:** None (protocol definition)

**Technology Stack:** Python Protocol (PEP 544)

**Code Location:** `taskforce/src/taskforce/core/interfaces/state.py`

---

#### **LLMProviderProtocol**

**Responsibility:** Defines contract for LLM completions. Abstracts OpenAI, Azure OpenAI, and future providers.

**Key Interfaces:**
```python
async def complete(model: str, messages: List[Dict], **params) -> Dict[str, Any]
async def generate(model: str, prompt: str, **params) -> str
```

**Dependencies:** None (protocol definition)

**Technology Stack:** Python Protocol (PEP 544)

**Code Location:** `taskforce/src/taskforce/core/interfaces/llm.py`

---

#### **ToolProtocol**

**Responsibility:** Defines contract for tool execution. All tools (Python, File, Git, Web, RAG) implement this interface.

**Key Interfaces:**
```python
@property
def name() -> str

@property  
def description() -> str

@property
def parameters_schema() -> Dict[str, Any]

async def execute(**params) -> Dict[str, Any]
def validate_parameters(params: Dict[str, Any]) -> bool
```

**Dependencies:** None (protocol definition)

**Technology Stack:** Python Protocol (PEP 544)

**Code Location:** `taskforce/src/taskforce/core/interfaces/tools.py`

---

### **Infrastructure Layer Components**

#### **FileStateManager**

**Responsibility:** File-based state persistence for development. Stores session state as JSON files with async I/O and versioning.

**Key Interfaces:** Implements `StateManagerProtocol`

**Dependencies:**
- `aiofiles` - Async file operations
- File system at `{work_dir}/states/{session_id}.json`

**Technology Stack:** Python 3.11, aiofiles, asyncio, JSON serialization

**Code Location:** `taskforce/src/taskforce/infrastructure/persistence/file_state.py`

---

#### **DbStateManager**

**Responsibility:** PostgreSQL-based state persistence for production. Stores state in relational tables with JSONB columns.

**Key Interfaces:** Implements `StateManagerProtocol`

**Dependencies:**
- `asyncpg` - Async PostgreSQL driver
- `SQLAlchemy 2.0` - ORM and query builder
- PostgreSQL database connection

**Technology Stack:** Python 3.11, SQLAlchemy async, asyncpg, PostgreSQL 15

**Code Location:** `taskforce/src/taskforce/infrastructure/persistence/db_state.py`

---

#### **OpenAIService (LLM Service)**

**Responsibility:** LLM service supporting OpenAI and Azure OpenAI via LiteLLM. Handles model aliases, parameter mapping (GPT-4 vs GPT-5), retry logic, token logging.

**Key Interfaces:** Implements `LLMProviderProtocol`

**Dependencies:**
- `litellm` - Multi-provider LLM client
- `llm_config.yaml` - Model configuration
- Environment variables: `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`

**Technology Stack:** Python 3.11, LiteLLM 1.7.7.0, async/await

**Code Location:** `taskforce/src/taskforce/infrastructure/llm/openai_service.py`

---

#### **Native Tools (Infrastructure)**

**Responsibility:** Core tool implementations relocated from Agent V2. Each tool implements `ToolProtocol` with preserved execution semantics.

**Key Interfaces:**
- **PythonTool**: Executes Python code in isolated namespace
- **FileReadTool / FileWriteTool**: File system operations
- **GitTool / GitHubTool**: Git operations and GitHub API
- **PowerShellTool**: Shell command execution (Windows-first)
- **WebSearchTool / WebFetchTool**: HTTP requests and web scraping
- **LLMTool**: Nested LLM calls for sub-tasks
- **AskUserTool**: User interaction via CLI or API

**Dependencies:**
- Various: subprocess, aiohttp, GitPython, etc. (tool-specific)

**Technology Stack:** Python 3.11, async/await, tool-specific libraries

**Code Location:** `taskforce/src/taskforce/infrastructure/tools/native/*.py`

---

#### **RAG Tools (Infrastructure)**

**Responsibility:** Azure AI Search integration for semantic search and document retrieval. Supports RAG agent capabilities.

**Key Interfaces:**
- **SemanticSearchTool**: Vector search in Azure AI Search index
- **ListDocumentsTool**: Document listing with metadata
- **GetDocumentTool**: Document retrieval by ID

**Dependencies:**
- `azure-search-documents` SDK - Azure AI Search client
- Azure AI Search index (external service)
- Environment variables: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`

**Technology Stack:** Python 3.11, Azure AI Search SDK 11.4+, async/await

**Code Location:** `taskforce/src/taskforce/infrastructure/tools/rag/*.py`

---

### **Application Layer Components**

#### **AgentFactory**

**Responsibility:** Dependency injection container. Reads configuration profiles (dev/staging/prod) and wires domain objects with appropriate infrastructure adapters.

**Key Interfaces:**
- `create_agent(profile: str = "dev") -> Agent` - Creates generic agent
- `create_rag_agent(profile: str = "dev") -> Agent` - Creates RAG-enabled agent
- `_create_state_manager(config: dict) -> StateManagerProtocol` - Instantiates persistence adapter
- `_create_llm_provider(config: dict) -> LLMProviderProtocol` - Instantiates LLM service
- `_create_tools(config: dict) -> List[ToolProtocol]` - Instantiates tool implementations

**Dependencies:**
- All infrastructure adapters (FileStateManager, DbStateManager, OpenAIService, Tools)
- Core domain classes (Agent, PlanGenerator)
- YAML configuration files

**Technology Stack:** Python 3.11, PyYAML, dataclasses

**Code Location:** `taskforce/src/taskforce/application/factory.py`

---

#### **AgentExecutor**

**Responsibility:** Service orchestrating agent execution. Shared logic for CLI and API entrypoints. Handles logging, error handling, state persistence, progress callbacks.

**Key Interfaces:**
- `execute_mission(mission: str, profile: str, session_id: Optional[str]) -> ExecutionResult` - Synchronous execution
- `execute_mission_streaming(mission: str, profile: str) -> AsyncIterator[ProgressUpdate]` - Streaming execution with progress events

**Dependencies:**
- `AgentFactory` - For agent creation
- Core domain `Agent` - For ReAct loop execution
- `structlog` - For structured logging

**Technology Stack:** Python 3.11, structlog, asyncio, async generators

**Code Location:** `taskforce/src/taskforce/application/executor.py`

---

#### **ProfileLoader**

**Responsibility:** Loads and validates YAML configuration profiles. Manages environment variable overrides.

**Key Interfaces:**
- `load_profile(profile_name: str) -> dict` - Loads configuration from YAML
- `validate_profile(config: dict) -> None` - Validates required fields
- `merge_env_overrides(config: dict) -> dict` - Applies environment variable overrides

**Dependencies:**
- `PyYAML` - YAML parsing
- `Pydantic` - Configuration validation
- Configuration files: `configs/dev.yaml`, `configs/staging.yaml`, `configs/prod.yaml`

**Technology Stack:** Python 3.11, PyYAML, Pydantic

**Code Location:** `taskforce/src/taskforce/application/profiles.py`

---

### **API Layer Components**

#### **FastAPI REST Service**

**Responsibility:** HTTP REST API for programmatic access. Exposes agent execution, session management, health checks.

**Key Interfaces:**
- `POST /api/v1/execute` - Execute mission synchronously
- `POST /api/v1/execute/stream` - Execute mission with streaming (SSE)
- `GET /api/v1/sessions` - List sessions
- `GET /api/v1/sessions/{session_id}` - Get session details
- `POST /api/v1/sessions` - Create session
- `GET /health` - Liveness probe
- `GET /health/ready` - Readiness probe (checks DB connectivity)

**Dependencies:**
- `AgentExecutor` - For mission execution
- `AgentFactory` - For session state access
- `Pydantic` - Request/response validation

**Technology Stack:** FastAPI 0.116+, uvicorn 0.25+, Pydantic 2.0+

**Code Location:** `taskforce/src/taskforce/api/server.py`, `taskforce/src/taskforce/api/routes/*.py`

---

#### **Typer CLI**

**Responsibility:** Command-line interface for developers. Adapted from Agent V2 CLI structure with Rich terminal output.

**Key Interfaces:**
- `taskforce run mission <description>` - Execute mission
- `taskforce chat` - Interactive chat mode
- `taskforce tools list` - List available tools
- `taskforce tools inspect <tool-name>` - Show tool details
- `taskforce sessions list` - List sessions
- `taskforce sessions show <session-id>` - Show session details
- `taskforce config show` - Show configuration

**Dependencies:**
- `AgentExecutor` - For mission execution
- `AgentFactory` - For agent creation
- `Typer` - CLI framework
- `Rich` - Terminal UI (progress bars, tables, colors)

**Technology Stack:** Typer 0.9+, Rich 13.0+, asyncio

**Code Location:** `taskforce/src/taskforce/api/cli/main.py`, `taskforce/src/taskforce/api/cli/commands/*.py`

---

### **Component Diagram**

```mermaid
C4Component
    title Taskforce Component Architecture (Clean Architecture Layers)
    
    Container_Boundary(api, "API Layer") {
        Component(cli, "Typer CLI", "Python, Typer, Rich", "Command-line interface")
        Component(rest, "FastAPI REST", "Python, FastAPI", "HTTP API endpoints")
    }
    
    Container_Boundary(app, "Application Layer") {
        Component(executor, "AgentExecutor", "Python", "Orchestrates execution")
        Component(factory, "AgentFactory", "Python", "Dependency injection")
        Component(profiles, "ProfileLoader", "Python, PyYAML", "Config management")
    }
    
    Container_Boundary(core, "Core Layer") {
        Component(agent, "Agent", "Python, Pure Logic", "ReAct loop execution")
        Component(planner, "PlanGenerator", "Python, Pure Logic", "TodoList planning")
        Component(events, "Domain Events", "Python, Dataclasses", "Thought/Action/Observation")
    }
    
    Container_Boundary(protocols, "Core Interfaces") {
        Component(state_proto, "StateManagerProtocol", "Python Protocol", "State persistence contract")
        Component(llm_proto, "LLMProviderProtocol", "Python Protocol", "LLM provider contract")
        Component(tool_proto, "ToolProtocol", "Python Protocol", "Tool execution contract")
    }
    
    Container_Boundary(infra, "Infrastructure Layer") {
        Component(file_state, "FileStateManager", "Python, aiofiles", "File-based persistence")
        Component(db_state, "DbStateManager", "Python, SQLAlchemy", "Database persistence")
        Component(llm_svc, "OpenAIService", "Python, LiteLLM", "LLM integration")
        Component(tools, "Native Tools", "Python", "11+ tool implementations")
        Component(rag_tools, "RAG Tools", "Python, Azure SDK", "Semantic search tools")
    }
    
    Container_Boundary(external, "External Systems") {
        ComponentDb(postgres, "PostgreSQL", "Database", "Production state storage")
        Component(openai, "OpenAI API", "External", "LLM provider")
        Component(azure_search, "Azure AI Search", "External", "Vector search")
    }
    
    Rel(cli, executor, "Uses")
    Rel(rest, executor, "Uses")
    
    Rel(executor, factory, "Creates agents via")
    Rel(factory, profiles, "Loads config from")
    
    Rel(factory, agent, "Instantiates")
    Rel(factory, planner, "Instantiates")
    
    Rel(agent, state_proto, "Depends on")
    Rel(agent, llm_proto, "Depends on")
    Rel(agent, tool_proto, "Depends on")
    Rel(planner, llm_proto, "Depends on")
    
    Rel(state_proto, file_state, "Implemented by", "dev profile")
    Rel(state_proto, db_state, "Implemented by", "prod profile")
    Rel(llm_proto, llm_svc, "Implemented by")
    Rel(tool_proto, tools, "Implemented by")
    Rel(tool_proto, rag_tools, "Implemented by")
    
    Rel(file_state, "File System", "Writes to")
    Rel(db_state, postgres, "Writes to")
    Rel(llm_svc, openai, "Calls")
    Rel(rag_tools, azure_search, "Queries")
```

---

### **Rationale:**

**Component Organization Decisions:**

1. **Strict Layer Separation**: Components organized by layer (Core, Infrastructure, Application, API) with explicit dependency direction (inward). Rationale: Enforces Clean Architecture dependency rule - domain logic never depends on infrastructure.

2. **Protocol Layer as Boundary**: Separate protocol components defining all layer boundaries. Rationale: Makes dependencies explicit. Core depends on abstractions (protocols), not concrete implementations.

3. **Dual Entrypoints (CLI + API)**: Both share AgentExecutor service. Rationale: Single source of truth for execution logic. CLI and API are thin wrappers providing different interfaces to same functionality.

4. **AgentFactory as Wiring Hub**: Centralized dependency injection. Rationale: Makes dependency graph explicit and configurable. Single place to change infrastructure implementations.

5. **Tool Implementations in Infrastructure**: All 11+ tools in infrastructure layer, not core. Rationale: Tools perform I/O (subprocess, HTTP, file system). Core domain only knows ToolProtocol interface.

**Trade-offs:**

- **Many Small Components vs Few Large**: Chose many focused components over monolithic services. Trade-off: More files to navigate vs. clearer responsibilities.
- **Shared Executor vs Separate Services**: CLI and API share executor. Trade-off: Tight coupling between entrypoints vs. guaranteed behavioral consistency.
- **Protocol Overhead**: Every infrastructure component implements a protocol. Trade-off: More interface code vs. testability and flexibility.

🏗️ **Proceeding to External APIs...**

---
