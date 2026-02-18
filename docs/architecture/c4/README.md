# C4 Architecture Diagrams – Taskforce

Dieses Verzeichnis enthält die C4-Architekturdiagramme für das Taskforce-Framework in [PlantUML](https://plantuml.com/) mit der [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML)-Bibliothek.

## Übersicht der Diagramme

| Datei | C4-Ebene | Beschreibung |
|-------|----------|--------------|
| `c4-system-context.puml` | Level 1 – System Context | Taskforce im Kontext von Nutzern und externen Systemen |
| `c4-container.puml` | Level 2 – Container | Technische Hauptbausteine innerhalb von Taskforce |
| `c4-component-core.puml` | Level 3 – Component | Domänenlogik, Agenten, Protokolle, Planungsstrategien |
| `c4-component-infrastructure.puml` | Level 3 – Component | LLM-Service, Persistenz, Tools, MCP, Butler-Infrastruktur |
| `c4-component-application.puml` | Level 3 – Component | Use-Cases, Factory, Executor, Epic-Orchestrierung, Butler-Services |
| `c4-component-api.puml` | Level 3 – Component | CLI-Befehle, REST-API-Routen, Schemas, Butler-Daemon |

---

## Level 1 – System Context

Zeigt Taskforce als Black Box mit den Akteuren und externen Systemen, mit denen es kommuniziert.

**Akteure:**
- **Developer** – führt Agenten über CLI oder REST-API aus
- **End User** – interagiert via Chat oder empfängt Benachrichtigungen
- **Administrator** – konfiguriert Profile, Plugins und Deployment

**Externe Systeme:**
- LLM Providers (OpenAI, Anthropic, Google, Azure, Ollama via LiteLLM)
- Azure AI Search (RAG)
- Google Calendar (Butler Event-Source)
- Telegram (Kommunikations-Provider)
- MCP Servers (Model Context Protocol)
- PostgreSQL (produktive Persistenz)
- Arize Phoenix (Observability / Tracing)
- Web / Internet (HTTP, Suche)
- Git Remote (Versionskontrolle)
- Webhook Sources (Butler Event-Source)

![System Context](c4-system-context.puml)

---

## Level 2 – Container

Zeigt die technischen Hauptbausteine innerhalb von Taskforce und ihre Beziehungen.

**Container:**

| Container | Technologie | Zweck |
|-----------|-------------|-------|
| **CLI Application** | Python / Typer / Rich | Lokale Nutzung via Terminal |
| **REST API Server** | Python / FastAPI | HTTP-Endpunkte für synchrone und Streaming-Ausführung |
| **Butler Daemon** | Python / asyncio | Langlebiger Hintergrundprozess für Event-driven Automation |
| **Application Layer** | Python | Use-Cases, Factory, Executor, Epic-Orchestrierung |
| **Core Domain** | Python (pure) | Reine Domänenlogik, Protokolle, Enums, Fehlertypen |
| **Infrastructure Layer** | Python | LLM-Provider, Persistenz, Tools, MCP, Tracing |
| **Extensions Package** | Python / YAML | Profile, Plugins, Skills, Communication-Provider |
| **File System Store** | JSON / Markdown | Lokale Persistenz (.taskforce/) |

![Container Diagram](c4-container.puml)

---

## Level 3 – Components

### Core Domain Layer (`src/taskforce/core/`)

Enthält die reine Domänenlogik ohne externe Abhängigkeiten.

**Hauptkomponenten:**
- **Agent / LeanAgent** – ReAct-Loop-Implementierungen
- **Planungsstrategien (4)** – NativeReAct, PlanAndExecute, PlanAndReact, SPAR
- **Agent Components** – MessageHistoryManager, ToolExecutor, PromptBuilder, MessageSanitizer, StateStore, ResourceCloser
- **Protokolle (15+)** – Strukturelle Subtypisierung für alle Layer-Grenzen
- **Domain Models** – ExecutionResult, StreamEvent, TokenUsage, EpicTask, TriggerRule, ScheduleJob
- **Domain Enums** – ExecutionStatus, EventType, LLMAction, MessageRole (keine Magic-Strings)
- **PlannerTool** – TodoList-Planung als nativer LLM-Tool-Call
- **TokenBudgeter / ContextPolicy** – Token-Budget-Management

![Core Domain](c4-component-core.puml)

---

### Infrastructure Layer (`src/taskforce/infrastructure/`)

Implementiert die Protokolle des Core-Layers und kommuniziert mit externen Systemen.

**Hauptkomponenten:**
- **LiteLLMService** – Unified LLM Provider (OpenAI, Anthropic, Google, Azure, Ollama)
- **FileStateManager** – Session-Persistenz als JSON-Dateien
- **FileMemoryStore** – Langzeit-Speicher (PREFERENCE, LEARNED_FACT) als Markdown
- **ToolResultStore** – Cacht große Tool-Ausgaben zur Token-Reduktion
- **ToolRegistry** – Zentrale Werkzeug-Katalogverwaltung (17 native Tools + RAG + MCP)
- **Native Tools (17)** – file, shell, python, git, web, search, edit, llm, memory, multimedia, ask_user, activate_skill, butler-tools (4)
- **RAG Tools** – Azure AI Search Integration (semantic_search, get_document, list_documents, global_analysis)
- **MCPConnectionManager** – MCP-Server-Verbindungsverwaltung (stdio / SSE)
- **SchedulerService / FileJobStore** – Asyncio-basierter Job-Scheduler mit Persistenz
- **CalendarEventSource / WebhookEventSource** – Butler Event-Sources
- **PhoenixTracer** – Arize Phoenix Distributed Tracing

![Infrastructure](c4-component-infrastructure.puml)

---

### Application Layer (`src/taskforce/application/`)

Orchestriert Use-Cases und verdrahtet Core-Domain mit Infrastructure.

**Hauptkomponenten:**
- **AgentFactory** – Dependency-Injection-Fabrik (config vs. Inline-Modus)
- **AgentExecutor** – Missions-Ausführungs-Orchestrator (Streaming-first)
- **ToolRegistry** – App-Layer-Wrapper für ToolRegistry (Singleton)
- **EpicOrchestrator** – Multi-Agenten-Pipeline (Planer → Worker → Richter)
- **TaskComplexityClassifier** – LLM-basierte Auto-Epic-Erkennung
- **ButlerService** – Butler-Lifecycle-Orchestrierung
- **EventRouter / RuleEngine** – Event-zu-Action-Dispatch mit TriggerRules
- **LearningService** – Automatische Extraktion aus Agenten-Ausführungen
- **SkillManager / SkillService** – Skill-Lifecycle und -Ausführung
- **PluginDiscovery / PluginLoader** – Plugin-System via Entry-Points
- **AgentRegistry** – Programmatische Agenten-Registrierung

![Application](c4-component-application.puml)

---

### API Layer (`src/taskforce/api/`)

Stellt CLI-Befehle und REST-API-Endpunkte bereit.

**CLI-Befehle (`api/cli/`):**
- `taskforce run mission` – Missions-Ausführung
- `taskforce chat` – Interaktiver Chat
- `taskforce epic` – Epic-Orchestrierung
- `taskforce skills` – Skill-Verwaltung
- `taskforce butler` – Butler-Daemon-Steuerung
- OutputFormatter (Rich) / SimpleChatInterface (Rich/Textual)

**REST-API-Routen (`api/routes/`):**
- `POST /api/v1/execute` – synchrone Ausführung
- `POST /api/v1/execute/stream` – SSE-Streaming
- `GET|POST|DELETE /api/v1/sessions` – Session-Management
- `GET|POST|DELETE /api/v1/agents` – Agenten-Registrierung
- `GET /api/v1/tools` – Tool-Discovery
- `GET /health` – Health-Check
- `POST /api/v1/integrations/{provider}/messages` – Externe Integrationen

**Butler Daemon (`api/butler_daemon.py`):** Langlebiger asyncio-Prozess für Event-Driven Automation.

![API Layer](c4-component-api.puml)

---

## Diagramme rendern

### Option 1: PlantUML Online

1. Öffne [https://www.plantuml.com/plantuml/uml/](https://www.plantuml.com/plantuml/uml/)
2. Füge den Inhalt einer `.puml`-Datei ein
3. Das Diagramm wird automatisch gerendert

### Option 2: VS Code Extension

Installiere die Extension [PlantUML](https://marketplace.visualstudio.com/items?itemName=jebbs.plantuml) von jebbs:
- Öffne eine `.puml`-Datei
- Drücke `Alt+D` (Preview)
- Erfordert lokale Java + PlantUML JAR oder den integrierten Server

### Option 3: Lokal mit PlantUML CLI

```bash
# Installation (macOS)
brew install plantuml

# Diagramme als PNG exportieren
plantuml docs/architecture/c4/*.puml

# Als SVG exportieren (empfohlen für hohe Qualität)
plantuml -tsvg docs/architecture/c4/*.puml
```

### Option 4: Docker

```bash
docker run --rm -v $(pwd):/data plantuml/plantuml -tsvg /data/docs/architecture/c4/*.puml
```

---

## Abhängigkeitsregeln (Clean Architecture)

```
API Layer
    ↓ (darf importieren)
Application Layer
    ↓ (darf importieren)
Infrastructure Layer
    ↓ (darf importieren)
Core Domain Layer
    (keine externen Abhängigkeiten)
```

**Verboten:** Core importiert Infrastructure, Infrastructure importiert Application oder API.

---

## Verwandte Dokumente

- [Architecture Overview](../index.md)
- [Architecture Entry Point](../../architecture.md)
- [Section 2: High-Level Architecture](../section-2-high-level-architecture.md)
- [Epic Orchestration](../epic-orchestration.md)
- [ADR Index](../../adr/index.md)
- [Source Tree](../source-tree.md)
