# ADR-016: Persistent Agent Architecture (Sessionless Orchestrator)

**Status:** Proposed
**Date:** 2026-03-18
**Deciders:** Team
**Context:** Taskforce personal assistant / butler agent use-case

---

## Context and Problem Statement

Taskforce verwendet ein **session-basiertes Modell**: Jeder CLI-Aufruf oder API-Request erzeugt eine neue Session (`session_id` = UUID). Conversation-History und Agent-State sind per `session_id` isoliert. Dieses Modell stammt aus einer Zeit, in der Taskforce primär als Ausführungsframework für einzelne Missions gedacht war.

Für den **Personal Assistant Use-Case** (Butler Agent, ADR-010) ist dieses Modell problematisch:

1. **Unnatürliche Interaktion:** Der Benutzer kommuniziert mit "Session 47a3f..." statt mit seinem Assistenten
2. **Kein geteilter Kontext:** Jede Session startet bei Null — der Agent "vergisst" alles aus vorherigen Sessions (außer explizit im Memory gespeichert)
3. **Überflüssige Komplexität:** Session-CRUD, Session-Listing, Session-Resuming — alles unnötig wenn es nur einen Agent gibt
4. **Gateway-Overhead:** Die Communication Gateway muss `conversation_id` → `session_id` Mappings pflegen
5. **Kein persistenter Lebenszyklus:** Agent startet, führt aus, beendet sich. Kein Daemon-Modus ohne Session-Hacks

### Ist-Zustand: Session-Kopplung im Code

| Komponente | Session-Kopplung | Aufwand bei Entfernung |
|---|---|---|
| `StateManagerProtocol` | `session_id` ist primärer Key für `save_state`/`load_state` | Hoch (Interface-Änderung) |
| `AgentExecutor` | Erzeugt/resolved `session_id` per Aufruf | Mittel |
| `SimpleChatRunner` | Speichert `conversation_history` per `session_id` | Mittel |
| CLI/API Entry Points | Auto-generieren UUID pro Aufruf | Niedrig |
| Sub-Agent Spawner | Erzeugt Child-Sessions | Mittel |
| Communication Gateway | Mapped `conversation_id` → `session_id` | Mittel |
| Runtime Tracking | Heartbeats/Checkpoints per Session | Niedrig |

### Bereits Session-unabhängig (keine Änderung nötig)

| Komponente | Status |
|---|---|
| **Memory** (`FileMemoryStore`) | Global — eine `memory.md` Datei, kein `session_id` |
| **Skills** | Global — nicht an Sessions gebunden |
| **Tool Registry** | Global — Singleton |
| **Profile/Config** | Global — pro Agent, nicht pro Session |
| **LLM Router** | Global — Routing-Regeln sind agent-weit |

---

## Decision

Wir ersetzen das session-basierte Modell durch eine **Persistent Agent Architecture**: Ein Singleton-Agent fungiert als event-driven Orchestrator, der über verschiedene Kanäle erreichbar ist und Sub-Agents für spezialisierte Tasks delegiert.

### Architektur-Überblick

```
┌─────────────────────────────────────────────────────────┐
│  Persistent Agent (Singleton Orchestrator)               │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ Identity  │  │ Memory   │  │ Request Queue      │    │
│  │ + Config  │  │ (global) │  │ (asyncio.Queue)    │    │
│  └──────────┘  └──────────┘  └─────────┬──────────┘    │
│                                         │                │
│  ┌──────────────────────────────────────▼─────────────┐ │
│  │ Conversation Manager                                │ │
│  │ ┌──────────┐ ┌──────────────┐ ┌──────────┐        │ │
│  │ │ Active   │ │ Archived     │ │ Active   │        │ │
│  │ │ Conv #1  │ │ (summary)    │ │ Conv #N  │        │ │
│  │ └──────────┘ └──────────────┘ └──────────┘        │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Event Router (from ADR-010)                         │ │
│  │ Events → Rules → Actions / LLM-Decisions            │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Sub-Agent Pool (ephemeral, task-specific)           │ │
│  │ - Coding Worker, Planner, Reviewer, Judge, etc.    │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         ▲               ▲               ▲
         │               │               │
    ┌────┴────┐    ┌────┴────┐    ┌─────┴─────┐
    │Telegram │    │CLI Chat │    │REST API / │
    │Slack    │    │         │    │Webhooks   │
    └─────────┘    └─────────┘    └───────────┘
```

### Kernkomponente 1: Agent als Singleton

Der Hauptagent ist ein **Singleton-Prozess** (Daemon), der dauerhaft läuft. Es gibt keine Session-Erzeugung mehr — der Agent IS der Kontext.

**Lebenszyklus:**

```
Start (butler start / server start)
    │
    ▼
┌────────────────────────────────────┐
│  1. Load Agent State (singleton)   │
│  2. Load Active Conversations      │
│  3. Start Event Sources (ADR-010)  │
│  4. Start Scheduler (ADR-010)      │
│  5. Start Request Queue Consumer   │
│  6. Start Channel Listeners        │
└────────────────────┬───────────────┘
                     │
                     ▼
              Main Event Loop
              (läuft unbegrenzt)
                     │
                     ▼
            Graceful Shutdown
            (State checkpoint, Queue drain)
```

### Kernkomponente 2: Request Queue

Alle eingehenden Nachrichten (egal welcher Channel) fließen in eine zentrale `asyncio.Queue`. Der Agent verarbeitet sie sequenziell — keine Race Conditions auf dem Agent-State.

```python
# application/request_queue.py
@dataclass
class AgentRequest:
    """A queued request from any channel."""
    request_id: str                     # UUID
    channel: str                        # "telegram", "cli", "rest", "event"
    conversation_id: str | None         # Zuordnung zu Conversation
    message: str                        # User-Nachricht oder Event-Beschreibung
    sender_id: str | None               # Absender (für Antwort-Routing)
    metadata: dict[str, Any]            # Channel-spezifische Daten
    created_at: datetime

class RequestQueue:
    """Central request queue for the persistent agent."""

    def __init__(self, max_size: int = 100) -> None:
        self._queue: asyncio.Queue[AgentRequest] = asyncio.Queue(maxsize=max_size)

    async def enqueue(self, request: AgentRequest) -> None:
        await self._queue.put(request)

    async def process_loop(self, handler: Callable[[AgentRequest], Awaitable[None]]) -> None:
        """Main processing loop — runs until cancelled."""
        while True:
            request = await self._queue.get()
            try:
                await handler(request)
            finally:
                self._queue.task_done()
```

**Sub-Agents arbeiten parallel:** Wenn der Hauptagent einen Task an einen Sub-Agent delegiert, läuft dieser in einem eigenen ephemeren Kontext. Der Hauptagent kann währenddessen den nächsten Request aus der Queue verarbeiten (optional, konfigurierbar).

### Kernkomponente 3: Conversation Manager (Hybrid-Modell)

Conversations ersetzen Sessions als leichtgewichtige Dialogeinheiten.

```python
# core/interfaces/conversation.py
class ConversationManagerProtocol(Protocol):
    """Manages conversation lifecycle for the persistent agent."""

    async def get_or_create(self, channel: str, sender_id: str | None = None) -> str:
        """Get active conversation for channel/sender or create new one."""
        ...

    async def append_message(self, conv_id: str, message: dict) -> None: ...
    async def get_messages(self, conv_id: str, limit: int | None = None) -> list[dict]: ...
    async def archive(self, conv_id: str) -> None: ...
    async def list_active(self) -> list[ConversationInfo]: ...
    async def list_archived(self, limit: int = 20) -> list[ConversationSummary]: ...

@dataclass
class ConversationInfo:
    conversation_id: str
    channel: str
    started_at: datetime
    last_activity: datetime
    message_count: int
    topic: str | None = None            # LLM-generierter Topic-Titel

@dataclass
class ConversationSummary:
    conversation_id: str
    topic: str
    summary: str                        # LLM-generierte Zusammenfassung
    started_at: datetime
    archived_at: datetime
    message_count: int
```

**Segmentierungslogik (Hybrid):**

1. **Agent-Vorschlag:** Nach einer Antwort prüft der Agent (leichter LLM-Call oder Heuristik), ob das Topic gewechselt hat. Falls ja, schlägt er vor: _"Soll ich ein neues Thema beginnen?"_
2. **User-explizit:** `/new` startet immer eine neue Conversation
3. **Auto-Archivierung:** Conversations ohne Aktivität seit N Stunden (konfigurierbar, default: 24h) werden automatisch archiviert mit LLM-generierter Summary
4. **Kein Zwang:** Wenn der User den Vorschlag ignoriert, läuft die Conversation einfach weiter

### Kernkomponente 4: Vereinfachtes AgentStateProtocol

```python
# core/interfaces/state.py (erweitert)
class AgentStateProtocol(Protocol):
    """Persistent state for the singleton agent."""

    async def save(self, state_data: dict[str, Any]) -> None:
        """Save agent-global state."""
        ...

    async def load(self) -> dict[str, Any] | None:
        """Load agent-global state."""
        ...
```

**Was im Agent-State gespeichert wird:**

- Agent-Konfiguration und Laufzeit-Parameter
- Aktive Conversation-IDs
- Scheduler-State-Referenz
- Letzte Aktivitätszeitstempel

**Was NICHT mehr im Agent-State ist:**

- Conversation-History (→ ConversationManager)
- Memory (→ FileMemoryStore, bereits global)
- Tool-State (→ Tool-eigene Persistence)

### Kernkomponente 5: Event-Driven Integration (Aufbauend auf ADR-010)

Der Persistent Agent ist das natürliche Zuhause für die Butler-Architektur aus ADR-010:

| ADR-010 Komponente | Integration in Persistent Agent |
|---|---|
| Event Sources | Starten beim Agent-Start, publizieren auf Request Queue |
| Scheduler | Teil des Agent-Lebenszyklus |
| Rule Engine | Evaluiert Events, erzeugt AgentRequests für die Queue |
| Event Router | Dispatched Actions (Notify, Execute, Log) |
| Learning Service | Läuft nach jeder verarbeiteten Conversation-Message |

**Events als Requests:** Externe Events (Kalender, Webhooks, Schedules) werden zu `AgentRequest`-Objekten konvertiert und in die Queue eingereiht — gleicher Verarbeitungspfad wie User-Nachrichten.

```
Calendar Event → AgentEvent → Rule Engine
    │                             │
    ├─ Regel-Match: notify ──────► Gateway.send_notification()
    │
    └─ Kein Match / LLM-Route ──► AgentRequest in Queue
                                       │
                                       ▼
                                  Agent verarbeitet
                                  (wie User-Message)
```

### Kernkomponente 6: Multi-Channel Communication

Die Communication Gateway (ADR-009) wird vereinfacht:

**Vorher (session-basiert):**
```
Telegram Message → InboundAdapter → resolve session_id → load session state
    → execute with session → save session state → OutboundSender
```

**Nachher (persistent agent):**
```
Telegram Message → InboundAdapter → AgentRequest(channel="telegram")
    → Request Queue → Agent verarbeitet → OutboundSender (reply to channel)
```

**Kein Session-Mapping mehr.** Die Gateway kennt Conversations (über Channel + Sender), nicht Sessions. Der Agent entscheidet basierend auf dem Conversation-Kontext.

**Alle Channels bleiben funktional:**

| Channel | Eingang | Ausgang |
|---|---|---|
| **Telegram** | Webhook → InboundAdapter → Queue | Agent → OutboundSender → Telegram API |
| **CLI Chat** | STDIN → Queue | Agent → STDOUT (Rich formatted) |
| **REST API** | `POST /execute` → Queue | SSE Stream / Response |
| **Webhooks** | External Event → EventSource → Queue | Agent → Notifications |
| **Slack/Teams** | Webhook → InboundAdapter → Queue | Agent → OutboundSender |

**Proaktive Notifications:** Der Agent kann jederzeit über `send_notification` Tool oder direkt über die Gateway Nachrichten versenden — unabhängig davon ob ein Request in der Queue liegt.

---

## Betroffene Dateien und Änderungen

### Core Layer (Neue/Geänderte Interfaces und Models)

| Datei | Änderung |
|---|---|
| `core/interfaces/state.py` | Neues `AgentStateProtocol` hinzufügen |
| `core/interfaces/conversation.py` | **Neu:** `ConversationManagerProtocol`, `ConversationInfo`, `ConversationSummary` |
| `core/domain/models.py` | `ExecutionResult`: `session_id` → `conversation_id` (optional) |
| `core/domain/request.py` | **Neu:** `AgentRequest` Dataclass |

### Infrastructure Layer (Adapter-Implementierungen)

| Datei | Änderung |
|---|---|
| `infrastructure/persistence/file_state_manager.py` | Zusätzlich `AgentStateProtocol` implementieren (singleton file) |
| `infrastructure/persistence/file_conversation_store.py` | **Neu:** File-basierter ConversationManager |

### Application Layer (Orchestrierung)

| Datei | Änderung |
|---|---|
| `application/executor.py` | `session_id` durch `conversation_id` ersetzen, Queue-Integration |
| `application/factory.py` | Singleton-Agent-Erzeugung, kein pro-Session-Wiring |
| `application/request_queue.py` | **Neu:** `RequestQueue`, `AgentRequest` Processing |
| `application/gateway.py` | Session-Mapping entfernen, Messages → Queue routen |
| `application/conversation_manager.py` | **Neu:** Conversation-Lifecycle (Hybrid-Segmentierung) |

### API Layer (Entry Points)

| Datei | Änderung |
|---|---|
| `api/cli/simple_chat.py` | Kein Session-UUID, fortlaufende Conversation |
| `api/cli/commands/sessions.py` | Ersetzen durch `conversations.py` |
| `api/routes/execution.py` | `session_id` Parameter → optional `conversation_id` |
| `api/routes/sessions.py` | Ersetzen durch Conversation-Endpoints |
| `api/butler_daemon.py` | Integriert Request Queue und Singleton-Agent |

---

## Migration Strategy

### Phase 1: Additive Änderungen (kein Breaking Change)

1. Neue Protocols hinzufügen (`AgentStateProtocol`, `ConversationManagerProtocol`)
2. `RequestQueue` implementieren
3. `ConversationManager` implementieren
4. Bestehende Session-APIs bleiben funktional

### Phase 2: Dual-Mode (Übergang)

1. `AgentExecutor` unterstützt sowohl `session_id` als auch `conversation_id`
2. Butler Daemon nutzt neues Modell
3. CLI/API können wahlweise Session-Modus oder Persistent-Modus nutzen
4. `StateManagerProtocol` bleibt für Sub-Agents erhalten

### Phase 3: Session-Deprecation

1. Session-Endpoints als Deprecated markieren
2. CLI Default wechselt auf Persistent-Modus
3. Session-Code bleibt für Sub-Agent-interne Nutzung

---

## Backward Compatibility

| Bereich | Kompatibilität |
|---|---|
| **Sub-Agents** | Behalten interne ephemere Sessions — keine Änderung |
| **Epic Orchestration** | Planner/Worker/Judge haben eigene States — keine Änderung |
| **Memory** | Bereits global, keine Änderung nötig |
| **Skills** | Bereits global, keine Änderung nötig |
| **REST API** | `session_id` wird Optional, `conversation_id` als Alternative |
| **Bestehende State-Files** | Können als initiale Conversation importiert werden |

---

## Consequences

### Vorteile

- **Natürlichere Interaktion:** "Mein Assistent" statt "Session 47a3f..."
- **Geteilter Kontext:** Agent kennt alle vorherigen Conversations via Memory + Summaries
- **Weniger Code:** Session-CRUD, Session-Listing, Session-Resuming entfällt
- **Event-Driven nativ:** Request Queue ist das natürliche Interface für Events UND User-Messages
- **Multi-Channel vereinfacht:** Kein Session-Mapping in der Gateway nötig
- **Besseres Context-Management:** Conversation-Archivierung + Memory-Recall statt Session-Isolation

### Herausforderungen

- **Context-Window-Management:** Unbegrenzt wachsende Conversations brauchen aktive Komprimierung/Archivierung
- **Fehler-Isolation:** Ein kaputter Agent-State betrifft alles — robustere Persistence nötig
- **Gleichzeitigkeit:** Request Queue ist single-threaded für den Hauptagent — langläufige Tasks sollten an Sub-Agents delegiert werden
- **Migration:** Bestehende Session-basierte Tests müssen angepasst werden

### Risiken und Mitigationen

| Risiko | Mitigation |
|---|---|
| Context-Overflow bei langen Conversations | Auto-Archivierung + Summary + Memory-Recall |
| State-Corruption | Checkpoint-System (bereits vorhanden via ADR-010), regelmäßige Backups |
| Queue-Stau bei langem Task | Sub-Agent-Delegation, konfigurierbares Timeout, Priority-Queue (future) |
| Breaking Changes für API-Consumer | Dual-Mode Übergangsphase, `session_id` bleibt Optional |

---

## Alternatives Considered

1. **Session-Pooling:** Ein fester Pool von Sessions, die wiederverwendet werden. Abgelehnt — löst das Kernproblem nicht (unnatürliche Abstraktion).

2. **Sticky Sessions per Channel:** Jeder Channel bekommt eine feste Session. Abgelehnt — konzeptionell ähnlich zum Persistent-Agent-Modell, aber mit unnötiger Session-Indirektion.

3. **Nur Memory-basierter Kontext (keine Conversations):** Ein endloser Message-Strom, nur Memory für Kontext. Abgelehnt — zu schwer für Context-Window-Management, keine Topic-Isolation möglich.

4. **Conversation = Session (Rename only):** Sessions umbenennen zu Conversations, aber Architektur beibehalten. Abgelehnt — löst nicht das Singleton-Problem und die Gateway-Komplexität.

---

## Relationship to Other ADRs

| ADR | Beziehung |
|---|---|
| **ADR-009** (Communication Gateway) | Gateway wird vereinfacht — kein Session-Mapping, Messages → Queue |
| **ADR-010** (Event-Driven Butler) | Persistent Agent ist das natürliche Zuhause für Butler-Architektur. Events werden zu AgentRequests |
| **ADR-013** (Memory Consolidation) | Memory bleibt unverändert. Conversation-Summaries ergänzen das Memory-System |
| **ADR-015** (Parallel Sub-Agents) | Sub-Agents behalten ephemere Sessions. Hauptagent delegiert via Sub-Agent-Pool |

---

## Summary

Die Persistent Agent Architecture transformiert Taskforce vom session-basierten Ausführungsframework zum **Singleton-Orchestrator mit Event-Driven-Architektur**. Der Agent ist dauerhaft aktiv, verarbeitet Requests aus einer zentralen Queue, segmentiert Dialoge in leichtgewichtige Conversations und delegiert spezialisierte Arbeit an Sub-Agents. Multi-Channel-Kommunikation (Telegram, CLI, REST, Webhooks) bleibt vollständig erhalten und wird durch das Entfernen des Session-Mappings sogar vereinfacht.
