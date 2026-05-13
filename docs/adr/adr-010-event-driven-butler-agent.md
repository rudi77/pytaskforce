# ADR 010: Event-Driven Butler Agent Architecture

## Status
Partially superseded by [ADR-027](adr-027-generic-agent-daemon.md), which
generalises ``ButlerDaemon`` / ``ButlerService`` / ``ButlerRoleLoader`` into
framework primitives (``AgentDaemon`` / ``AgentService`` / ``AgentRoleLoader``).
The event-driven primitives (``EventSource``, ``Scheduler``, ``RuleEngine``,
``EventRouter``) described here remain the canonical reference.

## Context

Taskforce ist derzeit ein **reaktives** System: Agenten werden durch explizite Benutzeranfragen (CLI-Kommando oder REST-API-Call) gestartet, führen eine Mission aus und beenden sich. Es gibt keinen Mechanismus für **proaktives Verhalten** -- der Agent kann nicht selbständig auf externe Ereignisse reagieren, den Benutzer zu bestimmten Zeitpunkten benachrichtigen oder im Hintergrund lernen.

### Gewünschtes Zielbild: "Butler Agent"

Ein persönlicher KI-Assistent, der:
1. **24/7 läuft** und auf Ereignisse horcht (Kalender, E-Mails, Webhooks, Zeitpläne)
2. **Proaktiv benachrichtigt** -- z.B. via Telegram an Kalendertermine erinnert
3. **Tasks autonom erledigt** -- z.B. tägliche Zusammenfassungen generieren, Berichte erstellen
4. **Kontinuierlich dazulernt** -- Wissen im Langzeitgedächtnis ablegt, Präferenzen erkennt und adaptiert
5. **Event-basiert** arbeitet -- auf Ereignisse reagiert und selbst Events/Notifications auslöst

### Analyse des Ist-Zustands

#### Was bereits vorhanden ist (Stärken)

| Komponente | Status | Details |
|-----------|--------|---------|
| **Telegram-Integration** | ✅ Vollständig | CommunicationGateway mit Inbound-Webhooks, Outbound-Push, Recipient-Registry, Conversation-Store |
| **Push-Notifications** | ✅ Vorhanden | `send_notification` Tool + `/api/v1/gateway/notify` Endpoint |
| **Broadcast** | ✅ Vorhanden | `/api/v1/gateway/broadcast` für alle registrierten Empfänger |
| **Message Bus** | ✅ Basis | `InMemoryMessageBus` mit Pub/Sub, Topics, Ack/Nack |
| **Long-Term Memory** | ✅ Basis (MVP) | File-basiert, Markdown, Scope-basiert (session/profile/user/org), CRUD via Memory-Tool |
| **Runtime Tracking** | ✅ Vorhanden | Heartbeat + Checkpoint-System für Session-Monitoring und Recovery |
| **Session Recovery** | ✅ Vorhanden | State-Persistence, Checkpoint-Restore, ask_user-Pause/Resume |
| **Streaming Events** | ✅ Intern | `StreamEvent` mit 11+ Event-Typen, aber nur für Execution-Progress (nicht für externe Events) |
| **Kalender-Tool** | ⚠️ Nur Beispiel | `examples/personal_assistant/` hat GoogleCalendarTool (list/create), aber nicht im Core |
| **Protocol-basiertes Design** | ✅ Fundament | Alle Schnittstellen sind Protocols -- einfach erweiterbar |

#### Was fehlt (Lücken)

| Lücke | Auswirkung |
|-------|-----------|
| **Kein Scheduler/Daemon** | Agent kann nicht zeitgesteuert aktiv werden (kein Cron, kein APScheduler, kein Background-Task-Loop) |
| **Keine externen Event-Sources** | Kein Mechanismus um auf Kalender-Änderungen, E-Mail-Eingang, Webhook-Events zu horchen |
| **Kein Event-Router** | Keine Zuordnung: "Kalender-Event → Agent-Aktion" |
| **Kein persistenter Agent-Lifecycle** | Agent startet, führt aus, beendet sich. Kein Daemon-Modus |
| **Naive Memory-Suche** | Nur Substring-Matching, kein semantisches Recall, keine automatische Kontextanreicherung |
| **Kein automatisches Lernen** | Agent speichert nur explizit über Memory-Tool; kein automatisches Extrahieren von Präferenzen/Wissen |
| **Kein Regelwerk/Trigger-System** | Keine "Wenn X dann Y"-Regeln die der Benutzer definieren kann |
| **Kalender/E-Mail nicht im Core** | Nur als Beispiel-Tool vorhanden, nicht als registriertes Native-Tool |

---

## Decision

Wir führen eine **Event-Driven Butler Architecture** ein, die auf dem bestehenden Clean-Architecture-Fundament aufbaut. Die Architektur besteht aus fünf neuen Kernkomponenten:

### Architektur-Überblick

```
                                    ┌─────────────────────────────┐
                                    │    Telegram / Slack / ...   │
                                    │    (Outbound Notifications) │
                                    └──────────────▲──────────────┘
                                                   │
┌──────────────────────────────────────────────────────────────────────────────┐
│                           BUTLER DAEMON (api layer)                         │
│                                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌───────────────────┐  │
│  │ FastAPI      │  │ Scheduler    │  │ Event      │  │ Webhook           │  │
│  │ Server       │  │ (APScheduler)│  │ Bus        │  │ Receiver          │  │
│  │ (REST API)   │  │              │  │            │  │ (ext. events)     │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘  └──────┬────────────┘  │
│         │                 │                │                 │               │
│         └─────────────────┴────────────────┴─────────────────┘               │
│                                    │                                         │
└────────────────────────────────────┼─────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER (Orchestration)                        │
│                                                                              │
│  ┌──────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐  │
│  │ AgentExecutor     │  │ EventRouter     │  │ ButlerService             │  │
│  │ (existing)        │  │ (NEW)           │  │ (NEW)                     │  │
│  │                   │  │                 │  │                           │  │
│  │ execute_mission() │  │ event → rules   │  │ lifecycle, preferences,   │  │
│  │                   │  │ → agent action  │  │ learning orchestration    │  │
│  └──────────────────┘  └─────────────────┘  └───────────────────────────┘  │
│                                                                              │
│  ┌──────────────────┐  ┌─────────────────┐                                  │
│  │ CommunicationGW  │  │ RuleEngine      │                                  │
│  │ (existing)        │  │ (NEW)           │                                  │
│  │                   │  │                 │                                  │
│  │ notify/broadcast  │  │ trigger rules,  │                                  │
│  │                   │  │ conditions,     │                                  │
│  └──────────────────┘  │ action templates │                                  │
│                         └─────────────────┘                                  │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE LAYER (Adapters)                        │
│                                                                              │
│  ┌────────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ EventSources   │ │ Scheduler    │ │ Enhanced     │ │ Tools            │ │
│  │ (NEW)          │ │ Store (NEW)  │ │ Memory (NEW) │ │ (erweitert)      │ │
│  │                │ │              │ │              │ │                  │ │
│  │ - Calendar     │ │ - Jobs       │ │ - Semantic   │ │ - calendar       │ │
│  │ - Email/IMAP   │ │ - Schedules  │ │   Search     │ │ - email          │ │
│  │ - RSS/Feeds    │ │ - Cron-Exprs │ │ - Auto-Learn │ │ - schedule       │ │
│  │ - Webhooks     │ │              │ │ - Decay/     │ │ - reminder       │ │
│  │ - File Watch   │ │              │ │   Compaction │ │ - rule_manager   │ │
│  └────────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘ │
│                                                                              │
│  ┌───────────────────────────────────┐                                      │
│  │ Existing Infrastructure           │                                      │
│  │ - LiteLLM, FileStateManager,      │                                      │
│  │   MessageBus, Heartbeat/Checkpoint│                                      │
│  └───────────────────────────────────┘                                      │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          CORE LAYER (Domain)                                │
│                                                                              │
│  ┌─────────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Neue Protocols              │  │ Neue Domain-Modelle                  │  │
│  │                             │  │                                      │  │
│  │ EventSourceProtocol         │  │ AgentEvent (eingehende Events)       │  │
│  │ SchedulerProtocol           │  │ TriggerRule (Wenn-Dann-Regeln)       │  │
│  │ RuleEngineProtocol          │  │ Schedule (Zeitpläne)                 │  │
│  │ LearningStrategyProtocol    │  │ UserPreference (Benutzer-Prefs)      │  │
│  │                             │  │ AgentEventType (Enum-Erweiterung)    │  │
│  └─────────────────────────────┘  └──────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │ Bestehendes: Agent, LeanAgent, PlanningStrategy, StreamEvent,          │ │
│  │ MemoryRecord, MessageEnvelope, enums.py                                │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Komponente 1: Event Sources & Event Bus Integration

**Zweck:** Externe Ereignisquellen anbinden, die Events auf den internen Message Bus publizieren.

#### Neues Protocol: `EventSourceProtocol`

```python
# core/interfaces/event_source.py
class EventSourceProtocol(Protocol):
    """Protocol for external event sources that feed into the butler."""

    @property
    def source_name(self) -> str: ...

    async def start(self) -> None:
        """Begin polling/listening for events."""
        ...

    async def stop(self) -> None:
        """Gracefully stop the event source."""
        ...

    @property
    def is_running(self) -> bool: ...
```

#### Neues Domain-Modell: `AgentEvent`

```python
# core/domain/agent_event.py
@dataclass(frozen=True)
class AgentEvent:
    event_id: str                    # UUID
    source: str                      # "calendar", "email", "schedule", "webhook"
    event_type: str                  # "calendar.reminder", "email.received", "schedule.trigger"
    payload: dict[str, Any]          # Source-spezifische Daten
    timestamp: datetime
    metadata: dict[str, Any]         # Zusatzinfos (user_id, priority, etc.)
```

#### Konkrete Event Sources (Infrastructure)

| Source | Beschreibung | Polling/Push |
|--------|-------------|-------------|
| `CalendarEventSource` | Google Calendar API polling, prüft Events in den nächsten N Minuten | Polling (konfigurierbares Intervall) |
| `EmailEventSource` | IMAP IDLE oder Polling auf neue E-Mails | Push (IDLE) oder Polling |
| `WebhookEventSource` | FastAPI-Endpunkte für externe Webhooks (GitHub, Jira, etc.) | Push (HTTP) |
| `FileWatchEventSource` | Filesystem-Watcher für Dateiänderungen | Push (watchdog) |
| `RSSEventSource` | RSS/Atom Feed Polling | Polling |

Jede Source publiziert `AgentEvent`-Objekte auf den bestehenden `MessageBus` unter dem Topic `events.<source_name>`.

---

### Komponente 2: Scheduler Service

**Zweck:** Zeitgesteuerte Aktionen ermöglichen (Cron-artige Zeitpläne, Erinnerungen, wiederkehrende Tasks).

#### Neues Protocol: `SchedulerProtocol`

```python
# core/interfaces/scheduler.py
class SchedulerProtocol(Protocol):
    """Protocol for job scheduling."""

    async def add_job(self, job: ScheduleJob) -> str: ...
    async def remove_job(self, job_id: str) -> bool: ...
    async def list_jobs(self) -> list[ScheduleJob]: ...
    async def pause_job(self, job_id: str) -> None: ...
    async def resume_job(self, job_id: str) -> None: ...
```

#### Domain-Modell: `ScheduleJob`

```python
# core/domain/schedule.py
@dataclass
class ScheduleJob:
    job_id: str                      # UUID
    name: str                        # "daily_briefing", "calendar_check"
    schedule_type: ScheduleType      # CRON, INTERVAL, ONE_SHOT
    expression: str                  # "0 8 * * *" (cron) oder "every 15m" (interval)
    action: ScheduleAction           # Was soll passieren
    enabled: bool = True
    created_at: datetime
    last_run: datetime | None = None
    next_run: datetime | None = None

@dataclass
class ScheduleAction:
    action_type: str                 # "execute_mission", "send_notification", "publish_event"
    params: dict[str, Any]           # Mission-Text, Notification-Details, etc.
```

#### Implementierung: APScheduler-basiert

```python
# infrastructure/scheduler/apscheduler_service.py
class APSchedulerService:
    """APScheduler-backed implementation of SchedulerProtocol.

    Uses APScheduler with async support. Persists jobs to file/DB for
    restart survival.
    """
```

**Warum APScheduler?**
- Bewährt, produktionsreif, async-kompatibel
- Unterstützt Cron, Interval und einmalige Jobs
- Persistente Job-Stores (SQLite, PostgreSQL, MongoDB)
- Leichtgewichtig, kein externer Service nötig

#### Neue Tools für den Agenten

| Tool | Beschreibung |
|------|-------------|
| `schedule` | Erstellt/löscht/listet Zeitpläne ("Erinnere mich jeden Tag um 8 Uhr an meine Termine") |
| `reminder` | Einmalige Erinnerung zu einem bestimmten Zeitpunkt |

---

### Komponente 3: Event Router & Rule Engine

**Zweck:** Events mit Aktionen verknüpfen -- "Wenn Kalender-Event in 30 Min, dann Telegram-Notification senden".

#### Neues Protocol: `RuleEngineProtocol`

```python
# core/interfaces/rule_engine.py
class RuleEngineProtocol(Protocol):
    """Protocol for trigger-based rule evaluation."""

    async def add_rule(self, rule: TriggerRule) -> str: ...
    async def remove_rule(self, rule_id: str) -> bool: ...
    async def evaluate(self, event: AgentEvent) -> list[RuleAction]: ...
    async def list_rules(self) -> list[TriggerRule]: ...
```

#### Domain-Modell: `TriggerRule`

```python
# core/domain/trigger_rule.py
@dataclass
class TriggerRule:
    rule_id: str
    name: str                        # "calendar_reminder"
    description: str
    trigger: TriggerCondition        # Wann feuert die Regel
    action: RuleAction               # Was passiert
    enabled: bool = True
    priority: int = 0                # Höher = wird zuerst evaluiert

@dataclass
class TriggerCondition:
    source: str                      # "calendar", "email", "*" (wildcard)
    event_type: str                  # "calendar.upcoming", "email.received"
    filters: dict[str, Any]          # {"minutes_until": {"$lte": 30}}

@dataclass
class RuleAction:
    action_type: str                 # "notify", "execute_mission", "log_memory"
    params: dict[str, Any]           # Channel, Nachrichtenvorlage, Mission-Text
    template: str | None = None      # Jinja2-Template für dynamische Nachrichten
```

#### EventRouter (Application Layer)

```python
# application/event_router.py
class EventRouter:
    """Routes AgentEvents through the RuleEngine and dispatches resulting actions.

    Subscribes to events.* topics on the MessageBus.
    For each event:
      1. Evaluate all rules
      2. For "notify" actions → CommunicationGateway.send_notification()
      3. For "execute_mission" actions → AgentExecutor.execute_mission()
      4. For "log_memory" actions → MemoryService.remember()
    """
```

**Zwei Modi der Event-Verarbeitung:**

1. **Regelbasiert (deterministisch):** Vordefinierte Trigger-Rules werden ausgewertet. Schnell, vorhersagbar, kein LLM-Call nötig.

2. **LLM-basiert (intelligent):** Wenn keine passende Regel existiert oder der Benutzer es konfiguriert, wird der Event an den Agenten übergeben, der frei entscheidet, was zu tun ist. Ermöglicht intelligente, kontextbezogene Reaktionen.

```
AgentEvent eingehend
    │
    ├─► RuleEngine.evaluate()
    │       │
    │       ├─ Regel gefunden → direkte Aktion (notify, execute, log)
    │       │
    │       └─ Keine Regel → Weiterleitung an LLM?
    │               │
    │               ├─ LLM-Routing aktiviert → AgentExecutor mit Event-Kontext
    │               │
    │               └─ Nicht aktiviert → Event loggen, ignorieren
    │
    └─► Memory: Event wird im Langzeitgedächtnis protokolliert
```

#### Neues Tool: `rule_manager`

Erlaubt dem Agenten und dem Benutzer, Regeln zur Laufzeit zu erstellen:

```
Agent: "Ich erstelle eine Regel: Wenn ein Kalendertermin in 30 Minuten
        ansteht, sende ich dir eine Telegram-Nachricht."

→ rule_manager tool: add_rule(
    trigger={source: "calendar", event_type: "upcoming", filters: {minutes_until: 30}},
    action={type: "notify", channel: "telegram", template: "Erinnerung: {{event.title}} in 30 Min"}
  )
```

---

### Komponente 4: Enhanced Memory & Learning

**Zweck:** Vom manuellen Gedächtnis zum adaptiven Lernsystem.

#### Erweiterungen des Memory-Systems

| Feature | Beschreibung |
|---------|-------------|
| **Auto-Extraction** | Nach jeder Agent-Execution: LLM extrahiert automatisch Fakten, Präferenzen und Entscheidungen aus der Konversation und speichert sie als Memory-Records |
| **Semantic Search** | Optionaler Embedding-basierter Index (z.B. via sentence-transformers oder OpenAI Embeddings) über die Markdown-Records |
| **Memory Decay** | Ältere, selten abgerufene Erinnerungen werden zusammengefasst/archiviert; häufig genutzte bekommen höhere Relevanz |
| **Preference Tracking** | Spezielle `UserPreference`-Records: Sprache, Kommunikationsstil, bevorzugte Zeiten, häufige Themen |
| **Kontextuelle Anreicherung** | Bei jedem Agent-Start: automatische Suche nach relevantem Kontext aus dem Langzeitgedächtnis, Injection in den System-Prompt |

#### Neues Protocol: `LearningStrategyProtocol`

```python
# core/interfaces/learning.py
class LearningStrategyProtocol(Protocol):
    """Protocol for automatic knowledge extraction and memory management."""

    async def extract_learnings(
        self, conversation: list[dict], session_context: dict
    ) -> list[MemoryRecord]:
        """Extract facts, preferences, and decisions from a conversation."""
        ...

    async def enrich_context(
        self, mission: str, user_id: str
    ) -> list[MemoryRecord]:
        """Retrieve relevant memories for the current mission context."""
        ...

    async def compact_memories(
        self, scope: MemoryScope, max_age_days: int
    ) -> int:
        """Summarize/archive old memories. Returns number processed."""
        ...
```

#### Automatischer Lern-Loop

```
Agent führt Mission aus
    │
    ▼
Execution abgeschlossen (ExecutionResult)
    │
    ▼
LearningStrategy.extract_learnings(conversation_history)
    │
    ├─ LLM analysiert Konversation
    │   - "Benutzer bevorzugt Python mit Type-Hints"
    │   - "Benutzer hat Zahnarzttermin am 20.02."
    │   - "Projekt X verwendet FastAPI"
    │
    ▼
Neue MemoryRecords erstellt (scope=USER, kind=LONG_TERM)
    │
    ▼
Bestehende Records aktualisiert (wenn Widerspruch → neueres Wissen gewinnt)
```

---

### Komponente 5: Butler Daemon & Lifecycle

**Zweck:** Langlebiger Prozess, der alle Komponenten orchestriert.

#### Neuer CLI-Befehl: `taskforce butler`

```bash
# Startet den Butler im Daemon-Modus
taskforce butler start --profile butler

# Butler konfigurieren
taskforce butler rules list
taskforce butler rules add "calendar_reminder" --trigger "calendar.upcoming(30min)" --action "notify.telegram"
taskforce butler schedules list
taskforce butler schedules add "daily_briefing" --cron "0 8 * * *" --mission "Erstelle mein Tages-Briefing"

# Butler Status
taskforce butler status
taskforce butler stop
```

#### Butler-Profil (`configs/butler.yaml`)

```yaml
profile: butler
specialist: butler

persistence:
  type: file
  work_dir: .taskforce_butler

agent:
  planning_strategy: spar           # Reflektiver Ansatz für Butler-Aufgaben
  max_steps: 50

memory:
  type: file
  store_dir: .taskforce_butler/memory
  auto_extract: true                # Automatisches Lernen aktiviert
  semantic_search: true             # Embedding-basierte Suche
  compaction_interval_hours: 24     # Tägliche Memory-Kompaktierung

scheduler:
  enabled: true
  store: file                       # Job-Persistence
  timezone: Europe/Vienna

event_sources:
  - type: calendar
    provider: google
    poll_interval_minutes: 5
    lookahead_minutes: 60           # Events in den nächsten 60 Min

  - type: email
    provider: imap
    server: imap.gmail.com
    poll_interval_minutes: 10
    folders: [INBOX]

notifications:
  default_channel: telegram

rules:
  - name: calendar_reminder_30min
    trigger:
      source: calendar
      event_type: upcoming
      filters: { minutes_until: { $lte: 30 } }
    action:
      type: notify
      channel: telegram
      template: "📅 Erinnerung: **{{event.title}}** in {{event.minutes_until}} Minuten"

  - name: calendar_reminder_5min
    trigger:
      source: calendar
      event_type: upcoming
      filters: { minutes_until: { $lte: 5 } }
    action:
      type: notify
      channel: telegram
      template: "⏰ JETZT: **{{event.title}}** beginnt in {{event.minutes_until}} Minuten!"

  - name: daily_briefing
    schedule: "0 8 * * *"
    action:
      type: execute_mission
      params:
        mission: >
          Erstelle mein Tages-Briefing: Prüfe meinen Kalender für heute,
          fasse wichtige Termine zusammen, und sende mir das Briefing via Telegram.

tools:
  - web_search
  - web_fetch
  - file_read
  - file_write
  - python
  - memory
  - send_notification
  - calendar                        # NEU: Kalender-Tool (promoted aus Beispiel)
  - email                           # NEU: E-Mail-Tool
  - schedule                        # NEU: Zeitplan-Tool
  - reminder                        # NEU: Erinnerungs-Tool
  - rule_manager                    # NEU: Regel-Management-Tool
```

#### Daemon-Prozess Architektur

```
taskforce butler start
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  ButlerDaemon (api layer)                            │
│                                                       │
│  1. Starte FastAPI Server (für Webhooks + REST API)  │
│  2. Starte APScheduler (für Zeitpläne)               │
│  3. Starte Event Sources (Calendar, Email, ...)      │
│  4. Starte EventRouter (subscribed auf Message Bus)  │
│  5. Starte Learning-Kompaktierung (periodisch)       │
│                                                       │
│  Hauptloop:                                           │
│  ┌─────────────────────────────────────────────┐     │
│  │  MessageBus.subscribe("events.*")            │     │
│  │      │                                       │     │
│  │      ▼                                       │     │
│  │  EventRouter.route(event)                    │     │
│  │      │                                       │     │
│  │      ├─ Regel-Match → direkte Aktion         │     │
│  │      │   ├─ notify → Gateway.send_notification│    │
│  │      │   ├─ execute → Executor.execute_mission│    │
│  │      │   └─ log → MemoryService.remember      │    │
│  │      │                                       │     │
│  │      └─ Kein Match + LLM-Routing →           │     │
│  │          Agent entscheidet autonom            │     │
│  │                                               │     │
│  │  Heartbeat alle 30s → Runtime Tracker        │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  Graceful Shutdown:                                   │
│  - Event Sources stoppen                              │
│  - Scheduler stoppen                                  │
│  - Laufende Missions abschließen                     │
│  - State checkpointen                                 │
└──────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Fundament (Core-Erweiterungen)

**Neue Dateien im Core Layer:**

| Datei | Inhalt |
|-------|--------|
| `core/interfaces/event_source.py` | `EventSourceProtocol` |
| `core/interfaces/scheduler.py` | `SchedulerProtocol` |
| `core/interfaces/rule_engine.py` | `RuleEngineProtocol` |
| `core/interfaces/learning.py` | `LearningStrategyProtocol` |
| `core/domain/agent_event.py` | `AgentEvent`, `AgentEventType` Enum |
| `core/domain/schedule.py` | `ScheduleJob`, `ScheduleType`, `ScheduleAction` |
| `core/domain/trigger_rule.py` | `TriggerRule`, `TriggerCondition`, `RuleAction` |

**Erweiterung bestehender Dateien:**

| Datei | Änderung |
|-------|---------|
| `core/domain/enums.py` | Neue `AgentEventType`-Werte: `CALENDAR_UPCOMING`, `EMAIL_RECEIVED`, `SCHEDULE_TRIGGERED`, `RULE_FIRED`, `LEARNING_EXTRACTED` |
| `core/domain/memory.py` | Neuer `MemoryKind`: `PREFERENCE`, `LEARNED_FACT` |

### Phase 2: Scheduler & Event Sources (Infrastructure)

**Neue Dateien:**

| Datei | Inhalt |
|-------|--------|
| `infrastructure/scheduler/apscheduler_service.py` | APScheduler-Implementierung |
| `infrastructure/scheduler/job_store.py` | File-basierter Job-Store |
| `infrastructure/event_sources/calendar_source.py` | Google Calendar Polling |
| `infrastructure/event_sources/email_source.py` | IMAP Event Source |
| `infrastructure/event_sources/webhook_source.py` | Generic Webhook Receiver |
| `infrastructure/event_sources/base.py` | Shared Polling-Loop Logik |

**Neue Tools:**

| Datei | Tool |
|-------|------|
| `infrastructure/tools/native/calendar_tool.py` | Kalender CRUD (promoted aus Beispiel) |
| `infrastructure/tools/native/email_tool.py` | E-Mail lesen/senden |
| `infrastructure/tools/native/schedule_tool.py` | Zeitpläne erstellen/verwalten |
| `infrastructure/tools/native/reminder_tool.py` | Erinnerungen setzen |
| `infrastructure/tools/native/rule_manager_tool.py` | Regeln erstellen/verwalten |

### Phase 3: Event Router & Rule Engine (Application)

**Neue Dateien:**

| Datei | Inhalt |
|-------|--------|
| `application/event_router.py` | Event → Rule → Action Routing |
| `application/rule_engine.py` | Rule-Evaluation und Matching |
| `application/butler_service.py` | Butler-Lifecycle und Orchestrierung |

### Phase 4: Enhanced Memory & Learning (Infrastructure + Application)

**Neue/Geänderte Dateien:**

| Datei | Inhalt |
|-------|--------|
| `infrastructure/memory/semantic_index.py` | Embedding-basierter Suchindex |
| `application/learning_service.py` | Auto-Extraction nach Execution |

**Änderungen an bestehender Logik:**

| Datei | Änderung |
|-------|---------|
| `application/executor.py` | Nach `execute_mission()`: optional `learning_service.extract_learnings()` aufrufen |
| `core/domain/lean_agent_components/prompt_builder.py` | Relevante Memories in System-Prompt injizieren |

### Phase 5: Butler Daemon & CLI (API Layer)

**Neue Dateien:**

| Datei | Inhalt |
|-------|--------|
| `api/cli/commands/butler.py` | `taskforce butler` CLI-Kommandos |
| `api/butler_daemon.py` | Daemon-Prozess Orchestrierung |

**Neue Konfiguration:**

| Datei | Inhalt |
|-------|--------|
| `taskforce/configs/butler.yaml` | Butler-Profil |

---

## Abhängigkeiten (neue Packages)

| Package | Zweck | Warum dieses? |
|---------|-------|--------------|
| `apscheduler>=4.0` | Job Scheduling | Async-nativ, bewährt, persistente Job-Stores |
| `google-api-python-client` | Google Calendar API | Standard Google API Client |
| `aioimaplib` | Async IMAP | IMAP IDLE Support für E-Mail-Events |
| `jinja2` | Template-Rendering | Für dynamische Notification-Templates in Regeln |
| `sentence-transformers` (optional) | Semantic Search | Lokale Embeddings für Memory-Suche |

Alle als **optionale Extras** in `pyproject.toml`:

```toml
[project.optional-dependencies]
butler = ["apscheduler>=4.0", "google-api-python-client", "aioimaplib", "jinja2"]
semantic-memory = ["sentence-transformers"]
```

---

## Consequences

### Vorteile
- **Proaktiver Agent:** Kann eigenständig auf Events reagieren und den Benutzer informieren
- **Erweiterbar:** Neue Event Sources und Regeln ohne Code-Änderung hinzufügbar
- **Clean Architecture bewahrt:** Alle neuen Komponenten folgen der bestehenden Schicht-Trennung
- **Inkrementell umsetzbar:** Jede Phase ist unabhängig testbar und nutzbar
- **Bestehende Stärken genutzt:** CommunicationGateway, MessageBus, Memory, Runtime Tracking werden wiederverwendet
- **Dual-Mode:** Regelbasiert (schnell, vorhersagbar) + LLM-basiert (intelligent, flexibel)

### Risiken und Mitigationen
- **Ressourcenverbrauch:** Daemon-Prozess läuft permanent → Heartbeat-Monitoring, konfigurierbare Polling-Intervalle
- **Kosten:** LLM-Calls für Auto-Learning bei jeder Execution → opt-in, konfigurierbar, günstiges Modell für Extraction
- **Komplexität:** Viele neue Komponenten → Phasenweise Implementierung, gute Testabdeckung
- **Sicherheit:** E-Mail/Kalender-Zugriff → OAuth2, keine Passwörter in Config, Secrets via Env-Vars

### Alternativen betrachtet

1. **Externe Orchestrierung (n8n, Zapier):** Abgelehnt -- zu weit vom Agent-Ökosystem entfernt, kein Zugriff auf Memory/Tools.
2. **Celery + Redis:** Abgelehnt -- zu schwergewichtig für den Anwendungsfall, APScheduler reicht.
3. **Rein LLM-basierte Entscheidungen:** Abgelehnt als alleiniger Modus -- zu langsam und teuer für einfache Regeln. Hybrid-Ansatz gewählt.
4. **Kubernetes CronJobs:** Abgelehnt für lokale Nutzung -- Butler soll auch lokal auf dem Desktop laufen.

---

## Zusammenfassung

Die Event-Driven Butler Architecture transformiert Taskforce von einem reaktiven Ausführungssystem zu einem proaktiven persönlichen Assistenten. Der Kern der Änderung: **Ein langlebiger Daemon-Prozess, der auf Events horcht, Regeln auswertet, Aktionen auslöst und dabei kontinuierlich dazulernt.** Die bestehende Clean Architecture wird bewahrt und erweitert -- kein Breaking Change an existierendem Code.
