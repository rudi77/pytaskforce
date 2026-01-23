# Taskforce Architecture Diagrams

Dieses Dokument enthält detaillierte Architekturdiagramme des Taskforce-Frameworks.

---

## 1. High-Level Layer Architecture

Das System folgt Clean Architecture mit vier strikten Schichten:

```mermaid
graph TB
    subgraph "API Layer (Entrypoints)"
        CLI[Typer CLI<br/>main.py]
        REST[FastAPI REST<br/>server.py]
        ChatCLI[Simple CLI Chat<br/>simple_chat.py]
    end

    subgraph "Application Layer (Orchestration)"
        Factory[AgentFactory<br/>Dependency Injection]
        Executor[AgentExecutor<br/>Mission Orchestration]
        Registry[AgentRegistry<br/>Unified Agent Sources]
        Resolver[ToolResolver<br/>Tool Resolution]
        InfraBld[InfrastructureBuilder<br/>Adapter Building]
        ToolCatalog[ToolCatalog<br/>Tool Validation]
        PluginLoader[PluginLoader<br/>Plugin Discovery]
    end

    subgraph "Infrastructure Layer (Adapters)"
        LLM[OpenAIService<br/>LiteLLM Wrapper]
        State[FileStateManager<br/>JSON Persistence]
        ResultStore[FileToolResultStore<br/>Result Caching]
        ToolReg[ToolRegistry<br/>Tool Definitions]

        subgraph "Tools"
            Native[Native Tools<br/>Python, File, Git, Shell, Web]
            RAG[RAG Tools<br/>Semantic Search, Documents]
            MCP[MCP Tools<br/>External Servers]
        end
    end

    subgraph "Core Layer (Domain)"
        Agent[LeanAgent<br/>ReAct Loop]
        Planner[PlannerTool<br/>Plan Management]
        AgentDef[AgentDefinition<br/>Unified Model]
        ConfigSchema[ConfigSchema<br/>Pydantic Validation]

        subgraph "Protocols"
            LLMProtocol[LLMProviderProtocol]
            StateProtocol[StateManagerProtocol]
            ToolProtocol[ToolProtocol]
        end

        Models[Domain Models<br/>ExecutionResult, StreamEvent]
        Prompts[System Prompts<br/>Kernel, Specialist]
    end

    %% Layer connections (dependency direction: inward)
    CLI --> Executor
    REST --> Executor
    TUI --> Executor

    Executor --> Factory
    Executor --> Registry
    Factory --> Agent
    Factory --> InfraBld
    Factory --> Resolver
    Factory --> AgentDef
    Registry --> AgentDef
    ConfigSchema --> AgentDef

    InfraBld --> LLM
    InfraBld --> State
    InfraBld --> MCP
    Resolver --> ToolReg
    ToolReg --> Native
    ToolReg --> RAG

    Agent --> LLMProtocol
    Agent --> StateProtocol
    Agent --> ToolProtocol
    Agent --> Planner
    Agent --> Models
    Agent --> Prompts

    LLM -.->|implements| LLMProtocol
    State -.->|implements| StateProtocol
    Native -.->|implements| ToolProtocol
    RAG -.->|implements| ToolProtocol
    MCP -.->|implements| ToolProtocol

    classDef core fill:#e1f5fe,stroke:#01579b
    classDef infra fill:#fff3e0,stroke:#e65100
    classDef app fill:#f3e5f5,stroke:#7b1fa2
    classDef api fill:#e8f5e9,stroke:#2e7d32
    classDef new fill:#c8e6c9,stroke:#2e7d32

    class Agent,Planner,LLMProtocol,StateProtocol,ToolProtocol,Models,Prompts core
    class LLM,State,ResultStore,ToolReg,Native,RAG,MCP infra
    class Factory,Executor,ToolCatalog,PluginLoader app
    class CLI,REST,TUI api
    class Registry,Resolver,InfraBld,AgentDef,ConfigSchema new
```

---

## 2. Component Dependency Diagram

Zeigt die Beziehungen zwischen den Hauptkomponenten:

```mermaid
flowchart LR
    subgraph Core["Core Domain"]
        direction TB
        LA[LeanAgent]
        PT[PlannerTool]
        PS[PlanningStrategy]
        CB[ContextBuilder]
        TB[TokenBudgeter]
        AD[AgentDefinition]
        CS[ConfigSchema]

        LA --> PT
        LA --> PS
        LA --> CB
        LA --> TB
    end

    subgraph Protocols["Core Interfaces"]
        direction TB
        LLMP[LLMProviderProtocol]
        SMP[StateManagerProtocol]
        TP[ToolProtocol]
        TRSP[ToolResultStoreProtocol]
    end

    subgraph Infra["Infrastructure"]
        direction TB
        OAI[OpenAIService]
        FSM[FileStateManager]
        FTRS[FileToolResultStore]

        subgraph Tools["Tool Registry"]
            PY[PythonTool]
            FR[FileReadTool]
            FW[FileWriteTool]
            GT[GitTool]
            PS2[PowerShellTool]
            SH[ShellTool]
            WS[WebSearchTool]
            WF[WebFetchTool]
            AU[AskUserTool]
        end

        subgraph MCPTools["MCP Integration"]
            MC[MCPClient]
            MW[MCPToolWrapper]
        end

        subgraph RAGTools["RAG Tools"]
            SS[SemanticSearchTool]
            LD[ListDocumentsTool]
            GD[GetDocumentTool]
        end
    end

    subgraph App["Application"]
        direction TB
        AF[AgentFactory]
        AE[AgentExecutor]
        AR[AgentRegistry]
        TR[ToolResolver]
        IB[InfrastructureBuilder]
        TC[ToolCatalog]
        PL[PluginLoader]
    end

    %% Protocol implementations
    OAI -.->|implements| LLMP
    FSM -.->|implements| SMP
    FTRS -.->|implements| TRSP
    PY -.->|implements| TP
    FR -.->|implements| TP
    MW -.->|implements| TP
    SS -.->|implements| TP

    %% Core uses protocols
    LA -->|uses| LLMP
    LA -->|uses| SMP
    LA -->|uses| TP

    %% New unified flow
    AR -->|loads| AD
    AF -->|uses| AD
    AF -->|uses| TR
    AF -->|uses| IB
    TR -->|resolves| Tools
    IB -->|builds| OAI
    IB -->|builds| FSM
    IB -->|builds| MCPTools

    %% Application wiring
    AF -->|creates| LA
    AE -->|uses| AF
    AE -->|uses| AR
    TC -->|validates| Tools
    CS -->|validates| AD

    classDef protocol fill:#ffecb3,stroke:#ff8f00
    classDef domain fill:#e1f5fe,stroke:#01579b
    classDef adapter fill:#fff3e0,stroke:#e65100
    classDef service fill:#f3e5f5,stroke:#7b1fa2
    classDef new fill:#c8e6c9,stroke:#2e7d32

    class LLMP,SMP,TP,TRSP protocol
    class LA,PT,PS,CB,TB domain
    class OAI,FSM,FTRS,PY,FR,FW,GT,PS2,SH,WS,WF,AU,MC,MW,SS,LD,GD adapter
    class AF,AE,TC,PL service
    class AR,TR,IB,AD,CS new
```

---

## 3. ReAct Loop Execution Flow

Der Hauptausführungszyklus des Agenten:

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant CLI/API
    participant Executor as AgentExecutor
    participant Factory as AgentFactory
    participant Agent as LeanAgent
    participant LLM as OpenAIService
    participant Tools as Tool Registry
    participant State as FileStateManager
    participant Store as ToolResultStore

    User->>CLI/API: taskforce run mission "..."
    CLI/API->>Executor: execute(mission, profile)
    Executor->>Factory: create_agent(profile)

    Note over Factory: Load YAML config<br/>Initialize adapters<br/>Wire dependencies

    Factory-->>Executor: Agent instance
    Executor->>Agent: execute(mission, session_id)

    Agent->>State: load_state(session_id)
    State-->>Agent: state_data or None

    loop ReAct Loop (max_steps)
        Agent->>Agent: Build system prompt<br/>+ plan status<br/>+ context pack

        Agent->>LLM: complete(messages, tools)

        alt LLM returns content only
            LLM-->>Agent: Final answer
            Agent->>Agent: Break loop
        else LLM returns tool_calls
            LLM-->>Agent: tool_calls[]

            par Parallel Tool Execution
                loop For each tool_call
                    Agent->>Tools: execute(name, params)
                    Tools-->>Agent: result

                    alt Result > 5000 chars
                        Agent->>Store: put(session_id, result)
                        Store-->>Agent: handle + preview
                    end
                end
            end

            Agent->>Agent: Add tool results to history
            Agent->>State: save_state(session_id, state)
        end
    end

    Agent-->>Executor: ExecutionResult
    Executor-->>CLI/API: Result
    CLI/API-->>User: Display output
```

---

## 4. Tool Ecosystem

Übersicht aller Tool-Typen und deren Integration:

```mermaid
flowchart TB
    subgraph Agent["LeanAgent"]
        TE[ToolExecutor]
    end

    subgraph Registry["Tool Registry"]
        direction LR
        TR[registry.py<br/>name → module mapping]
    end

    subgraph Native["Native Tools"]
        direction TB
        N1[PythonTool<br/>Code Execution]
        N2[FileReadTool<br/>Read Files]
        N3[FileWriteTool<br/>Write Files]
        N4[GitTool<br/>Git Operations]
        N5[GitHubTool<br/>GitHub API]
        N6[PowerShellTool<br/>Shell Commands]
        N7[WebSearchTool<br/>Web Search]
        N8[WebFetchTool<br/>HTTP Requests]
        N9[AskUserTool<br/>User Interaction]
        N10[LLMTool<br/>Sub-Agent Calls]
    end

    subgraph RAGTools["RAG Tools"]
        direction TB
        R1[SemanticSearchTool<br/>Vector Search]
        R2[ListDocumentsTool<br/>Document List]
        R3[GetDocumentTool<br/>Fetch Document]
        R4[GlobalDocumentAnalysisTool<br/>Cross-Doc Analysis]
    end

    subgraph MCPIntegration["MCP Integration"]
        direction TB
        MC[MCPClient<br/>Connection Manager]
        MW[MCPToolWrapper<br/>Protocol Adapter]

        subgraph Servers["External MCP Servers"]
            S1[Memory Server<br/>Knowledge Graph]
            S2[Custom Servers<br/>via stdio/SSE]
        end
    end

    subgraph Orchestration["Orchestration Tools"]
        AT[AgentTool<br/>Invoke Sub-Agents]
    end

    subgraph CoreTool["Core Tool"]
        PT[PlannerTool<br/>Plan CRUD]
    end

    TE --> TR
    TR --> Native
    TR --> RAGTools
    TR --> MCPIntegration
    TR --> Orchestration
    TR --> CoreTool

    MC --> Servers
    MW --> MC

    classDef native fill:#c8e6c9,stroke:#2e7d32
    classDef rag fill:#bbdefb,stroke:#1565c0
    classDef mcp fill:#ffe0b2,stroke:#ef6c00
    classDef orch fill:#e1bee7,stroke:#7b1fa2
    classDef core fill:#fff9c4,stroke:#f9a825

    class N1,N2,N3,N4,N5,N6,N7,N8,N9,N10 native
    class R1,R2,R3,R4 rag
    class MC,MW,S1,S2 mcp
    class AT orch
    class PT core
```

---

## 5. State Management & Persistence

Wie Session-State verwaltet wird:

```mermaid
flowchart TB
    subgraph Agent["LeanAgent"]
        MHM[MessageHistoryManager]
        SS[StateStore]
    end

    subgraph State["FileStateManager"]
        direction TB
        SM[save_state]
        LM[load_state]
        DM[delete_state]
        LS[list_sessions]
    end

    subgraph Storage["File Storage"]
        direction TB
        SF[".taskforce/states/<br/>{session_id}.json"]
        TMP[".json.tmp"]
        BAK[".json.bak"]
    end

    subgraph Schema["State Schema"]
        direction LR
        SCH["
        {
          session_id: str
          message_history: [...]
          plan_status: {...}
          tool_result_handles: {...}
          _version: int
          _updated_at: timestamp
        }
        "]
    end

    subgraph ResultStore["FileToolResultStore"]
        direction TB
        RS[".taskforce/tool_results/"]
        RES["results/{handle}.json"]
        HND["handles/{handle}.meta"]
    end

    Agent --> SS
    SS --> State
    State --> Storage

    SM -->|"1. Write"| TMP
    TMP -->|"2. Backup"| BAK
    TMP -->|"3. Rename"| SF

    MHM --> ResultStore
    ResultStore --> RS

    classDef storage fill:#e3f2fd,stroke:#1565c0
    classDef manager fill:#fff3e0,stroke:#e65100

    class SF,TMP,BAK,RS,RES,HND storage
    class SM,LM,DM,LS manager
```

---

## 6. Configuration System

Profile-basierte Konfiguration:

```mermaid
flowchart TB
    subgraph Env["Environment"]
        E1[TASKFORCE_PROFILE]
        E2[OPENAI_API_KEY]
        E3[DATABASE_URL]
    end

    subgraph Profiles["configs/*.yaml"]
        direction TB
        DEV["dev.yaml
        ─────────────
        profile: dev
        specialist: null
        persistence: file
        tools: [basic]"]

        COD["coding_agent.yaml
        ─────────────
        profile: coding_agent
        specialist: coding
        tools: [file, git, python]
        mcp_servers: [memory]"]

        RAG["rag_agent.yaml
        ─────────────
        profile: rag_agent
        specialist: rag
        tools: [semantic_search]"]

        ORCH["orchestrator.yaml
        ─────────────
        profile: orchestrator
        tools: [agent_tool]"]
    end

    subgraph Prompts["System Prompts"]
        direction TB
        KERN[LEAN_KERNEL_PROMPT<br/>Base für alle Agenten]
        SPEC_COD[CODING_SPECIALIST_PROMPT<br/>+ Coding Guidelines]
        SPEC_RAG[RAG_SPECIALIST_PROMPT<br/>+ RAG Guidelines]
    end

    subgraph Factory["AgentFactory"]
        PL[ProfileLoader]
        PS[Prompt Selection]
        TL[Tool Loading]
        ML[MCP Loading]
    end

    subgraph Agent["Configured Agent"]
        LA[LeanAgent<br/>+ Tools<br/>+ System Prompt<br/>+ Adapters]
    end

    E1 -->|selects| Profiles
    Profiles --> Factory

    PL --> PS
    PS -->|specialist=null| KERN
    PS -->|specialist=coding| SPEC_COD
    PS -->|specialist=rag| SPEC_RAG

    KERN --> LA
    SPEC_COD --> LA
    SPEC_RAG --> LA

    PL --> TL --> LA
    PL --> ML --> LA

    classDef env fill:#ffecb3,stroke:#ff8f00
    classDef config fill:#e1f5fe,stroke:#01579b
    classDef prompt fill:#f3e5f5,stroke:#7b1fa2
    classDef factory fill:#c8e6c9,stroke:#2e7d32

    class E1,E2,E3 env
    class DEV,COD,RAG,ORCH config
    class KERN,SPEC_COD,SPEC_RAG prompt
    class PL,PS,TL,ML factory
```

---

## 6a. Unified Agent Definition System (2026-01 Refactoring)

Das neue vereinheitlichte Agent-Definitions-System:

```mermaid
flowchart TB
    subgraph Sources["Agent Sources"]
        direction TB
        CUSTOM["configs/custom/*.yaml<br/>──────────────<br/>source: CUSTOM<br/>mutable: ✓"]
        PROFILE["configs/*.yaml<br/>──────────────<br/>source: PROFILE<br/>mutable: ✗"]
        PLUGIN["examples/, plugins/<br/>──────────────<br/>source: PLUGIN<br/>mutable: ✗"]
        COMMAND[".taskforce/commands/**/*.md<br/>──────────────<br/>source: COMMAND<br/>mutable: ✗"]
    end

    subgraph Registry["AgentRegistry"]
        direction TB
        LIST[list_all]
        GET[get]
        SAVE[save]
        CREATE[create]
        UPDATE[update]
        DELETE[delete]
        CACHE[(Cache)]
    end

    subgraph Definition["AgentDefinition (Unified Model)"]
        direction LR
        DEF["
        agent_id: str
        name: str
        source: AgentSource
        ───────────────
        system_prompt: str
        specialist: str?
        tools: list[str]  ← Strings only!
        mcp_servers: list[MCPServerConfig]
        ───────────────
        base_profile: str
        work_dir: str?
        "]
    end

    subgraph Factory["AgentFactory.create()"]
        direction TB
        IB[InfrastructureBuilder]
        TR[ToolResolver]
        PB[PromptBuilder]
    end

    subgraph Agent["Agent Instance"]
        LA[LeanAgent]
    end

    %% Source loading
    CUSTOM --> Registry
    PROFILE --> Registry
    PLUGIN --> Registry
    COMMAND --> Registry

    Registry --> Definition
    LIST --> CACHE
    GET --> CACHE

    %% Factory flow
    Definition --> Factory
    IB -->|State, LLM, MCP| Factory
    TR -->|Native Tools| Factory
    PB -->|System Prompt| Factory

    Factory --> Agent

    classDef source fill:#e3f2fd,stroke:#1565c0
    classDef registry fill:#f3e5f5,stroke:#7b1fa2
    classDef model fill:#e1f5fe,stroke:#01579b
    classDef factory fill:#c8e6c9,stroke:#2e7d32

    class CUSTOM,PROFILE,PLUGIN,COMMAND source
    class LIST,GET,SAVE,CREATE,UPDATE,DELETE,CACHE registry
    class DEF model
    class IB,TR,PB factory
```

---

## 6b. Tool Resolution Flow

Wie Tools von Namen zu Instanzen aufgelöst werden:

```mermaid
sequenceDiagram
    autonumber
    participant Def as AgentDefinition
    participant Factory as AgentFactory
    participant Resolver as ToolResolver
    participant Registry as ToolRegistry
    participant Infra as InfrastructureBuilder

    Note over Def: tools: ["python", "file_read", "web_search"]

    Factory->>Resolver: resolve(tool_names)

    loop For each tool name
        Resolver->>Registry: get_tool_definition(name)
        Registry-->>Resolver: {type, module, params}

        Resolver->>Resolver: import_module(module)
        Resolver->>Resolver: instantiate(type, **params)

        alt Tool needs LLM (e.g., LLMTool)
            Resolver->>Resolver: inject llm_provider
        else Tool needs user_context (e.g., RAG tools)
            Resolver->>Resolver: inject user_context
        end
    end

    Resolver-->>Factory: list[ToolProtocol]

    Factory->>Infra: build_mcp_tools(mcp_servers)
    Infra-->>Factory: mcp_tools, contexts

    Factory->>Factory: Combine native + MCP tools
    Factory-->>Factory: All tools ready
```

---

## 6c. Unified Config Schema

Pydantic-basierte Validierung:

```mermaid
flowchart TB
    subgraph Input["YAML Input"]
        YAML["
        agent_id: my-agent
        name: My Agent
        tools:
          - python
          - file_read
        mcp_servers:
          - type: stdio
            command: npx
            args: [-y, @mcp/memory]
        "]
    end

    subgraph Validation["Config Validation"]
        direction TB
        ACS[AgentConfigSchema<br/>Pydantic Model]
        MCS[MCPServerConfigSchema]
        PCS[ProfileConfigSchema]

        ACS --> MCS
    end

    subgraph Rules["Validation Rules"]
        direction TB
        R1["✓ tools must be strings only"]
        R2["✓ agent_id: alphanumeric + _ : -"]
        R3["✓ specialist: coding | rag | wiki | null"]
        R4["✓ stdio requires command"]
        R5["✓ sse requires url"]
    end

    subgraph Output["Validated Output"]
        AD[AgentDefinition]
    end

    YAML --> Validation
    Validation --> Rules
    Rules -->|"valid"| Output
    Rules -->|"invalid"| ERR[ConfigValidationError<br/>with file path & field]

    classDef input fill:#fff3e0,stroke:#e65100
    classDef valid fill:#c8e6c9,stroke:#2e7d32
    classDef rules fill:#ffecb3,stroke:#ff8f00
    classDef error fill:#ffcdd2,stroke:#c62828

    class YAML input
    class ACS,MCS,PCS valid
    class R1,R2,R3,R4,R5 rules
    class ERR error
```

---

## 7. MCP Server Integration

Wie externe MCP-Server integriert werden:

```mermaid
sequenceDiagram
    autonumber
    participant Factory as AgentFactory
    participant Client as MCPClient
    participant Wrapper as MCPToolWrapper
    participant Server as MCP Server Process
    participant Agent as LeanAgent

    Factory->>Factory: Load mcp_servers from config

    loop For each MCP server
        Factory->>Client: create_stdio(command, args, env)
        Client->>Server: Spawn subprocess
        Client->>Server: Initialize via stdio
        Server-->>Client: Server capabilities

        Client->>Server: list_tools()
        Server-->>Client: tool_definitions[]

        loop For each tool
            Factory->>Wrapper: MCPToolWrapper(client, tool_def)
            Note over Wrapper: Adapts MCP tool<br/>to ToolProtocol
        end

        Factory->>Agent: Add wrapped tools
    end

    Note over Agent: Agent now has<br/>MCP tools available

    Agent->>Wrapper: execute(params)
    Wrapper->>Client: call_tool(name, args)
    Client->>Server: RPC call via stdio
    Server-->>Client: Tool result
    Client-->>Wrapper: Result
    Wrapper-->>Agent: Formatted result
```

---

## 8. API Layer Architecture

REST und CLI Entrypoints:

```mermaid
flowchart TB
    subgraph External["External"]
        U1[User Terminal]
        U2[HTTP Client]
    end

    subgraph CLI["CLI Layer (Typer)"]
        direction TB
        MAIN[main.py<br/>Entry Point]

        subgraph Commands["Commands"]
            RUN[run.py<br/>taskforce run mission]
            CHAT[chat.py<br/>taskforce chat]
            TOOLS[tools.py<br/>taskforce tools]
            SESS[sessions.py<br/>taskforce sessions]
            CFG[config.py<br/>taskforce config]
        end

        OF[OutputFormatter<br/>Rich Formatting]
    end

    subgraph ChatConsole["Chat Console (REPL)"]
        direction TB
        SIMPLE[SimpleChatRunner<br/>simple_chat.py]
    end

    subgraph REST["REST Layer (FastAPI)"]
        direction TB
        SRV[server.py<br/>FastAPI App]

        subgraph Routes["Routes"]
            EX["/execute"]
            EXS["/execute/stream"]
            AG["/agents"]
            SE["/sessions"]
            TL["/tools"]
            HE["/health"]
        end

        SCH[Pydantic Schemas]
    end

    subgraph App["Application Layer"]
        AE[AgentExecutor]
    end

    U1 --> CLI
    U2 --> REST

    MAIN --> Commands
    Commands --> OF
    CHAT --> TUI

    RUN --> AE
    CHAT --> AE

    SRV --> Routes
    Routes --> SCH
    EX --> AE
    EXS --> AE

    classDef external fill:#ffcdd2,stroke:#c62828
    classDef cli fill:#c8e6c9,stroke:#2e7d32
    classDef tui fill:#bbdefb,stroke:#1565c0
    classDef rest fill:#ffe0b2,stroke:#ef6c00

    class U1,U2 external
    class MAIN,RUN,CHAT,TOOLS,SESS,CFG,OF cli
    class APP,CL,EP,PP,IB tui
    class SRV,EX,EXS,AG,SE,TL,HE,SCH rest
```

---

## 9. Complete System Overview

Vollständige Systemübersicht mit allen Komponenten:

```mermaid
graph TB
    subgraph Users["Users"]
        DEV[Developer]
        SVC[Service/API Client]
    end

    subgraph Entrypoints["API Layer"]
        CLI[CLI<br/>taskforce run/chat]
        REST[REST API<br/>POST /execute]
        TUI[Chat TUI<br/>Interactive]
    end

    subgraph Application["Application Layer"]
        EXEC[AgentExecutor]
        FACT[AgentFactory]
        REG[AgentRegistry]
        TRES[ToolResolver]
        IBLD[InfrastructureBuilder]
        CAT[ToolCatalog]
        PLUG[PluginLoader]
    end

    subgraph Domain["Core Domain Layer"]
        AGENT[LeanAgent<br/>ReAct Loop]
        PLAN[PlannerTool]
        STRAT[PlanningStrategy]
        CTX[ContextBuilder]
        TOK[TokenBudgeter]
        ADEF[AgentDefinition<br/>Unified Model]
        CSCH[ConfigSchema<br/>Validation]

        subgraph Protocols["Interfaces"]
            P1[LLMProviderProtocol]
            P2[StateManagerProtocol]
            P3[ToolProtocol]
            P4[ToolResultStoreProtocol]
        end
    end

    subgraph Infrastructure["Infrastructure Layer"]
        subgraph LLMAdapters["LLM"]
            OAI[OpenAIService]
        end

        subgraph Persistence["Persistence"]
            FSM[FileStateManager]
            FTR[FileToolResultStore]
        end

        subgraph ToolsInfra["Tools"]
            TREG[ToolRegistry]
            NT[Native Tools<br/>11 tools]
            RT[RAG Tools<br/>4 tools]
            MT[MCP Tools<br/>dynamic]
            OT[Orchestration<br/>AgentTool]
        end
    end

    subgraph External["External Services"]
        OPENAI[OpenAI API]
        AZURE[Azure OpenAI]
        MCPS[MCP Servers]
        FS[File System]
        GH[GitHub API]
    end

    %% User connections
    DEV --> CLI
    DEV --> TUI
    SVC --> REST

    %% API to Application
    CLI --> EXEC
    REST --> EXEC
    TUI --> EXEC

    %% Application wiring (new unified flow)
    EXEC --> FACT
    EXEC --> REG
    REG --> ADEF
    FACT --> ADEF
    FACT --> TRES
    FACT --> IBLD
    TRES --> TREG
    IBLD --> OAI
    IBLD --> FSM
    IBLD --> MT
    FACT --> AGENT
    FACT --> CAT
    PLUG --> REG
    CSCH --> ADEF

    %% Domain dependencies
    AGENT --> PLAN
    AGENT --> STRAT
    AGENT --> CTX
    AGENT --> TOK
    AGENT --> P1
    AGENT --> P2
    AGENT --> P3

    %% Protocol implementations
    OAI -.->|impl| P1
    FSM -.->|impl| P2
    FTR -.->|impl| P4
    NT -.->|impl| P3
    RT -.->|impl| P3
    MT -.->|impl| P3

    %% Tool registry
    TREG --> NT
    TREG --> RT

    %% External connections
    OAI --> OPENAI
    OAI --> AZURE
    MT --> MCPS
    FSM --> FS
    FTR --> FS
    NT --> GH
    NT --> FS

    classDef user fill:#ffcdd2,stroke:#c62828
    classDef api fill:#e8f5e9,stroke:#2e7d32
    classDef app fill:#f3e5f5,stroke:#7b1fa2
    classDef domain fill:#e1f5fe,stroke:#01579b
    classDef infra fill:#fff3e0,stroke:#e65100
    classDef external fill:#f5f5f5,stroke:#616161
    classDef new fill:#c8e6c9,stroke:#2e7d32

    class DEV,SVC user
    class CLI,REST,TUI api
    class EXEC,FACT,CAT,PLUG app
    class AGENT,PLAN,STRAT,CTX,TOK,P1,P2,P3,P4 domain
    class OAI,FSM,FTR,TREG,NT,RT,MT,OT infra
    class OPENAI,AZURE,MCPS,FS,GH external
    class REG,TRES,IBLD,ADEF,CSCH new
```

---

## 10. Import Rules & Layer Dependencies

Visualisierung der erlaubten Abhängigkeitsrichtungen:

```mermaid
flowchart TB
    subgraph Rules["Import Rules (Dependency Direction: INWARD)"]
        direction TB

        API["API Layer<br/>────────────<br/>Can import: Application, Core/Interfaces<br/>Cannot import: Infrastructure directly"]

        APP["Application Layer<br/>────────────<br/>Can import: ALL layers<br/>Cannot import: -"]

        INFRA["Infrastructure Layer<br/>────────────<br/>Can import: Core/Interfaces, Core/Domain<br/>Cannot import: Application, API"]

        CORE["Core Layer<br/>────────────<br/>Core/Domain can import: Core/Interfaces only<br/>Core/Interfaces can import: NOTHING"]
    end

    API -->|"allowed"| APP
    API -->|"allowed"| CORE
    API -.->|"FORBIDDEN"| INFRA

    APP -->|"allowed"| INFRA
    APP -->|"allowed"| CORE

    INFRA -->|"allowed"| CORE
    INFRA -.->|"FORBIDDEN"| APP
    INFRA -.->|"FORBIDDEN"| API

    style API fill:#e8f5e9,stroke:#2e7d32
    style APP fill:#f3e5f5,stroke:#7b1fa2
    style INFRA fill:#fff3e0,stroke:#e65100
    style CORE fill:#e1f5fe,stroke:#01579b
```

---

## Legende

| Farbe | Bedeutung |
|-------|-----------|
| Blau (#e1f5fe) | Core Domain Layer |
| Orange (#fff3e0) | Infrastructure Layer |
| Violett (#f3e5f5) | Application Layer |
| Grün (#e8f5e9) | API Layer |
| Gelb (#ffecb3) | Protocols/Interfaces |
| Grau (#f5f5f5) | External Services |
| Hellgrün (#c8e6c9) | New Unified Components (2026-01 Refactoring) |

---

## Changelog

### 2026-01-21: Unified Agent Architecture Refactoring

Added new components for unified agent definitions:

| New Component | Description |
|---------------|-------------|
| `AgentDefinition` | Unified model for all agent types (custom, profile, plugin, command) |
| `AgentRegistry` | Aggregates agents from all sources with unified CRUD API |
| `ToolResolver` | Resolves tool names to instances with dependency injection |
| `InfrastructureBuilder` | Builds state managers, LLM providers, and MCP tools |
| `ConfigSchema` | Pydantic validation for agent and profile configs |
| `ToolRegistry` (extended) | Added `shell` tool, `get_all_tool_names()`, `register_tool()`, `unregister_tool()` |

New diagrams added:
- 6a. Unified Agent Definition System
- 6b. Tool Resolution Flow
- 6c. Unified Config Schema

---

*Erstellt am: 2026-01-21*
*Letzte Aktualisierung: 2026-01-21 (Unified Agent Architecture)*
*Basierend auf: Taskforce Codebase Analyse*
