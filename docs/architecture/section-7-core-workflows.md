# Section 7: Core Workflows

Key system workflows illustrating component interactions and data flow:

---

### **Workflow 1: Mission Execution via CLI (ReAct Loop)**

This workflow shows a complete mission execution from CLI command to completion, illustrating the ReAct (Reason + Act) loop.

```mermaid
sequenceDiagram
    actor User
    participant CLI as Typer CLI
    participant Executor as AgentExecutor
    participant Factory as AgentFactory
    participant Agent as Agent (Core)
    participant LLM as OpenAIService
    participant Tool as PythonTool
    participant State as FileStateManager
    
    User->>CLI: taskforce run mission "Create hello world"
    CLI->>Executor: execute_mission(mission, profile="dev")
    
    Executor->>Factory: create_agent(profile="dev")
    Factory->>State: new FileStateManager()
    Factory->>LLM: new OpenAIService()
    Factory->>Tool: new PythonTool()
    Factory->>Agent: new Agent(state, llm, [tools])
    Factory-->>Executor: agent
    
    Executor->>Agent: execute(mission, session_id)
    
    Note over Agent: ReAct Loop Iteration 1
    Agent->>State: load_state(session_id)
    State-->>Agent: None (new session)
    
    Agent->>LLM: complete("Generate thought for mission")
    LLM->>OpenAI API: POST /chat/completions
    OpenAI API-->>LLM: "I need to create a Python function..."
    LLM-->>Agent: Thought
    
    Agent->>Agent: decide_action(thought)
    Note over Agent: Decides to use PythonTool
    
    Agent->>Tool: execute(code="def hello(): print('Hello World')")
    Tool-->>Agent: Observation(success=true, output="Function created")
    
    Agent->>State: save_state(session_id, state_data)
    State-->>Agent: saved
    
    Note over Agent: ReAct Loop Iteration 2
    Agent->>LLM: complete("Evaluate if mission complete")
    LLM->>OpenAI API: POST /chat/completions
    OpenAI API-->>LLM: "Mission accomplished"
    LLM-->>Agent: Thought
    
    Agent->>Agent: decide_action(thought)
    Note over Agent: Decides to complete
    
    Agent-->>Executor: ExecutionResult(status="completed")
    Executor-->>CLI: result
    CLI-->>User: ✓ Mission completed!
```

---

### **Workflow 2: TodoList Plan Generation**

This workflow shows how a mission is decomposed into a structured TodoList with dependencies.

```mermaid
sequenceDiagram
    participant Agent as Agent (Core)
    participant Planner as PlanGenerator
    participant LLM as OpenAIService
    participant TodoMgr as FileTodoListManager
    participant State as FileStateManager
    
    Agent->>Planner: generate_plan(mission)
    
    Planner->>LLM: complete(prompt="Decompose mission into steps")
    Note over LLM: Uses planning system prompt<br/>with examples
    LLM->>OpenAI API: POST /chat/completions
    OpenAI API-->>LLM: JSON plan structure
    LLM-->>Planner: plan_json
    
    Planner->>Planner: parse_plan_json()
    Note over Planner: Creates TodoItem objects
    
    Planner->>Planner: validate_dependencies()
    alt Circular dependencies detected
        Planner-->>Agent: Error: Circular dependency
    else Valid plan
        Planner->>TodoMgr: save_plan(todolist)
        TodoMgr->>State: save to file system
        State-->>TodoMgr: saved
        TodoMgr-->>Planner: todolist_id
        Planner-->>Agent: TodoList(items, todolist_id)
    end
    
    Agent->>Agent: Set current_step = 0
    Note over Agent: Ready to execute first task
```

---

### **Workflow 3: Tool Execution with Retry and Error Handling**

This workflow shows the tool execution pattern with retry logic and error recovery.

```mermaid
sequenceDiagram
    participant Agent as Agent (Core)
    participant Tool as GitTool
    participant Subprocess as subprocess
    participant Logger as structlog
    
    Agent->>Tool: execute(repo_path="/path", command="clone")
    
    Tool->>Tool: validate_parameters(params)
    alt Invalid parameters
        Tool-->>Agent: Error: Missing required param
    end
    
    Tool->>Logger: log("tool.execution.started", tool="git")
    
    loop Retry up to 3 times
        Tool->>Subprocess: run(["git", "clone", "..."])
        
        alt Success
            Subprocess-->>Tool: returncode=0, stdout="Cloning..."
            Tool->>Logger: log("tool.execution.success")
            Tool-->>Agent: {success: true, output: "..."}
        else Transient Error (network timeout)
            Subprocess-->>Tool: Exception: TimeoutError
            Tool->>Logger: log("tool.execution.retry", attempt=N)
            Note over Tool: Exponential backoff: 1s, 2s, 4s
        else Permanent Error (invalid repo)
            Subprocess-->>Tool: returncode=128, stderr="not found"
            Tool->>Logger: log("tool.execution.failed")
            Tool-->>Agent: {success: false, error: "..."}
        end
    end
    
    alt Max retries exceeded
        Tool->>Logger: log("tool.execution.failed", reason="max_retries")
        Tool-->>Agent: {success: false, error: "Max retries"}
    end
```

---

### **Workflow 4: State Persistence and Recovery (Database)**

This workflow shows database-backed state persistence with versioning and concurrent access handling.

```mermaid
sequenceDiagram
    participant Agent1 as Agent Instance 1
    participant Agent2 as Agent Instance 2
    participant DbState as DbStateManager
    participant SQLAlchemy as SQLAlchemy ORM
    participant Postgres as PostgreSQL
    
    Note over Agent1,Agent2: Concurrent execution scenario
    
    Agent1->>DbState: save_state(session_id, state_data)
    DbState->>SQLAlchemy: query(Session).filter_by(session_id)
    SQLAlchemy->>Postgres: SELECT * FROM sessions WHERE session_id=?
    Postgres-->>SQLAlchemy: session (version=1)
    
    DbState->>SQLAlchemy: insert(State, state_json, version=2)
    SQLAlchemy->>Postgres: INSERT INTO states (session_id, state_json, version=2)
    Postgres-->>SQLAlchemy: OK
    
    DbState->>SQLAlchemy: update(Session, updated_at, version=2)
    SQLAlchemy->>Postgres: UPDATE sessions SET version=2, updated_at=NOW()
    Postgres-->>SQLAlchemy: OK
    SQLAlchemy-->>DbState: committed
    DbState-->>Agent1: saved (version=2)
    
    Note over Agent2: Attempting to save with stale version
    Agent2->>DbState: save_state(session_id, state_data, version=1)
    DbState->>SQLAlchemy: update(Session) WHERE version=1
    SQLAlchemy->>Postgres: UPDATE sessions SET version=2 WHERE version=1
    Postgres-->>SQLAlchemy: 0 rows affected (conflict!)
    
    alt Optimistic lock conflict
        DbState-->>Agent2: Error: State modified by another instance
        Agent2->>DbState: load_state(session_id)
        DbState->>Postgres: SELECT latest state
        Postgres-->>DbState: state (version=2)
        DbState-->>Agent2: current_state
        Note over Agent2: Retry with updated state
    end
```

---

### **Workflow 5: FastAPI REST API Execution with Streaming**

This workflow shows mission execution via REST API with Server-Sent Events for progress updates.

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI
    participant Route as ExecutionRoute
    participant Executor as AgentExecutor
    participant Agent as Agent (Core)
    
    Client->>API: POST /api/v1/execute/stream
    Note over Client: {"mission": "...", "profile": "prod"}
    
    API->>Route: execute_mission_stream(request)
    Route->>Executor: execute_mission_streaming(mission, profile)
    
    Note over Executor: Returns AsyncIterator[ProgressUpdate]
    
    loop ReAct Loop Iterations
        Executor->>Agent: execute (step by step)
        
        Agent-->>Executor: ProgressUpdate(event="thought")
        Executor-->>Route: yield ProgressUpdate
        Route-->>API: SSE: data: {"event":"thought", ...}
        API-->>Client: Server-Sent Event
        
        Agent-->>Executor: ProgressUpdate(event="action")
        Executor-->>Route: yield ProgressUpdate
        Route-->>API: SSE: data: {"event":"action", ...}
        API-->>Client: Server-Sent Event
        
        Agent-->>Executor: ProgressUpdate(event="observation")
        Executor-->>Route: yield ProgressUpdate
        Route-->>API: SSE: data: {"event":"observation", ...}
        API-->>Client: Server-Sent Event
    end
    
    Agent-->>Executor: ProgressUpdate(event="complete")
    Executor-->>Route: yield ProgressUpdate
    Route-->>API: SSE: data: {"event":"complete", ...}
    API-->>Client: Server-Sent Event
    
    API->>Client: Connection closed
```

---

### **Workflow 6: Configuration Profile Loading and Adapter Selection**

This workflow shows how configuration profiles determine which infrastructure adapters are used.

```mermaid
sequenceDiagram
    participant CLI as CLI/API
    participant Factory as AgentFactory
    participant Profiles as ProfileLoader
    participant FileState as FileStateManager
    participant DbState as DbStateManager
    participant LLM as OpenAIService
    
    CLI->>Factory: create_agent(profile="prod")
    
    Factory->>Profiles: load_profile("prod")
    Profiles->>Profiles: read configs/prod.yaml
    Profiles->>Profiles: merge_env_overrides()
    Profiles->>Profiles: validate_config()
    Profiles-->>Factory: config
    
    Note over Factory: Config inspection:<br/>persistence.type = "database"
    
    Factory->>Factory: _create_state_manager(config)
    alt config.persistence.type == "database"
        Factory->>DbState: new DbStateManager(db_url)
        DbState->>PostgreSQL: Test connection
        PostgreSQL-->>DbState: OK
        DbState-->>Factory: state_manager
    else config.persistence.type == "file"
        Factory->>FileState: new FileStateManager(work_dir)
        FileState-->>Factory: state_manager
    end
    
    Factory->>Factory: _create_llm_provider(config)
    Factory->>LLM: new OpenAIService(llm_config_path)
    LLM->>LLM: Load llm_config.yaml
    alt config.llm.provider == "azure"
        LLM->>LLM: Configure Azure endpoint
    else config.llm.provider == "openai"
        LLM->>LLM: Configure OpenAI endpoint
    end
    LLM-->>Factory: llm_provider
    
    Factory->>Factory: _create_tools(config)
    Factory-->>CLI: Agent(state_manager, llm_provider, tools)
```

---

### **Rationale:**

**Workflow Selection Decisions:**

1. **ReAct Loop as Primary Workflow**: Showcased complete thought → action → observation cycle. Rationale: This is the core algorithm - understanding this workflow is essential for all developers.

2. **State Persistence with Concurrency**: Included optimistic locking scenario. Rationale: Production environment may have multiple agent instances. Shows how conflicts are detected and resolved.

3. **Streaming API Workflow**: Demonstrated SSE pattern. Rationale: Long-running missions need progress updates. Shows how domain events translate to API events.

4. **Error Handling in Tool Execution**: Showed retry logic explicitly. Rationale: External tool calls fail frequently. Retry strategy is critical for reliability.

5. **Profile-Based Adapter Selection**: Illustrated dependency injection. Rationale: Shows how Clean Architecture enables runtime adapter swapping via configuration.

**Key Patterns Illustrated:**

- **Async throughout**: All I/O operations use async/await
- **Protocol-based boundaries**: Agent never calls concrete implementations directly
- **Event-driven progress**: Domain events enable real-time updates
- **Defensive error handling**: Every external call wrapped in try/catch with retry
- **Structured logging**: Every significant operation logged with context

**Trade-offs:**

- **Sequence diagram complexity**: Detailed diagrams vs. readability. Chose detail to show actual implementation patterns.
- **Workflow scope**: Full workflows vs. focused interactions. Chose full workflows to show end-to-end flow.

---

🏗️ **Proceeding to Security...**

---
