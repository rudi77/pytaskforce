# Story 3: CLI und Server Streaming Integration

**Status:** Ready for Review  
**Epic:** [Epic 7: Streaming-Support für LeanAgent](../epics/epic-7-lean-agent-streaming.md)  
**Priorität:** Hoch  
**Schätzung:** 5 SP  
**Abhängigkeiten:** Story 2 (LeanAgent Streaming)  

## Description

Als **Benutzer** möchte ich im CLI und über die API Streaming-Events in Echtzeit sehen, damit ich den Fortschritt des Agenten live verfolgen kann.

Diese Story integriert das LeanAgent-Streaming in die beiden Hauptkonsumenten: CLI (mit Rich Live Display) und Server (mit SSE).

## Technical Details

### 1. AgentExecutor True Streaming

Aktualisiere `_execute_streaming()` im AgentExecutor, um echtes Streaming zu nutzen:

```python
# application/executor.py

async def _execute_streaming(
    self, agent: Agent | LeanAgent, mission: str, session_id: str
) -> AsyncIterator[ProgressUpdate]:
    """Execute agent with true streaming progress updates."""
    
    # Check if agent supports streaming
    if hasattr(agent, "execute_stream"):
        # True streaming: yield events as they happen
        async for event in agent.execute_stream(mission, session_id):
            yield self._stream_event_to_progress_update(event)
    else:
        # Fallback: post-hoc streaming from execution history
        result = await agent.execute(mission=mission, session_id=session_id)
        
        for event in result.execution_history:
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=event.get("type", "unknown"),
                message=self._format_event_message(event),
                details=event,
            )
        
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="complete",
            message=result.final_message,
            details={"status": result.status, "session_id": result.session_id},
        )

def _stream_event_to_progress_update(self, event: StreamEvent) -> ProgressUpdate:
    """Convert StreamEvent to ProgressUpdate for API consumers."""
    message_map = {
        "step_start": lambda d: f"Step {d.get('step', '?')} starting...",
        "llm_token": lambda d: d.get("content", ""),
        "tool_call": lambda d: f"🔧 Calling: {d.get('tool', 'unknown')}",
        "tool_result": lambda d: f"{'✅' if d.get('success') else '❌'} {d.get('tool', 'unknown')}: {d.get('output', '')[:50]}",
        "plan_updated": lambda d: f"📋 Plan updated ({d.get('action', 'unknown')})",
        "final_answer": lambda d: d.get("content", ""),
        "error": lambda d: f"⚠️ Error: {d.get('message', 'unknown')}",
    }
    
    message_fn = message_map.get(event.event_type, lambda d: str(d))
    
    return ProgressUpdate(
        timestamp=event.timestamp,
        event_type=event.event_type,
        message=message_fn(event.data),
        details=event.data,
    )
```

### 2. CLI Streaming Integration

Erweitere den CLI `run` Command mit `--stream` Flag und Rich Live Display:

```python
# api/cli/commands/run.py

import typer
from rich.live import Live
from rich.panel import Panel
from rich.console import Group
from rich.text import Text
from rich.spinner import Spinner

@app.command()
def mission(
    mission_text: str = typer.Argument(..., help="Mission to execute"),
    profile: str = typer.Option("dev", "--profile", "-p", help="Configuration profile"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
    stream: bool = typer.Option(False, "--stream", help="Enable streaming output"),
    lean: bool = typer.Option(False, "--lean", help="Use LeanAgent"),
):
    """Execute a mission."""
    
    if stream:
        asyncio.run(_execute_streaming_mission(mission_text, profile, session_id, lean))
    else:
        # Existing non-streaming execution
        asyncio.run(_execute_mission(mission_text, profile, session_id, lean))


async def _execute_streaming_mission(
    mission: str,
    profile: str,
    session_id: Optional[str],
    lean: bool,
):
    """Execute mission with streaming Rich display."""
    from taskforce.application.executor import AgentExecutor
    
    executor = AgentExecutor()
    console = Console()
    
    # State for live display
    current_step = 0
    current_tool = None
    tool_results: list[str] = []
    final_answer_tokens: list[str] = []
    
    def build_display() -> Group:
        """Build Rich display group for current state."""
        elements = []
        
        # Header
        elements.append(Text(f"🚀 Mission: {mission[:60]}...", style="bold cyan"))
        elements.append(Text(f"📋 Step: {current_step}", style="dim"))
        
        # Current tool (if any)
        if current_tool:
            elements.append(Panel(
                Text(f"🔧 {current_tool}", style="yellow"),
                title="Current Tool",
                border_style="yellow",
            ))
        
        # Recent tool results
        if tool_results:
            results_text = "\n".join(tool_results[-5:])  # Last 5 results
            elements.append(Panel(
                Text(results_text, style="green"),
                title="Tool Results",
                border_style="green",
            ))
        
        # Streaming final answer
        if final_answer_tokens:
            answer_text = "".join(final_answer_tokens)
            elements.append(Panel(
                Text(answer_text, style="white"),
                title="💬 Answer",
                border_style="blue",
            ))
        
        return Group(*elements)
    
    with Live(build_display(), console=console, refresh_per_second=10) as live:
        async for update in executor.execute_mission_streaming(
            mission=mission,
            profile=profile,
            session_id=session_id,
            use_lean_agent=lean,
        ):
            event_type = update.event_type
            
            if event_type == "step_start":
                current_step = update.details.get("step", current_step + 1)
                current_tool = None
            
            elif event_type == "tool_call":
                current_tool = update.details.get("tool", "unknown")
            
            elif event_type == "tool_result":
                tool = update.details.get("tool", "unknown")
                success = "✅" if update.details.get("success") else "❌"
                output = update.details.get("output", "")[:100]
                tool_results.append(f"{success} {tool}: {output}")
                current_tool = None
            
            elif event_type == "llm_token":
                # Only collect tokens for final answer (not during tool calls)
                if not current_tool:
                    final_answer_tokens.append(update.details.get("content", ""))
            
            elif event_type == "final_answer":
                # If we didn't get streaming tokens, use the full content
                if not final_answer_tokens:
                    final_answer_tokens.append(update.details.get("content", ""))
            
            elif event_type == "error":
                console.print(f"[red]Error: {update.message}[/red]")
            
            live.update(build_display())
    
    # Final summary
    console.print()
    console.print(Panel(
        "".join(final_answer_tokens) if final_answer_tokens else "No answer generated",
        title="✅ Final Answer",
        border_style="green",
    ))
```

### 3. Server SSE True Streaming

Der Server-Endpoint nutzt bereits SSE. Mit dem aktualisierten `_execute_streaming()` werden Events jetzt in Echtzeit gestreamt:

```python
# api/routes/execution.py (keine Änderungen nötig, da _execute_streaming jetzt echtes Streaming macht)

@router.post("/execute/stream")
async def execute_mission_stream(request: ExecuteMissionRequest):
    """Execute agent mission with streaming progress via SSE."""
    # ... existing code ...
    
    async def event_generator():
        async for update in executor.execute_mission_streaming(
            mission=request.mission,
            profile=request.profile,
            session_id=request.session_id,
            conversation_history=request.conversation_history,
            user_context=user_context,
            use_lean_agent=request.lean,
        ):
            # Events werden jetzt in Echtzeit geliefert (nicht mehr post-hoc)
            data = json.dumps(asdict(update), default=str)
            yield f"data: {data}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 4. CLI Help und Dokumentation

Aktualisiere CLI Help-Texte:

```python
# --stream Flag Help
stream: bool = typer.Option(
    False, 
    "--stream", "-S",
    help="Enable real-time streaming output. Shows tool calls, results, and answer as they happen.",
)
```

### 5. Tests

```python
# tests/unit/cli/test_streaming_integration.py

class TestCLIStreaming:
    """Tests for CLI streaming integration."""
    
    @pytest.mark.asyncio
    async def test_streaming_displays_tool_calls(self, mock_executor):
        """Test that tool calls are displayed during streaming."""
        # Setup mock executor to yield tool_call events
        mock_executor.execute_mission_streaming.return_value = async_generator([
            ProgressUpdate(..., event_type="step_start", ...),
            ProgressUpdate(..., event_type="tool_call", details={"tool": "web_search"}),
            ProgressUpdate(..., event_type="tool_result", details={"tool": "web_search", "success": True}),
            ProgressUpdate(..., event_type="final_answer", details={"content": "Answer"}),
        ])
        
        # Execute streaming mission
        # Verify that display updates were made for each event

# tests/integration/test_server_streaming.py

class TestServerSSEStreaming:
    """Tests for Server SSE streaming."""
    
    @pytest.mark.asyncio
    async def test_sse_yields_events_in_realtime(self, test_client):
        """Test that SSE endpoint yields events as they happen."""
        response = await test_client.post("/api/v1/execute/stream", json={
            "mission": "Test mission",
            "profile": "dev",
            "lean": True,
        })
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        
        # Verify events include intermediate steps
        event_types = [e["event_type"] for e in events]
        assert "step_start" in event_types
        assert "tool_call" in event_types or "final_answer" in event_types
```

## Acceptance Criteria

- [x] **CLI --stream Flag:** `run mission --stream` Flag aktiviert Streaming-Output
- [x] **CLI Live Display:** Rich Live Display zeigt Updates in Echtzeit (Tool Calls, Results)
- [x] **CLI Token Streaming:** Finale Antwort wird Token-für-Token angezeigt
- [x] **Server SSE Realtime:** `/execute/stream` yieldet Events während der Ausführung (nicht erst am Ende)
- [x] **AgentExecutor Integration:** `_execute_streaming()` nutzt `agent.execute_stream()` wenn verfügbar
- [x] **Fallback:** Graceful Degradation wenn Agent kein Streaming unterstützt
- [x] **Backward Compatibility:** CLI ohne `--stream` verhält sich wie bisher
- [x] **Backward Compatibility:** Server `/execute` (non-streaming) unverändert
- [x] **Tests:** Integration Tests für CLI und Server Streaming

## Integration Notes

- CLI nutzt Rich `Live` Context für flicker-free Updates
- Server SSE Format bleibt kompatibel (ProgressUpdate dataclass)
- AgentExecutor erkennt automatisch ob Agent Streaming unterstützt
- Beide Consumers (CLI/Server) nutzen den gleichen Executor-Code

## Definition of Done

- [x] CLI `--stream` Flag implementiert
- [x] Rich Live Display für Streaming-Output
- [x] AgentExecutor `_execute_streaming()` nutzt echtes Streaming
- [x] Integration Tests für CLI Streaming
- [x] Integration Tests für Server SSE Streaming
- [x] CLI Help-Texte aktualisiert
- [x] Keine Regression in non-streaming Pfaden

---

## Risk Assessment

**Primary Risk:** Rich Live Display kann bei schnellen Updates flackern

**Mitigation:**
- `refresh_per_second=10` limitiert Update-Frequenz
- Token-Events werden gesammelt statt einzeln gerendert
- Fallback auf einfachen Print wenn Live nicht verfügbar

**Secondary Risk:** SSE-Verbindung bricht bei langen Executions ab

**Mitigation:**
- Keep-alive Events können hinzugefügt werden (future enhancement)
- Client-seitige Reconnection-Logic (API consumer responsibility)

**Rollback:** 
- CLI: `--stream` Flag entfernen
- Server: `_execute_streaming()` auf post-hoc Fallback zurücksetzen

---

## Technical References

| File | Änderungen |
|------|------------|
| `application/executor.py` | `_execute_streaming()` für echtes Streaming |
| `api/cli/commands/run.py` | `--stream` Flag und Rich Live Display |
| `api/routes/execution.py` | Keine Änderungen (nutzt bereits SSE) |
| `tests/integration/test_cli_streaming.py` | Neue Tests |
| `tests/integration/test_server_streaming.py` | Neue Tests |

---

## Dev Agent Record

### Agent Model Used
Claude Opus 4.5 (claude-sonnet-4-20250514)

### File List
| File | Action | Description |
|------|--------|-------------|
| `src/taskforce/application/executor.py` | Modified | True streaming in _execute_streaming() with execute_stream() detection and _stream_event_to_progress_update() conversion |
| `src/taskforce/api/cli/commands/run.py` | Modified | Added --stream/-S flag, Rich Live display with _execute_streaming_mission() |
| `src/taskforce/api/cli/commands/chat.py` | Modified | Added --stream/-S flag, Rich Live display with _execute_streaming_chat() |
| `tests/integration/test_cli_streaming.py` | Created | 9 CLI streaming integration tests |
| `tests/integration/test_server_streaming.py` | Created | 12 Server SSE integration tests |

### Change Log
| Date | Change |
|------|--------|
| 2025-12-04 | Implemented CLI `run mission --stream` flag with Rich Live Display |
| 2025-12-04 | Updated AgentExecutor._execute_streaming() for true streaming |
| 2025-12-04 | Added _stream_event_to_progress_update() for StreamEvent conversion |
| 2025-12-04 | Created integration tests for CLI and Server streaming (21 tests) |
| 2025-12-04 | Added `chat chat --stream` flag with Rich Live Display |

