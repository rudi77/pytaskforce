<!-- Powered by BMAD™ Core -->

# Epic 9: Pattern A (Context Pack / Rehydration) + Token-Budget Guardrails für LeanAgent - Brownfield Enhancement

## Epic Goal

Den `LeanAgent` **generisch** und **token-budget-stabil** machen, indem große Tool-Ergebnisse **nicht mehr roh** in die Message-History geschrieben werden, sondern als **Handles** ausgelagert werden. Vor jedem LLM-Call wird deterministisch ein **budgetiertes Context Pack** gebaut (Pattern A), sodass Token-Overflows („input tokens exceed limit“) nicht mehr auftreten.

## Epic Description

### Existing System Context

- **Current relevant functionality:**
  - `LeanAgent` (`taskforce/src/taskforce/core/domain/lean_agent.py`) nutzt **Native Tool Calling** und hängt Tool-Resultate direkt an `messages` an (`messages.append(tool_result_to_message(..., tool_result))`).
  - Tool-Resultate werden in `tool_result_to_message()` als JSON serialisiert und zwar mit einer **sehr großen** Standard-Trunkierung (`max_output_chars=20000`), was weiterhin zu großen Prompts führt.
  - Message-Compression (`LeanAgent._compress_messages`) triggert anhand **Message Count** (`SUMMARY_THRESHOLD=20`) und baut den Summary-Prompt via `json.dumps(old_messages, indent=2)` — das kann bei Tool-Heavy Sessions massiv eskalieren.

- **Technology stack:** Python 3.11, asyncio, LiteLLM/OpenAI tool calling, FastAPI, Typer/Rich, Clean Architecture (Core/Application/Infrastructure), structlog.

- **Integration points (konkret):**
  - `taskforce/src/taskforce/core/domain/lean_agent.py`: Tool execution loop (`execute()` und `execute_stream()`), `_compress_messages()`
  - `taskforce/src/taskforce/infrastructure/tools/tool_converter.py`: `tool_result_to_message()` (aktuell JSON + 20k char truncation)
  - `taskforce/src/taskforce/core/interfaces/state.py`: `StateManagerProtocol` (Persistenz von `message_history`/Session State)

### Enhancement Details

**Was geändert wird (MVP / Brownfield-scope):**

1. **Tool Result Store (Handle statt Payload):**
   - Tool-Outputs werden in einen Store ausgelagert (`ToolResultHandle` + Metadaten + Preview).
   - In `messages` wird nur noch **Handle + Preview** gespeichert (kein Raw Output).

2. **Context Builder + Policy (Pattern A, generisch):**
   - Vor jedem LLM-Call wird ein **Context Pack** deterministisch erzeugt (z.B. „letzte N Handles + Previews + selektive Excerpts“).
   - Harte Caps (max items / max chars) verhindern Prompt-Bloat.

3. **Token Budgeter + Safe Compression:**
   - Preflight Budget Check (Heuristik ok) vor LLM Calls.
   - Compression wird **handle-aware** und nutzt **keine** vollständigen JSON-Dumps der History.

**Success Criteria:**

- Tool-Heavy Runs überschreiten das LLM Input Budget nicht mehr.
- Message-Compression erzeugt keine extrem großen Prompts (kein `json.dumps(old_messages, indent=2)` auf volle Message Objekte).
- Debuggability bleibt erhalten (Tool Raw Outputs sind über Handles abrufbar).

## Stories

1. **Story 9.1: ToolResultStore + ToolResultHandle (Stop the bleeding)**
   - Ergänze einen generischen `ToolResultStore` (min. file-/memory-basiert) und ein `ToolResultHandle` Format (id/tool/created_at/bytes/metadata/schema_version).
   - Passe `LeanAgent` an: Nach Tool-Execution wird `tool_result` gespeichert → `handle` erzeugt → `messages` enthalten nur `handle + preview`.
   - Persistiere Handles im Session State (ohne Raw Payload).

2. **Story 9.2: ContextPolicy + ContextBuilder (Pattern A Rehydration)**
   - Definiere eine konfigurierbare `ContextPolicy` (pro Agent/Profil), z.B.:
     - include latest N tool previews
     - selectors für erlaubte excerpt-fetches
     - caps: `max_items`, `max_chars_per_item`, `max_total_chars`
   - Implementiere `ContextBuilder.build(policy, state, mission) -> context_pack` und injiziere es vor LLM Calls (System oder User Nachricht).

3. **Story 9.3: Token Budgeter + Safe Compression (budget-basiert, handle-aware)**
   - Implementiere einen `TokenBudgeter` (Heuristik) + zentrale `sanitize_message()` Trunkierung.
   - Rework `LeanAgent._compress_messages()`:
     - keine full JSON Dumps der History
     - summary basiert auf sanitisierten recent turns + handle-previews
     - Trigger primär budget-basiert (nicht nur message_count)

## Compatibility Requirements

- [ ] Existing APIs remain unchanged (`LeanAgent.execute()` / Streaming Contracts bleiben kompatibel)
- [ ] State persistence bleibt backward compatible (z.B. via `schema_version` und optionalen Feldern für Handles)
- [ ] CLI und Server-Verhalten bleibt unverändert ohne neue Flags/Config
- [ ] Performance impact ist minimal (Store writes sind lightweight; LLM payloads werden kleiner)

## Risk Mitigation

- **Primary Risk:** LLM verliert Kontext, weil Raw Tool Outputs nicht mehr „automatisch“ im Prompt stehen.
- **Mitigation:**
  - verpflichtende Previews + deterministischer ContextBuilder mit caps und selektiver Rehydration
  - Logging/Tracing der Handles (id/tool/bytes) zur Debug-Analyse
  - Feature Flag / Config Toggle zum Rollback (z.B. `use_tool_result_handles: true/false`)
- **Rollback Plan:** Flag deaktivieren → altes Verhalten (Tool results direkt in messages) + Store bleibt ungenutzt.

## Definition of Done

- [ ] Alle 3 Stories completed mit Akzeptanzkriterien erfüllt
- [ ] Keine Token-Overflow Fehler in Tool-Heavy Runs (Smoke-Test + repräsentative Traces)
- [ ] Bestehende Funktionalität verifiziert (Unit + Integration Tests)
- [ ] Dokumentation aktualisiert (Konfig-Optionen für Policy/Budget/Store)
- [ ] Kein Regression in bestehenden Agents/Profiles

## Story Manager Handoff

**Story Manager Handoff:**

"Please develop detailed user stories for this brownfield epic. Key considerations:

- This is an enhancement to an existing system running **Python 3.11, LiteLLM/OpenAI tool calling, FastAPI, Typer/Rich**
- Integration points: `core/domain/lean_agent.py` (tool loop + compression), `infrastructure/tools/tool_converter.py` (tool result messages), `StateManagerProtocol` persistence
- Existing patterns to follow: Clean Architecture, Protocol interfaces, config-driven behavior
- Critical compatibility requirements: No breaking changes to CLI/API; state persistence must remain compatible (schema versioning / optional fields)
- Each story must include verification that existing functionality remains intact and that prompt sizes stay within budget

The epic should maintain system integrity while delivering **stable, budgeted Context Pack / Rehydration (Pattern A)** for the LeanAgent."


