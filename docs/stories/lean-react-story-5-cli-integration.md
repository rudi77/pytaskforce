# Story 5: CLI Integration des LeanAgent

**Status:** Implemented
**Epic:** [Epic 6: Transition zu "Lean ReAct" Architektur](taskforce/docs/epics/epic-6-lean-react-transition.md)
**Priorität:** Hoch
**Schätzung:** 3 SP
**Abhängigkeiten:** Story 1-4 (LeanAgent vollständig implementiert)

## Description

Als **Entwickler/Benutzer** möchte ich den neuen `LeanAgent` über die CLI nutzen können, damit ich von der vereinfachten Architektur und dem robusteren Native Tool Calling profitiere.

Hierfür wird die `AgentFactory` um eine `create_lean_agent()` Methode erweitert. Der `ApplicationExecutor` erhält einen Parameter, um zwischen Legacy `Agent` und `LeanAgent` zu wählen. Die CLI bekommt ein optionales Flag `--lean` (oder Config-Option).

## Technical Details

### 1. Factory-Erweiterung: `create_lean_agent()`

Füge eine neue Methode zur `AgentFactory` hinzu:

```python
async def create_lean_agent(
    self,
    profile: str = "dev",
    specialist: Optional[str] = None,
    work_dir: Optional[str] = None,
) -> LeanAgent:
    """
    Create LeanAgent with specified profile.
    
    Uses the simplified ReAct loop with native tool calling
    and PlannerTool for dynamic plan management.
    """
    config = self._load_profile(profile)
    
    # Reuse existing infrastructure creation
    state_manager = self._create_state_manager(config, work_dir)
    llm_provider = self._create_llm_provider(config)
    tools = self._create_tools(config, specialist)
    
    # Use LEAN_KERNEL_PROMPT or specialist prompt
    system_prompt = self._assemble_lean_system_prompt(specialist)
    
    return LeanAgent(
        state_manager=state_manager,
        llm_provider=llm_provider,
        tools=tools,
        system_prompt=system_prompt,
    )
```

### 2. Executor-Anpassung

Erweitere `ApplicationExecutor` um einen `use_lean_agent` Parameter:

```python
async def execute_mission(
    self,
    session_id: str,
    mission: str,
    profile: str = "dev",
    use_lean_agent: bool = False,  # NEU
    ...
) -> ExecutionResult:
    if use_lean_agent:
        agent = await self.factory.create_lean_agent(profile)
    else:
        agent = await self.factory.create_agent(profile)
    ...
```

### 3. CLI Flag (Optional in dieser Story)

In `cli/commands/run.py` oder `chat.py`:

```python
@app.command()
def run_mission(
    mission: str,
    lean: bool = typer.Option(False, "--lean", help="Use LeanAgent"),
    ...
):
    result = executor.execute_mission(..., use_lean_agent=lean)
```

## Acceptance Criteria

- [x] **Factory-Methode:** `AgentFactory.create_lean_agent()` existiert und funktioniert.
- [x] **Tool-Integration:** `LeanAgent` erhält alle konfigurierten Tools inkl. `PlannerTool`.
- [x] **Prompt-Integration:** System-Prompt wird korrekt mit `LEAN_KERNEL_PROMPT` gebaut.
- [x] **Executor-Support:** `ApplicationExecutor` kann zwischen `Agent` und `LeanAgent` wählen.
- [x] **Backward Compatibility:** Ohne `--lean` Flag wird weiterhin der Legacy `Agent` verwendet.
- [x] **CLI-Flag:** `--lean` Flag aktiviert `LeanAgent` in der CLI.

## Integration Notes

*   Die `LeanAgent` Klasse ist bereits vollständig implementiert (Stories 1-4).
*   Die bestehenden Helper-Methoden der Factory (`_create_state_manager`, `_create_llm_provider`, `_create_tools`) können wiederverwendet werden.
*   Der Legacy `Agent` bleibt als Default, um Regressions zu vermeiden.

## Testing Strategy

### Unit Tests
- `test_factory_create_lean_agent()`: Verifiziert, dass `LeanAgent` korrekt erstellt wird
- `test_factory_lean_agent_has_planner_tool()`: Verifiziert PlannerTool Injektion
- `test_executor_with_lean_agent()`: Verifiziert Executor-Integration

### Integration Tests (optional)
- End-to-End Test: CLI mit `--lean` Flag führt Mission erfolgreich aus

## Definition of Done

- [x] `create_lean_agent()` Methode in `AgentFactory` implementiert.
- [x] `ApplicationExecutor` unterstützt `use_lean_agent` Parameter.
- [x] Unit Tests für Factory-Methode bestehen (8 Tests).
- [x] Backward Compatibility verifiziert (Legacy Agent funktioniert weiterhin).
- [x] CLI `--lean` Flag implementiert.

## Risk Assessment

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Breaking Change in CLI | Niedrig | Hoch | `--lean` ist opt-in, Default bleibt Legacy |
| Tool-Inkompatibilität | Niedrig | Mittel | Reuse bestehender `_create_tools()` Logik |
| Config-Drift | Niedrig | Niedrig | Reuse bestehender Profile-Loading |

## Rollback Plan

Falls Probleme auftreten:
1. `--lean` Flag entfernen (CLI)
2. `use_lean_agent` Parameter entfernen (Executor)
3. `create_lean_agent()` Methode entfernen (Factory)

Git Revert ist einfach, da keine Breaking Changes am Legacy-Pfad.

---

## Dev Agent Record

### File List

| File | Status | Description |
|------|--------|-------------|
| `src/taskforce/application/factory.py` | ✅ Modified | Added `create_lean_agent()` and `_assemble_lean_system_prompt()` methods, `user_context` support |
| `src/taskforce/application/executor.py` | ✅ Modified | Added `use_lean_agent` parameter to `execute_mission()`, `execute_mission_streaming()`, `_create_agent()` |
| `src/taskforce/api/cli/commands/run.py` | ✅ Modified | Added `--lean` / `-l` flag to `run_mission` command |
| `src/taskforce/api/cli/commands/chat.py` | ✅ Modified | Added `--lean` / `-l` flag to `chat` command with RAG context support |
| `src/taskforce/api/routes/execution.py` | ✅ Modified | Added `lean` field to `ExecuteMissionRequest` for API integration |
| `src/taskforce/core/domain/lean_agent.py` | ✅ Modified | Added `conversation_history` support for multi-turn chat |
| `tests/unit/test_factory.py` | ✅ Modified | Added `TestLeanAgentFactory` class with 8 tests |

### Debug Log References
- No errors encountered during implementation
- All 8 new tests pass

### Completion Notes
- `create_lean_agent()` reuses existing factory infrastructure (`_create_state_manager`, `_create_llm_provider`, `_create_native_tools`, `_create_mcp_tools`)
- `_assemble_lean_system_prompt()` uses `LEAN_KERNEL_PROMPT` as base, supports specialist overlay
- `LeanAgent` auto-injects `PlannerTool` if not present in tools list
- Backward compatibility preserved: default behavior (no `--lean` flag) uses legacy `Agent`
- Type hints use `Agent | LeanAgent` union for flexibility
- **Multi-turn chat**: `LeanAgent` now loads `conversation_history` from state for context
- **API integration**: `POST /execute` and `/execute/stream` accept `lean: true` parameter
- **RAG + Lean**: `create_lean_agent()` accepts `user_context` for RAG tool security filtering

### Change Log
| Date | Change |
|------|--------|
| 2025-12-04 | Story created by PM (John) |
| 2025-12-04 | Story implemented by Dev Agent |


