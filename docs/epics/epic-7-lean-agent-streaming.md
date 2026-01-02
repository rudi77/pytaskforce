# Epic 7: Streaming-Support für LeanAgent - Brownfield Enhancement

<!-- Powered by BMAD™ Core -->

**Status:** Draft  
**Priorität:** Hoch  
**Owner:** Development Team  
**Geschätzter Aufwand:** M (Medium) - 3 Stories  

### Story Status Overview

| Story | Title | Status | SP | Abhängigkeiten |
|-------|-------|--------|-----|----------------|
| 1 | [LLM Provider Streaming](../stories/streaming-story-1-llm-provider.md) | 📝 Draft | 5 | - |
| 2 | [LeanAgent Streaming Execution](../stories/streaming-story-2-lean-agent.md) | 📝 Draft | 8 | Story 1 |
| 3 | [CLI und Server Integration](../stories/streaming-story-3-cli-server.md) | 📝 Draft | 5 | Story 2 |

**Gesamt Story Points:** 18 SP

## 1. Epic Goal

Echtzeit-Streaming im `LeanAgent` implementieren, damit Benutzer Zwischenschritte (Tool-Aufrufe, Ergebnisse) und Token-Output während der Ausführung live verfolgen können – sowohl im CLI als auch über die Server-API (SSE).

---

## 2. Epic Description

### Existing System Context

| Komponente | Aktueller Stand |
|------------|-----------------|
| **LeanAgent** (`core/domain/lean_agent.py`) | `execute()` kehrt erst nach vollständiger Ausführung zurück. Kein Streaming während der Loop-Iteration. |
| **LLMProviderProtocol** (`core/interfaces/llm.py`) | `complete()` Methode – blockiert bis Antwort komplett. Keine `stream` Option. |
| **AgentExecutor** (`application/executor.py`) | `_execute_streaming()` ist **post-hoc**: iteriert über `result.execution_history` *nach* Completion. |
| **Server API** (`api/routes/execution.py`) | `/execute/stream` Endpoint existiert (SSE), aber streamt erst nach Ausführungsende. |
| **CLI** (`api/cli/commands/run.py`) | Kein Live-Progress-Display während Execution. |

**Technology Stack:**  
- Python 3.11, asyncio, async generators
- LiteLLM/OpenAI SDK (supports streaming via `stream=True`)
- FastAPI SSE (`StreamingResponse`)
- Rich (CLI output library – bereits als Dependency)

**Integration Points:**
- `LeanAgent.execute()` → neues `execute_stream()` mit `AsyncIterator[StreamEvent]`
- `LLMProviderProtocol` → neue `complete_stream()` Methode
- `AgentExecutor` → echtes Streaming statt post-hoc
- CLI → Live-Display mit Rich `Live` oder `Progress`

### Enhancement Details

**Was geändert wird:**

1. **LLM Provider Streaming:**  
   Neue `complete_stream()` Methode im Protocol, die `AsyncIterator[dict]` yieldet (Token-Chunks, Tool-Calls).

2. **LeanAgent Streaming:**  
   Neue `execute_stream()` Methode, die `AsyncIterator[StreamEvent]` yieldet:
   - `step_start`: Loop-Iteration startet
   - `llm_token`: Token-Chunk vom LLM
   - `tool_call`: Tool wird aufgerufen
   - `tool_result`: Tool-Ergebnis
   - `final_answer`: Execution abgeschlossen

3. **AgentExecutor True Streaming:**  
   `_execute_streaming()` nutzt `agent.execute_stream()` statt post-hoc Iteration.

4. **CLI Live Display:**  
   `run` Command zeigt während Execution:
   - Aktueller Step (z.B. "🔧 Calling: web_search")
   - Tool-Ergebnisse (gekürzt)
   - Streaming-Text für finale Antwort

5. **Server SSE Integration:**  
   `/execute/stream` yieldet Events in Echtzeit während Execution.

**Wie es integriert wird:**
- Neue Methoden neben bestehenden (keine Breaking Changes)
- `execute()` bleibt unverändert für Backward Compatibility
- CLI bekommt `--stream` Flag (opt-in)
- Server nutzt automatisch Streaming wenn verfügbar

**Success Criteria:**
- Benutzer sieht Tool-Aufrufe **während** sie passieren (nicht erst am Ende)
- Token-Streaming für finale Antwort (sichtbar im CLI und SSE)
- Keine Regression in nicht-streaming Ausführung
- < 100ms Latenz zwischen Event und Anzeige

---

## 3. Stories

### Story 1: LLM Provider Streaming Support

**Ziel:** Streaming-Methode zum LLM Provider hinzufügen.

**Änderungen:**
- `core/interfaces/llm.py`: Neue `complete_stream()` Methode im Protocol
- `infrastructure/llm/litellm_provider.py`: Implementierung mit `stream=True`

**Interface:**

```python
async def complete_stream(
    self,
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> AsyncIterator[dict[str, Any]]:
    """
    Yields:
        {"type": "token", "content": "..."} - Text chunk
        {"type": "tool_call_start", "tool": "...", "id": "..."} - Tool invocation begins
        {"type": "tool_call_args", "delta": "..."} - Argument chunk
        {"type": "done", "usage": {...}} - Stream complete
    """
```

**Akzeptanzkriterien:**
- [ ] `complete_stream()` yieldet Token-Chunks in Echtzeit
- [ ] Tool-Calls werden korrekt als Events gestreamt
- [ ] Usage Statistics am Ende verfügbar
- [ ] Fehlerbehandlung mit `{"type": "error", "message": "..."}` Event
- [ ] Bestehende `complete()` Methode unverändert

---

### Story 2: LeanAgent Streaming Execution

**Ziel:** `LeanAgent` kann Events während der Ausführung yielden.

**Änderungen:**
- `core/domain/lean_agent.py`: Neue `execute_stream()` Methode
- `core/domain/models.py`: Neues `StreamEvent` Dataclass

**Stream Event Types:**

```python
@dataclass
class StreamEvent:
    """Event emitted during streaming execution."""
    event_type: Literal[
        "step_start",      # New loop iteration
        "llm_token",       # Token from LLM
        "tool_call",       # Tool invocation
        "tool_result",     # Tool completed
        "plan_updated",    # PlannerTool updated plan
        "final_answer",    # Execution complete
        "error",           # Error occurred
    ]
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
```

**Execution Flow:**

```python
async def execute_stream(
    self, mission: str, session_id: str
) -> AsyncIterator[StreamEvent]:
    # ... setup ...
    
    while step < self.MAX_STEPS:
        yield StreamEvent("step_start", {"step": step})
        
        # Stream LLM response
        async for chunk in self.llm_provider.complete_stream(...):
            if chunk["type"] == "token":
                yield StreamEvent("llm_token", chunk)
            elif chunk["type"] == "tool_call_start":
                yield StreamEvent("tool_call", {"tool": chunk["tool"]})
        
        # Execute tools
        for tool_call in tool_calls:
            result = await self._execute_tool(...)
            yield StreamEvent("tool_result", {"tool": ..., "result": ...})
    
    yield StreamEvent("final_answer", {"content": final_message})
```

**Akzeptanzkriterien:**
- [ ] `execute_stream()` yieldet Events während jeder Loop-Iteration
- [ ] Tool-Aufrufe erzeugen `tool_call` + `tool_result` Events
- [ ] Token-Streaming für LLM-Antworten
- [ ] Plan-Updates erzeugen `plan_updated` Events
- [ ] Bestehende `execute()` Methode funktioniert unverändert
- [ ] State-Persistence nach Streaming-Execution

---

### Story 3: CLI und Server Streaming Integration

**Ziel:** CLI und Server nutzen das neue Streaming.

**CLI Änderungen (`api/cli/commands/run.py`):**
- Neues `--stream` / `-s` Flag
- Live-Display mit Rich `Live` Context:

```
🚀 Starting mission...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Step 1
🔧 Calling: web_search("Python async streaming")
✅ web_search: Found 5 results
📋 Step 2  
🔧 Calling: manage_plan(action="mark_done", step_index=0)
✅ Plan updated

💬 Final Answer:
Based on my research, Python async streaming...
```

**Server Änderungen (`api/routes/execution.py`):**
- `/execute/stream` nutzt `agent.execute_stream()` wenn verfügbar
- SSE Events in Echtzeit:

```
data: {"event_type": "step_start", "data": {"step": 1}}

data: {"event_type": "tool_call", "data": {"tool": "web_search"}}

data: {"event_type": "llm_token", "data": {"content": "Based"}}
```

**Executor Änderungen (`application/executor.py`):**
- `_execute_streaming()` prüft auf `execute_stream()` Methode
- Fallback auf post-hoc Streaming für Legacy Agent

**Akzeptanzkriterien:**
- [ ] CLI `--stream` Flag zeigt Live-Progress
- [ ] Tool-Aufrufe werden in Echtzeit angezeigt (nicht erst am Ende)
- [ ] Token-Streaming für finale Antwort sichtbar
- [ ] Server SSE Events in Echtzeit
- [ ] Graceful Degradation wenn Agent kein Streaming unterstützt
- [ ] Keine Breaking Changes an bestehenden CLI/API Contracts

---

## 4. Compatibility Requirements

- [x] Existing APIs remain unchanged (`execute()` bleibt)
- [x] Database schema changes are backward compatible (keine DB-Änderungen)
- [x] CLI behavior unchanged without `--stream` flag
- [x] Server `/execute` (non-streaming) endpoint unchanged
- [x] Performance impact minimal (async generators sind effizient)

---

## 5. Risk Mitigation

**Primary Risk:** Streaming-Logik erhöht Komplexität im LeanAgent

**Mitigation:**
- `execute_stream()` ist separate Methode – `execute()` bleibt simpel
- Streaming-Logik in eigener Methode/Klasse kapseln wenn zu komplex
- Umfangreiche Integration Tests für beide Pfade

**Secondary Risk:** LLM Provider API-Änderungen bei Streaming

**Mitigation:**
- Abstraction Layer im LLM Provider
- Fallback auf non-streaming wenn Streaming fehlschlägt
- Error Events für graceful degradation

**Rollback Plan:**
- Neue Methoden sind additiv – Entfernen hat keine Side Effects
- CLI `--stream` Flag ist opt-in
- Server kann auf post-hoc Streaming zurückfallen

---

## 6. Definition of Done

- [ ] Alle 3 Stories completed mit Akzeptanzkriterien erfüllt
- [ ] Bestehende Funktionalität verifiziert durch Test-Suite
- [ ] CLI zeigt Live-Progress bei `--stream` Flag
- [ ] Server SSE Events werden in Echtzeit gestreamt
- [ ] Integration Tests für Streaming-Pfad
- [ ] Keine Regression in non-streaming Execution
- [ ] Dokumentation aktualisiert (CLI --help, API docs)

---

## 7. Validation Checklist

### Scope Validation

- [x] Epic kann in 3 Stories completed werden
- [x] Keine Architektur-Dokumentation erforderlich (additives Feature)
- [x] Enhancement folgt bestehenden Patterns (Protocol, async generators)
- [x] Integrations-Komplexität ist manageable

### Risk Assessment

- [x] Risiko für bestehendes System ist gering (neue Methoden, keine Änderung bestehender)
- [x] Rollback-Plan ist machbar (Methoden entfernen)
- [x] Testing-Ansatz deckt bestehende Funktionalität ab
- [x] Team hat ausreichend Wissen über Integration Points

### Completeness Check

- [x] Epic-Ziel ist klar und erreichbar
- [x] Stories sind angemessen abgegrenzt
- [x] Success Criteria sind messbar
- [x] Dependencies sind identifiziert

---

## 8. Technical References

| File | Relevante Bereiche |
|------|-------------------|
| `core/domain/lean_agent.py` | `execute()` Loop (Zeilen 133-289) |
| `core/interfaces/llm.py` | `LLMProviderProtocol.complete()` (Zeilen 49-133) |
| `application/executor.py` | `_execute_streaming()` (Zeilen 355-412) |
| `api/routes/execution.py` | `/execute/stream` Endpoint (Zeilen 76-104) |
| `api/cli/commands/run.py` | CLI run command |

---

## 9. Story Manager Handoff

**Story Manager Handoff:**

"Please develop detailed user stories for this brownfield epic. Key considerations:

- This is an enhancement to an existing system running **Python 3.11, asyncio, LiteLLM, FastAPI**
- **Integration Points**: `LeanAgent.execute()`, `LLMProviderProtocol`, `AgentExecutor`, CLI, Server API
- **Existing Patterns**: Protocol interfaces, async generators, SSE streaming
- **Critical Compatibility Requirements**: 
  - `execute()` must remain unchanged
  - CLI without `--stream` behaves as before
  - Server `/execute` endpoint unchanged
- Each story must include verification that existing functionality remains intact

The epic should maintain system integrity while delivering **real-time streaming visibility into agent execution**."

---

*Epic erstellt basierend auf Code-Analyse vom 04.12.2025*

