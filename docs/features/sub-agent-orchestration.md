# Sub-Agent Orchestration

Sub-Agents ermöglichen es einem Parent-Agent, Aufgaben an spezialisierte Agenten zu delegieren. Die Kommunikation basiert auf dem **Tool-based Delegation**-Pattern: Sub-Agents werden als Tool-Aufrufe behandelt, Ergebnisse fließen als Tool-Results zurück.

## Konzept

```
Parent Agent (session-123)
  ├─ ReAct-Loop: Denkt → entscheidet, Aufgabe zu delegieren
  ├─ Ruft Sub-Agent-Tool auf (z.B. coding_worker)
  │   └─ SubAgentSpawner erstellt neuen Agent
  │       ├─ Eigene Session: session-123--sub_coding_worker_a1b2c3d4
  │       ├─ Eigener isolierter State
  │       └─ Führt eigenen ReAct-Loop aus
  ├─ Erhält Ergebnis als Tool-Result
  └─ Fährt mit eigenem ReAct-Loop fort
```

**Wichtig:** Sub-Agents sind vollständig isoliert. Es gibt keinen geteilten State, keine implizite Kontext-Vererbung und kein Streaming vom Sub-Agent zum Parent. Kontext muss explizit im Mission-String übergeben werden.

## Drei Orchestrierungs-Tools

### 1. `call_agent` (AgentTool)

Generische Delegation an einen wählbaren Spezialisten.

**Parameter:**

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `mission` | string | ja | Aufgabenbeschreibung für den Sub-Agent |
| `specialist` | string | nein | Profil-Name oder Custom-Agent-ID |
| `planning_strategy` | string | nein | `native_react`, `plan_and_execute`, `plan_and_react`, `spar` |

### 2. SubAgentTool (Fixierter Spezialist)

Wrapper um `call_agent` mit voreingestelltem Spezialisten. Der Agent muss nur noch die `mission` angeben — Specialist und Planning-Strategy sind fixiert.

### 3. `call_agents_parallel` (ParallelAgentTool)

Führt mehrere Sub-Agent-Missions parallel aus.

**Parameter:**

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `missions` | array | ja | Liste von `{mission, specialist?, planning_strategy?}` |
| `max_concurrency` | integer | nein | Max. parallele Agenten (default: 3) |

**Rückgabe:**

```json
{
  "success": true,
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "results": [
    { "mission": "...", "specialist": "coding", "success": true, "result": "...", "session_id": "..." }
  ]
}
```

## Konfiguration (Profil-YAML)

Sub-Agents werden in der `tools:`-Sektion des Profils konfiguriert:

```yaml
# src/taskforce/configs/coding_agent.yaml
tools:
  - shell
  - edit
  - memory

  # Fixierter Sub-Agent (nur mission als Parameter)
  - type: sub_agent
    name: coding_worker           # Tool-Name (muss eindeutig sein)
    specialist: coding_worker     # Profil-Name (Lookup: configs/custom/{name}.yaml)
    auto_approve: true            # Approval überspringen (default: false)
    summarize_results: true       # Ergebnis zusammenfassen (default: true)
    summary_max_length: 3200      # Max. Zeichen der Zusammenfassung

  - type: sub_agent
    name: coding_reviewer
    summarize_results: true
    summary_max_length: 2600

  # Parallele Ausführung
  - type: parallel_agent
    max_concurrency: 3
    profile: dev                  # Basis-Profil für parallele Agenten
```

### Weitere Konfigurationsoptionen für `sub_agent`

| Option | Default | Beschreibung |
|--------|---------|--------------|
| `profile` | `dev` | Basis-YAML-Profil |
| `work_dir` | `.taskforce` | Arbeitsverzeichnis |
| `max_steps` | aus Profil | Max. ReAct-Schritte |
| `planning_strategy` | aus Profil | Strategie-Override |
| `tool_overrides` | `[]` | Geteilte Tool-Instanzen |

### Custom-Agent-Konfigurationen

Sub-Agent-Profile liegen in `src/taskforce/configs/custom/`:

```yaml
# src/taskforce/configs/custom/coding_worker.yaml
profile: coding_worker
agent:
  planning_strategy: native_react
  max_steps: 120
tools:
  - shell
  - edit
  - memory
```

**Lookup-Reihenfolge** beim Auflösen eines Specialist-Namens:

1. `configs/custom/{specialist}.yaml`
2. `configs/custom/{specialist}/{specialist}.yaml`
3. Plugin-Verzeichnisse: `configs/agents/{specialist}.yaml`
4. Fallback auf Inline-Parameter

## Ergebnis-Format

Jeder Sub-Agent-Aufruf gibt ein einheitliches Dict zurück:

```python
{
    "success": bool,        # True wenn Status completed/paused
    "result": str,          # Finale Antwort (ggf. zusammengefasst)
    "session_id": str,      # z.B. "parent-123--sub_coding_worker_a1b2c3d4"
    "status": str,          # completed, failed, paused
    "error": str | None     # Fehlermeldung bei Failure
}
```

Dieses Ergebnis wird als Tool-Result in die Message-History des Parent eingefügt und steht dort für weitere Reasoning-Schritte zur Verfügung.

## Approval-Verhalten

| Tool | Default | Risiko-Level |
|------|---------|-------------|
| `call_agent` | Approval erforderlich | MEDIUM |
| SubAgentTool | Approval erforderlich | MEDIUM |
| `call_agents_parallel` | Kein Approval | MEDIUM |

Mit `auto_approve: true` in der YAML-Config wird die Approval-Abfrage für ein Sub-Agent-Tool deaktiviert. Sub-Agents erzwingen ihre eigenen Approval-Gates unabhängig vom Parent.

## Fehlerbehandlung

- **Sub-Agent-Fehler** werden gefangen und als `SubAgentResult(success=False, error="...")` zurückgegeben — der Parent stürzt nicht ab.
- **Parallele Ausführung:** Teilfehler brechen die anderen Sub-Agents nicht ab. Das Gesamtergebnis enthält `succeeded` und `failed` Counts.
- **Ressourcen-Cleanup:** Sub-Agent-Ressourcen (MCP-Connections etc.) werden nach Abschluss automatisch geschlossen.
- **Kein Timeout:** Es gibt derzeit keinen konfigurierbaren Timeout für Sub-Agent-Ausführungen.

## Wann welches Pattern?

| Szenario | Empfohlenes Pattern |
|----------|-------------------|
| Einzelne spezialisierte Aufgabe | `sub_agent` mit fixiertem Specialist |
| Dynamische Specialist-Wahl | `call_agent` mit `specialist`-Parameter |
| Mehrere unabhängige Aufgaben | `call_agents_parallel` |
| Komplexe Multi-Step-Pipelines (Planner/Worker/Judge) | [Epic Orchestration](../architecture/epic-orchestration.md) |

## Verwandte Dokumentation

- [Sub-Agent-Kommunikation (Architektur)](../architecture/sub-agent-communication.md) — Technischer Deep-Dive
- [Epic Orchestration](../architecture/epic-orchestration.md) — Planner/Worker/Judge Workflow
- [ADR-004: Multi-Agent Runtime](../adr/adr-004-multi-agent-runtime.md)
- [ADR-015: Parallel Sub-Agent Execution](../adr/adr-015-parallel-sub-agent-execution.md)
