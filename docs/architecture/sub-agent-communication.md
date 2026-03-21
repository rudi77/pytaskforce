# Sub-Agent Communication — Technische Architektur

Dieses Dokument beschreibt die technischen Details der Agent-zu-Sub-Agent-Kommunikation in Taskforce.

## Architektur-Überblick

```
┌─────────────────────────────────────────────────────────┐
│  LeanAgent (Parent)                                     │
│  └─ _execute_tool()                                     │
│      ├─ Prüft: requires_parent_session == True?         │
│      ├─ Injiziert _parent_session_id in tool_args       │
│      └─ Ruft tool.execute() auf                         │
├─────────────────────────────────────────────────────────┤
│  AgentTool / SubAgentTool / ParallelAgentTool           │
│  └─ Erstellt SubAgentSpec                               │
│  └─ Ruft SubAgentSpawner.spawn() auf                    │
├─────────────────────────────────────────────────────────┤
│  SubAgentSpawner                                        │
│  └─ Erstellt Agent via AgentFactory                     │
│  └─ agent.execute(mission, session_id)                  │
│  └─ Schließt Ressourcen                                 │
│  └─ Gibt SubAgentResult zurück                          │
└─────────────────────────────────────────────────────────┘
```

## Parent-Session-Injection

Der Mechanismus, über den Orchestrierungs-Tools die Parent-Session-ID erhalten, ist in `LeanAgent._execute_tool()` implementiert:

```python
# src/taskforce/core/domain/lean_agent.py (~Zeile 517-520)
tool = self.tool_executor.get_tool(tool_name)
if tool and getattr(tool, "requires_parent_session", False) and session_id:
    tool_args = {**tool_args, "_parent_session_id": session_id}
```

Tools mit dem Marker `requires_parent_session = True` erhalten automatisch die `_parent_session_id` des aufrufenden Agenten. Dieses Pattern wird von allen drei Orchestrierungs-Tools genutzt (`AgentTool`, `SubAgentTool`, `ParallelAgentTool`).

## Session-Hierarchie

Session-IDs werden hierarchisch aufgebaut:

```
parent-session-123
├── parent-session-123--sub_coding_worker_a1b2c3d4
├── parent-session-123--sub_coding_reviewer_e5f6g7h8
└── parent-session-123--sub_generic_b9c0d1e2
    └── parent-session-123--sub_generic_b9c0d1e2--sub_rag_f3a4b5c6
```

**Generierung:** `build_sub_agent_session_id()` aus `core/domain/sub_agents.py`:

```python
f"{parent_session_id}--sub_{label}_{uuid4().hex[:8]}"
```

Unbegrenzte Verschachtelung ist möglich — ein Sub-Agent kann selbst Sub-Agents spawnen.

## State-Isolation

Jeder Agent hat seinen eigenen, vollständig isolierten State:

```
.taskforce/states/
├── parent-session-123.json
├── parent-session-123--sub_coding_worker_a1b2c3d4.json
└── parent-session-123--sub_coding_reviewer_e5f6g7h8.json
```

- **Kein geteilter State** zwischen Parent und Sub-Agent
- **Keine implizite Kontext-Vererbung** — Sub-Agent kennt den Parent-Kontext nicht
- **Kontext** muss explizit über den Mission-String übergeben werden
- **Dateisystem** ist geteilt — Sub-Agents können Dateien lesen/schreiben, die andere Agenten erstellt haben

## Datenfluss im Detail

### 1. Tool-Aufruf

Der Parent-Agent entscheidet im ReAct-Loop, eine Aufgabe zu delegieren. Das LLM generiert einen Tool-Call:

```json
{
  "tool": "coding_worker",
  "arguments": { "mission": "Implementiere die Funktion calculate_total() in utils.py" }
}
```

### 2. Session-ID-Injection und Spec-Erstellung

`LeanAgent._execute_tool()` injiziert `_parent_session_id`. Das Tool erstellt einen `SubAgentSpec`:

```python
@dataclass(frozen=True)
class SubAgentSpec:
    mission: str
    parent_session_id: str
    specialist: str | None = None
    planning_strategy: str | None = None
    profile: str | None = None
    work_dir: str | None = None
    max_steps: int | None = None
    agent_definition: dict[str, Any] | None = None
```

### 3. Agent-Erstellung und Ausführung

`SubAgentSpawner.spawn()` erzeugt einen neuen Agent über die `AgentFactory` und führt die Mission aus:

1. Session-ID generieren (hierarchisch)
2. Agent-Config auflösen (Custom-YAML → Plugin → Fallback)
3. Agent via Factory erstellen
4. `agent.execute(mission, session_id)` aufrufen
5. Ressourcen schließen (MCP-Connections etc.)

### 4. Ergebnis-Rückgabe

```python
@dataclass(frozen=True)
class SubAgentResult:
    session_id: str
    status: str           # completed, failed, paused
    success: bool         # True wenn status in {completed, paused}
    final_message: str    # Letzte Antwort des Sub-Agents
    error: str | None     # Fehlermeldung bei Failure
```

Das Orchestrierungs-Tool wandelt dies in ein Dict um, das als Tool-Result in die Message-History des Parent eingefügt wird. Der Parent kann darauf in seinem nächsten Reasoning-Schritt zugreifen.

### 5. Optionale Ergebnis-Zusammenfassung

`AgentTool` kann lange Ergebnisse zusammenfassen (`summarize_results: true`). Dabei wird das Ergebnis auf `summary_max_length` Zeichen gekürzt. Dies reduziert den Token-Verbrauch im Parent-Kontext.

## Parallele Ausführung

`ParallelAgentTool` nutzt `asyncio.Semaphore` zur Concurrency-Kontrolle:

```python
semaphore = asyncio.Semaphore(max_concurrency)  # Default: 3

async def _run_with_semaphore(spec):
    async with semaphore:
        return await spawner.spawn(spec)

results = await asyncio.gather(*[_run_with_semaphore(s) for s in specs])
```

- Teilfehler brechen andere Sub-Agents nicht ab
- Ergebnisse werden aggregiert mit `succeeded`/`failed` Counts
- Jeder Sub-Agent hat eine eigene Session-ID

## Tool-Wiring (ToolBuilder)

Die Verdrahtung der Orchestrierungs-Tools geschieht in `application/tool_builder.py`:

```python
# Sub-Agent-Tool
if tool_spec.get("type") in {"sub_agent", "agent"}:
    spawner = SubAgentSpawner(factory, profile=..., max_steps=...)
    agent_tool = AgentTool(factory, spawner, profile=..., summarize_results=...)
    return SubAgentTool(agent_tool, specialist=..., name=...)

# Parallel-Agent-Tool
if tool_spec.get("type") == "parallel_agent":
    spawner = SubAgentSpawner(factory, profile=..., max_steps=...)
    return ParallelAgentTool(spawner, max_concurrency=...)
```

## Beteiligte Dateien

| Datei | Schicht | Zweck |
|-------|---------|-------|
| `core/domain/sub_agents.py` | Core | `SubAgentSpec`, `SubAgentResult`, `build_sub_agent_session_id()` |
| `core/domain/lean_agent.py` | Core | Parent-Session-ID-Injection (~Zeile 517) |
| `core/interfaces/sub_agents.py` | Core | `SubAgentSpawnerProtocol` |
| `infrastructure/tools/orchestration/agent_tool.py` | Infra | `AgentTool` (`call_agent`) |
| `infrastructure/tools/orchestration/sub_agent_tool.py` | Infra | `SubAgentTool` (fixierter Specialist) |
| `infrastructure/tools/orchestration/parallel_agent_tool.py` | Infra | `ParallelAgentTool` (`call_agents_parallel`) |
| `application/sub_agent_spawner.py` | App | `SubAgentSpawner` (Agent-Lifecycle) |
| `application/tool_builder.py` | App | Tool-Instanziierung und Wiring |

## Bekannte Einschränkungen

- **Kein Streaming:** Sub-Agent-Events werden nicht an den Parent propagiert. Der Parent wartet auf das vollständige Ergebnis.
- **Kein Timeout:** Es gibt keinen konfigurierbaren Timeout für Sub-Agent-Ausführungen.
- **Kein geteilter Kontext:** Kontext muss manuell im Mission-String übergeben werden. Es gibt kein automatisches Context-Forwarding.
- **Geteiltes Dateisystem:** Parallele Sub-Agents können sich gegenseitig Dateien überschreiben — es gibt keinen Locking-Mechanismus.

## Verwandte Dokumentation

- [Sub-Agent Orchestration (Feature-Guide)](../features/sub-agent-orchestration.md)
- [Epic Orchestration](epic-orchestration.md)
- [ADR-004: Multi-Agent Runtime](../adr/adr-004-multi-agent-runtime.md)
- [ADR-015: Parallel Sub-Agent Execution](../adr/adr-015-parallel-sub-agent-execution.md)
