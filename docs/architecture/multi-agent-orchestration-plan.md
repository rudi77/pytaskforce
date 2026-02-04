# Multi-Agent-Orchestration Plan

**Version:** 1.0
**Datum:** 2026-01-13
**Status:** Vorschlag (Draft)

---

## Übersicht

Dieser Plan beschreibt die Implementierung von Multi-Agent-Orchestration in Taskforce, bei der ein **Orchestrator-Agent** einen oder mehrere **Sub-Agents** aufrufen kann.

### Anforderungen

1. **Agent-zu-Agent-Kommunikation**: Ein Agent kann andere Agents aufrufen
2. **Context-Isolation**: Jeder Sub-Agent hat seinen eigenen Session-Context
3. **Parallele Ausführung**: Orchestrator kann mehrere Sub-Agents parallel aufrufen
4. **Clean Architecture**: Lösung muss in die bestehende 4-Layer-Architektur passen

---

## Lösungsansätze (Evaluation)

### Ansatz 1: Agents als Tools ⭐ **EMPFOHLEN**

**Konzept**: Wrappen von Agents in ein ToolProtocol-konformes Interface.

**Vorteile:**
- ✅ Perfekte Integration in bestehende Architektur
- ✅ Nutzt vorhandene Tool-Infrastruktur (Tool Registry, Execution, Approval)
- ✅ Parallele Ausführung bereits unterstützt (`supports_parallelism`)
- ✅ State-Isolation automatisch (separate Session IDs)
- ✅ Protocol-basiert → einfach testbar
- ✅ Nutzt natives LLM Function Calling
- ✅ Keine Änderungen am Core Domain erforderlich

**Nachteile:**
- ⚠️ Sub-Agent-Tools müssen serialisierbar sein (für Tool-Schema)
- ⚠️ Verschachtelte Tool-Approvals können komplex werden

**Passt zu**: Clean Architecture, Protocol-based Design, bestehende Tool-Infrastruktur

---

### Ansatz 2: Dedicated Orchestrator Agent

**Konzept**: Spezialisierte Agent-Klasse mit direkter Agent-Instanziierung.

**Vorteile:**
- ✅ Maximum an Flexibilität
- ✅ Direkter Zugriff auf Sub-Agent-Internals

**Nachteile:**
- ❌ Bricht Clean Architecture (Core importiert Application/Infrastructure)
- ❌ Schwerer zu testen
- ❌ Duplikation von Orchestrierungs-Logik
- ❌ Keine Wiederverwendung bestehender Tool-Infrastruktur

**Fazit**: Nicht empfohlen für Taskforce.

---

### Ansatz 3: Planning Strategy mit Agent-Delegation

**Konzept**: Neue `PlanningStrategy`, die bestimmte Steps an Sub-Agents delegiert.

**Vorteile:**
- ✅ Saubere Trennung auf Planning-Ebene
- ✅ Sub-Agents werden automatisch für passende Tasks aktiviert

**Nachteile:**
- ⚠️ Komplexe Implementierung
- ⚠️ LLM kann nicht explizit Sub-Agents auswählen (statische Delegation)
- ⚠️ Weniger flexibel als Tool-basierter Ansatz

**Fazit**: Interessant für zukünftige Optimierung, aber zunächst Tool-basiert starten.

---

## Empfohlene Lösung: Agents als Tools

### Architektur-Überblick

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ReAct Loop (Agent.execute_stream)                   │   │
│  │  - Thought: "I need a specialist for task X"         │   │
│  │  - Action: call_agent(specialist="coding", ...)      │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │ AgentTool.execute()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              AgentTool (ToolProtocol)                        │
│  - Wraps AgentFactory                                        │
│  - Creates Sub-Agent with isolated session                   │
│  - Executes mission in Sub-Agent                             │
│  - Collects and returns result                               │
└───────────────────────────┬─────────────────────────────────┘
                            │ AgentFactory.create_agent()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Sub-Agent                               │
│  - Own Session ID (e.g., "parent-123:sub-coding-456")       │
│  - Own State Manager                                         │
│  - Own Tool Set (specialist tools)                           │
│  - Executes mission independently                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Story 1)

#### Story 1.1: AgentTool Protocol Implementation

**Ziel**: Implementierung des `AgentTool` als ToolProtocol-konforme Wrapper-Klasse.

**Location**: `src/taskforce/infrastructure/tools/orchestration/agent_tool.py`

**Implementation**:

```python
"""
Agent Tool - Delegate missions to specialist sub-agents
"""

from typing import Any, Dict, Optional
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.application.factory import AgentFactory


class AgentTool(ToolProtocol):
    """
    Tool that delegates missions to specialist sub-agents.

    Allows an orchestrator agent to spawn and execute sub-agents
    with different specialist profiles, tools, and system prompts.

    Each sub-agent execution:
    - Gets isolated session ID (parent_session:sub_{specialist}_{uuid})
    - Has own state management
    - Runs independently with specialist toolset
    - Returns ExecutionResult to parent agent
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        profile: str = "dev",
        work_dir: Optional[str] = None,
        max_steps: Optional[int] = None,
    ):
        """
        Initialize AgentTool with factory for creating sub-agents.

        Args:
            agent_factory: Factory for creating sub-agents
            profile: Configuration profile (dev/staging/prod)
            work_dir: Optional work directory override
            max_steps: Optional max steps override for sub-agents
        """
        self._factory = agent_factory
        self._profile = profile
        self._work_dir = work_dir
        self._max_steps = max_steps

    @property
    def name(self) -> str:
        return "call_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a mission to a specialist sub-agent. "
            "Use this when you need specialized capabilities not available in your current toolset. "
            "Available specialists: "
            "'coding' (file operations, shell commands), "
            "'rag' (semantic search, document retrieval), "
            "'wiki' (Wikipedia research), "
            "or use agent_id for custom agents (e.g., 'accounting_expert'). "
            "The sub-agent will execute the mission independently and return results."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "specialist": {
                    "type": "string",
                    "description": (
                        "Specialist profile: 'coding', 'rag', 'wiki', or custom agent ID. "
                        "Choose based on mission requirements."
                    ),
                    "enum": ["coding", "rag", "wiki"],  # Custom agent IDs also allowed
                },
                "mission": {
                    "type": "string",
                    "description": (
                        "Clear, specific mission description for the sub-agent. "
                        "Include all necessary context and constraints."
                    ),
                },
                "planning_strategy": {
                    "type": "string",
                    "description": (
                        "Optional planning strategy for sub-agent: "
                        "'native_react' (default), 'plan_and_execute', 'plan_and_react', 'spar'"
                    ),
                    "enum": ["native_react", "plan_and_execute", "plan_and_react", "spar"],
                },
                "agent_definition": {
                    "type": "object",
                    "description": (
                        "Optional custom agent definition (overrides specialist). "
                        "Use this to create a sub-agent with custom prompt and tools."
                    ),
                    "properties": {
                        "system_prompt": {"type": "string"},
                        "tool_allowlist": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "required": ["mission"],
        }

    @property
    def requires_approval(self) -> bool:
        # Sub-agent spawning requires approval (sub-agent may execute risky tools)
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        # Sub-agents can run in parallel (isolated sessions)
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        specialist = kwargs.get("specialist", "unknown")
        mission = kwargs.get("mission", "")
        mission_preview = mission[:150] + "..." if len(mission) > 150 else mission

        return (
            f"🤖 SUB-AGENT EXECUTION\n"
            f"Tool: {self.name}\n"
            f"Specialist: {specialist}\n"
            f"Mission: {mission_preview}"
        )

    async def execute(
        self,
        mission: str,
        specialist: Optional[str] = None,
        planning_strategy: Optional[str] = None,
        agent_definition: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute mission in sub-agent with isolated context.

        Args:
            mission: Mission description for sub-agent
            specialist: Optional specialist profile ("coding", "rag", "wiki")
            planning_strategy: Optional strategy override
            agent_definition: Optional custom agent definition

        Returns:
            Dictionary with:
            - success: bool - True if sub-agent completed successfully
            - result: str - Final answer from sub-agent
            - session_id: str - Sub-agent session ID
            - steps_taken: int - Number of execution steps
            - error: str - Error message (if failed)
        """
        import uuid
        import structlog
        from taskforce.core.domain.models import ExecutionResult

        logger = structlog.get_logger().bind(component="agent_tool")

        # Get parent session from kwargs (injected by ToolExecutor)
        parent_session = kwargs.get("_parent_session_id", "unknown")

        # Generate unique session ID for sub-agent
        sub_session_suffix = specialist or "custom"
        sub_session_id = f"{parent_session}:sub_{sub_session_suffix}_{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                "spawning_sub_agent",
                parent_session=parent_session,
                sub_session_id=sub_session_id,
                specialist=specialist,
                mission_length=len(mission),
                has_custom_definition=agent_definition is not None,
            )

            # Create sub-agent based on specialist or custom definition
            if agent_definition:
                # Custom agent from definition
                sub_agent = await self._factory.create_agent_from_definition(
                    agent_definition=agent_definition,
                    profile=self._profile,
                    work_dir=self._work_dir,
                    planning_strategy=planning_strategy,
                )
            elif specialist:
                # Standard specialist agent
                sub_agent = await self._factory.create_agent(
                    profile=self._profile,
                    specialist=specialist,
                    work_dir=self._work_dir,
                    planning_strategy=planning_strategy,
                )
            else:
                # Generic agent (no specialist)
                sub_agent = await self._factory.create_agent(
                    profile=self._profile,
                    work_dir=self._work_dir,
                    planning_strategy=planning_strategy,
                )

            # Override max_steps if configured
            if self._max_steps:
                sub_agent.max_steps = self._max_steps

            # Execute mission in sub-agent
            logger.debug(
                "executing_sub_agent_mission",
                sub_session_id=sub_session_id,
                max_steps=sub_agent.max_steps,
            )

            result: ExecutionResult = await sub_agent.execute(
                mission=mission,
                session_id=sub_session_id,
            )

            # Cleanup sub-agent resources (MCP connections, etc.)
            await sub_agent.cleanup()

            logger.info(
                "sub_agent_completed",
                sub_session_id=sub_session_id,
                success=result.success,
                steps_taken=result.steps_taken,
            )

            # Return result to parent agent
            return {
                "success": result.success,
                "result": result.final_answer or result.error or "No result",
                "session_id": sub_session_id,
                "steps_taken": result.steps_taken,
                "error": result.error if not result.success else None,
            }

        except Exception as e:
            logger.error(
                "sub_agent_execution_failed",
                sub_session_id=sub_session_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            return {
                "success": False,
                "error": f"Sub-agent execution failed: {str(e)}",
                "error_type": type(e).__name__,
                "session_id": sub_session_id,
            }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        mission = kwargs.get("mission")

        if not mission or not mission.strip():
            return False, "Missing required parameter: mission"

        specialist = kwargs.get("specialist")
        agent_definition = kwargs.get("agent_definition")

        # Must have either specialist or agent_definition
        if not specialist and not agent_definition:
            return False, "Must provide either 'specialist' or 'agent_definition'"

        return True, None
```

**Testing**: Unit tests with mock AgentFactory and Agent.

---

#### Story 1.2: Agent Session Context Injection

**Ziel**: Erweitere `ToolExecutor` um Parent-Session-ID-Injection für AgentTool.

**Location**: `src/taskforce/core/domain/lean_agent_components/tool_executor.py`

**Changes**:

```python
# In ToolExecutor._execute_tool_call():

# Inject parent session ID for AgentTool
if tool_call.tool_name == "call_agent":
    params["_parent_session_id"] = self.session_id
```

**Rationale**: AgentTool braucht Parent-Session-ID für hierarchische Session-IDs.

---

#### Story 1.3: Factory Integration

**Ziel**: Registriere AgentTool in AgentFactory für Orchestrator-Agents.

**Location**: `src/taskforce/application/factory.py`

**Changes**:

```python
# In AgentFactory._get_all_native_tools():
from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool

# Add to tool list only if profile explicitly enables it
tools = [
    # ... existing tools ...
]

# Optionally add AgentTool if config enables orchestration
orchestration_config = config.get("orchestration", {})
if orchestration_config.get("enable_agent_tool", False):
    tools.append(
        AgentTool(
            agent_factory=self,  # Pass factory to AgentTool
            profile=orchestration_config.get("sub_agent_profile", profile),
            work_dir=orchestration_config.get("sub_agent_work_dir"),
            max_steps=orchestration_config.get("sub_agent_max_steps"),
        )
    )

return tools
```

**Config Example** (`configs/orchestrator.yaml`):

```yaml
agent:
  type: generic
  specialist: null  # Orchestrator has no specialist
  planning_strategy: native_react
  max_steps: 50  # Higher for orchestration

orchestration:
  enable_agent_tool: true
  sub_agent_profile: dev
  sub_agent_max_steps: 30

tools:
  - web_search
  - web_fetch
  - file_read
  - file_write
  - ask_user
  # call_agent added automatically via orchestration config

llm:
  config_path: configs/llm_config.yaml
  default_model: main

persistence:
  type: file
  work_dir: .taskforce

logging:
  level: INFO
```

---

### Phase 2: Parallel Execution Support (Story 2)

#### Story 2.1: Parallel Tool Execution Review

**Ziel**: Verifiziere, dass `supports_parallelism=True` für AgentTool korrekt funktioniert.

**Review**: `src/taskforce/core/domain/lean_agent_components/tool_executor.py`

**Expected Behavior**:
- Agent kann mehrere `call_agent` Tool-Calls parallel ausführen
- Jeder Sub-Agent hat isolierten Session-State
- ToolExecutor sammelt alle Results ein

**Test**:

```python
# Test: Orchestrator ruft 2 Sub-Agents parallel auf
async def test_parallel_sub_agent_execution():
    orchestrator = await factory.create_agent(profile="orchestrator")

    result = await orchestrator.execute(
        mission=(
            "Research these topics in parallel: "
            "1. Python async/await best practices "
            "2. PostgreSQL performance optimization"
        ),
        session_id="test-orchestrator-001",
    )

    # Erwartung: LLM ruft call_agent 2x parallel auf
    # Sub-Agents arbeiten unabhängig
    assert result.success
```

---

#### Story 2.2: Session Hierarchy Visualization

**Ziel**: Logging für Parent-Child-Session-Relationships.

**Location**: `src/taskforce/infrastructure/tools/orchestration/agent_tool.py`

**Enhancement**:

```python
# In AgentTool.execute():
logger.info(
    "sub_agent_spawned",
    parent_session=parent_session,
    sub_session=sub_session_id,
    specialist=specialist,
    hierarchy_level=parent_session.count(":") + 1,  # Nesting depth
)
```

**CLI Enhancement**: Session tree visualization in `taskforce sessions list`.

---

### Phase 3: Advanced Features (Story 3)

#### Story 3.1: Sub-Agent Result Summarization

**Problem**: Sub-Agent-Results können sehr groß sein (langes Transcript).

**Solution**: Optional summarization of sub-agent results.

**Config**:

```yaml
orchestration:
  enable_agent_tool: true
  summarize_results: true  # Summarize long sub-agent outputs
  summary_max_length: 2000  # Max chars for result summary
```

**Implementation**: In `AgentTool.execute()`, summarize result if > max_length:

```python
if orchestration_config.get("summarize_results") and len(result.final_answer) > max_length:
    # Use LLM to summarize
    summary = await llm_provider.complete(
        model_alias="fast",
        messages=[{
            "role": "user",
            "content": f"Summarize this result concisely:\n\n{result.final_answer}"
        }]
    )
    return {"success": True, "result": summary, ...}
```

---

#### Story 3.2: Custom Agent Definitions at Runtime

**Goal**: Orchestrator erstellt Sub-Agents mit dynamisch generierten Prompts/Tools.

**Use Case**:
```
Mission: "Create a specialist agent for German tax law and use it to analyze this invoice."

Orchestrator → Generiert custom agent_definition → Ruft call_agent mit definition auf
```

**Implementation**: Already supported via `agent_definition` parameter in AgentTool.

---

#### Story 3.3: Sub-Agent Result Caching

**Problem**: Wiederholte Sub-Agent-Aufrufe mit gleicher Mission verschwenden Tokens.

**Solution**: Cache Sub-Agent-Results basierend auf (mission_hash, specialist, planning_strategy).

**Config**:

```yaml
orchestration:
  enable_result_cache: true
  cache_ttl_seconds: 3600  # Cache for 1 hour
```

**Implementation**: Optional, nice-to-have.

---

### Phase 4: Testing & Documentation (Story 4)

#### Story 4.1: Integration Tests

**Location**: `tests/integration/test_multi_agent_orchestration.py`

**Tests**:
- Simple orchestration (1 sub-agent)
- Parallel orchestration (2+ sub-agents)
- Nested orchestration (sub-agent ruft weiteren sub-agent auf)
- Error handling (sub-agent fails)
- Session isolation (state bleibt getrennt)

---

#### Story 4.2: Documentation

**Updates**:
- `docs/architecture/multi-agent-orchestration.md` (diese Datei → finalisieren)
- `docs/cli.md` → Orchestrator-Beispiele
- `README.md` → Use case examples

**Example**:

```bash
# Create orchestrator agent
taskforce run mission "Research Python FastAPI and React simultaneously" \
  --profile orchestrator

# Output:
# [Agent] Spawning 2 sub-agents in parallel...
# [Sub-Agent 1] Researching Python FastAPI...
# [Sub-Agent 2] Researching React...
# [Agent] Combining results...
```

---

## Configuration Examples

### Orchestrator Profile

```yaml
# configs/orchestrator.yaml
agent:
  type: generic
  specialist: null
  planning_strategy: native_react
  max_steps: 50

orchestration:
  enable_agent_tool: true
  sub_agent_profile: dev
  sub_agent_max_steps: 30
  summarize_results: false

tools:
  - web_search
  - web_fetch
  - file_read
  - file_write
  - ask_user

llm:
  config_path: configs/llm_config.yaml
  default_model: main

persistence:
  type: file
  work_dir: .taskforce
```

---

### Custom Sub-Agent (via agent_definition)

```python
# Orchestrator LLM generiert dieses agent_definition:
agent_definition = {
    "system_prompt": (
        "You are a German tax law expert. "
        "Analyze invoices for VAT compliance and provide recommendations."
    ),
    "tool_allowlist": ["file_read", "python", "web_search"],
}

# Orchestrator ruft call_agent auf:
result = await call_agent(
    mission="Analyze invoice_2024.pdf for VAT compliance",
    agent_definition=agent_definition,
)
```

---

## Migration Path

### Phase 1: Minimal Viable Implementation (MVP)
- ✅ AgentTool implementation
- ✅ Factory integration
- ✅ Basic parallel execution
- ✅ Session isolation

**Timeline**: 1 Sprint (2 weeks)

### Phase 2: Production Hardening
- ✅ Error handling & retries
- ✅ Result summarization
- ✅ Comprehensive testing
- ✅ Documentation

**Timeline**: 1 Sprint (2 weeks)

### Phase 3: Advanced Features
- ⏳ Result caching
- ⏳ Nested orchestration (3+ levels)
- ⏳ Sub-agent monitoring UI

**Timeline**: 1-2 Sprints (optional)

---

## Security Considerations

### Sub-Agent Sandboxing

**Problem**: Sub-Agents können beliebige Tools ausführen.

**Mitigation**:
1. **Tool Allowlists**: Sub-Agents sollten eingeschränkte Toolsets haben
2. **Approval Propagation**: Sub-Agent-Tool-Approvals propagieren zum Parent
3. **Max Steps Limit**: Sub-Agents haben niedrigere max_steps

**Config**:

```yaml
orchestration:
  sub_agent_max_steps: 20  # Lower than orchestrator
  sub_agent_tool_allowlist:  # Optional global allowlist
    - web_search
    - file_read
    # Exclude: file_write, python, shell
```

---

### Session Isolation

**Guarantee**: Sub-Agents können Parent-State **nicht** modifizieren.

**Implementation**:
- Separate Session IDs (`parent:sub_{id}`)
- Separate State Manager calls
- State nur über Tool-Result-Return übertragen

---

## Alternative Designs (Considered & Rejected)

### 1. Shared State Between Agents

**Idea**: Sub-Agents teilen sich State mit Parent.

**Problem**:
- Race conditions bei parallel execution
- Schwer zu debuggen
- Verletzt Isolation-Prinzip

**Fazit**: ❌ Rejected

---

### 2. Agent Protocol (statt Tool)

**Idea**: Neues `AgentProtocol` für Sub-Agents (analog zu ToolProtocol).

**Problem**:
- Mehr Komplexität
- Duplikation von Tool-Infrastruktur
- LLM kann nicht über Function Calling wählen

**Fazit**: ❌ Rejected (Tool-based ist einfacher)

---

### 3. Message-Passing zwischen Agents

**Idea**: Agents kommunizieren via Message Queue (pub/sub).

**Problem**:
- Zu komplex für synchrone Orchestration
- Async message handling schwierig im ReAct-Loop

**Fazit**: ❌ Overkill für current use cases

---

## Open Questions

1. **Nested Orchestration Depth**: Sollten wir max nesting depth limitieren?
   - **Proposal**: Max 3 levels (orchestrator → sub → sub-sub)

2. **Sub-Agent Streaming**: Sollten Sub-Agent-Events zum Parent gestreamt werden?
   - **Proposal**: Optional via `stream_sub_agent_events` config

3. **Sub-Agent Approval**: Wie handlen wir Approval-Flows in Sub-Agents?
   - **Proposal**: Approvals propagieren zum Parent (Parent entscheidet)

4. **Cross-Agent Tool Sharing**: Sollten Sub-Agents Tools vom Parent erben?
   - **Proposal**: Nein, explizite Tool-Konfiguration pro Agent

---

## Success Metrics

### Performance
- Sub-Agent spawning latency: < 2s
- Parallel execution speedup: ~2x für 2 agents
- State isolation: 0 cross-contamination bugs

### Developer Experience
- Clean API: AgentTool registration in 5 lines
- Clear error messages bei nested failures
- Comprehensive logging für debugging

### Production Readiness
- Unit test coverage: ≥90%
- Integration tests: 10+ scenarios
- Documentation: Complete user guide

---

## Next Steps

1. **Review dieses Plans** mit Team
2. **Create Stories** in Backlog (basierend auf Phases)
3. **Spike**: Proof-of-Concept für AgentTool (1-2 Tage)
4. **Implementation**: Start mit Phase 1 (MVP)

---

## Appendix: Example Usage

### Example 1: Research Assistant

```python
# Orchestrator mission
mission = """
Research the following topics and create a summary report:
1. Latest trends in LLM architecture (2024-2025)
2. Best practices for RAG systems
3. Multi-agent orchestration patterns

For each topic, use a specialist sub-agent:
- Topic 1: Use 'rag' specialist with web_search
- Topic 2: Use 'rag' specialist with semantic_search
- Topic 3: Use generic agent with web_search
"""

# Orchestrator uses call_agent tool:
# call_agent(specialist="rag", mission="Research latest trends in LLM architecture...")
# call_agent(specialist="rag", mission="Research best practices for RAG systems...")
# call_agent(mission="Research multi-agent orchestration patterns...")

# Results combined into final report
```

---

### Example 2: Code Review + Documentation

```python
# Orchestrator mission
mission = """
Review the codebase and:
1. Analyze code quality (use 'coding' specialist)
2. Generate API documentation (use 'coding' specialist)
3. Write user guide (use generic agent)
"""

# Parallel execution:
# call_agent(specialist="coding", mission="Analyze code quality in src/...")
# call_agent(specialist="coding", mission="Generate API docs from src/...")
# call_agent(mission="Write user guide based on README.md...")
```

---

### Example 3: Custom Agent at Runtime

```python
# Orchestrator mission
mission = """
Create a specialist agent for German accounting and use it to:
1. Analyze invoice_2024.pdf
2. Check VAT compliance
3. Generate compliance report
"""

# Orchestrator generates agent_definition:
agent_definition = {
    "system_prompt": "You are a German accounting expert specializing in VAT compliance...",
    "tool_allowlist": ["file_read", "python", "web_search"],
}

# Then calls:
# call_agent(mission="Analyze invoice_2024.pdf...", agent_definition=agent_definition)
```

---

**Ende des Plans**

---

## Feedback & Iteration

Bitte feedback geben zu:
1. Ist Tool-based Approach der richtige Weg?
2. Sind die Security Considerations ausreichend?
3. Fehlen wichtige Use Cases?
4. Sollten wir mit einem einfacheren Ansatz starten?
