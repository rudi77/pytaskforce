<!-- Powered by BMAD™ Core -->

# Epic 8: Custom Agent Registry via API (Prompt + Tools + MCP) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Hoch  
**Owner:** Development Team  
**Geschätzter Aufwand:** M (Medium) - 3 Stories  

### Story Status Overview

| Story | Title | Status | SP | Abhängigkeiten |
|-------|-------|--------|----|----------------|
| 1 | [Custom Agent Registry (CRUD + YAML)](../stories/story-8.1-custom-agent-registry-crud.md) | 📝 Draft | 5 | - |
| 2 | [Tool Catalog + Allowlist Validation](../stories/story-8.2-tool-catalog-allowlist.md) | 📝 Draft | 5 | Story 1 |
| 3 | [Execute by `agent_id` (LeanAgent-only)](../stories/story-8.3-execute-by-agent-id.md) | 📝 Draft | 5 | Stories 1-2 |

**Gesamt Story Points:** 15 SP

## Epic Goal

Es soll möglich sein, **neue Agenten über die Taskforce API zu definieren und zu persistieren**, sodass sie später wiederverwendbar sind. Ein User kann dabei:

- den **Agent Prompt** (Kernel-/System-Prompt + optionale Zusatz-Instruktionen) definieren
- die **Tools** definieren, die der Agent nutzen darf (**allowlisted** auf Tools, die das Service anbietet)
- optional **MCP Server** integrieren, um zusätzliche Tools dynamisch bereitzustellen

**Scope (vereinbart):**
- Persistenz ist **file-based als YAML** (analog zu `taskforce/configs/*.yaml`)
- Nur **LeanAgent** (kein Legacy Agent)
- Agenten sind zunächst **global sichtbar** (keine Auth/Ownership Scoping)

**Wichtig (Kompatibilität):**
- Die bereits vorhandenen Agenten/Profile in `taskforce/configs/*.yaml` müssen weiterhin **über API und CLI aufrufbar** bleiben (über das bestehende `profile`-Konzept).

---

## Epic Description

### Existing System Context

- **Current relevant functionality:**
  - Agenten werden heute über **YAML Profile** (`configs/*.yaml`) konfiguriert und via `AgentFactory` instanziiert.
  - Tool-Auswahl erfolgt über `config.tools` als Liste von `{type, module, params}` (explizite Tool-Liste) oder über Specialist Defaults.
  - MCP Tools werden optional via `mcp_servers` in der Profile-Config geladen und als `ToolProtocol`-Wrapper bereitgestellt.
- **Technology stack:** Python 3.11, FastAPI, Clean Architecture, `uv`
- **Integration points:**
  - `taskforce/src/taskforce/application/factory.py` (`create_agent`, `_create_native_tools`, `_create_mcp_tools`)
  - `taskforce/src/taskforce/api/routes/execution.py` (Mission Execution via `profile`, `lean`)
  - `taskforce/src/taskforce/infrastructure/persistence/file_state.py` (Datei-basierte Persistenz in `.taskforce/*`)

### Enhancement Details

**Was hinzugefügt wird (MVP):**

1. **AgentDefinition (Konzept + YAML)**
   - `agent_id` (stable identifier, file name)
   - `name`, `description`
   - `prompt`:
     - `system_prompt`: kompletter System Prompt für den LeanAgent (string)
       - *Hinweis:* Wir verzichten bewusst auf starre Prompt-Komposition (Kernel/Specialist), damit User maximale Kontrolle haben.
   - `tools`:
     - `allowlist`: Liste von Tool-Namen, die der Agent verwenden darf (**muss** Subset des Service Tool Catalog sein)
   - optional `mcp_servers`: Liste von MCP Servern (stdio/sse) (Format kompatibel zu `configs/dev.yaml`)
   - optional `mcp_tools`:
     - `allowlist`: wenn gesetzt, wird das MCP Toolset zusätzlich eingeschränkt
   - `created_at`, `updated_at`: optional, wird vom Service bei Create/Update gesetzt (nicht vom Client erzwingen)

2. **Persistenz**
   - Datei-basierte Ablage als YAML analog zum bestehenden Profile Pattern:
     - `taskforce/configs/custom/{agent_id}.yaml`
   - CRUD-Operationen: create/list/get/update/delete
   - Es wird **kein** globales “index file” benötigt; `GET /agents` scannt das Verzeichnis.

3. **API**
   - Neue REST Endpoints:
     - `POST /api/v1/agents` (create)
     - `GET /api/v1/agents` (list)
     - `GET /api/v1/agents/{agent_id}` (get)
     - `PUT /api/v1/agents/{agent_id}` (update)
     - `DELETE /api/v1/agents/{agent_id}` (delete)
   - `GET /api/v1/agents` liefert pro Agent mindestens:
     - `agent_id`, `name`, `description`, `system_prompt`, `tool_allowlist`, `mcp_servers` (falls gesetzt)
   - Optional/empfohlen: `GET /api/v1/tools` (Tool-Katalog des Services inkl. Namen + Schema), damit der User valide Tool-Listen bauen kann.

4. **Execution Integration**
   - Erweiterung der Execution Requests um optionales Feld `agent_id`.
   - Wenn `agent_id` gesetzt ist: Agent wird **als LeanAgent** aus `AgentDefinition` gebaut (Prompt + Tool-Allowlist + MCP Server).
   - Wenn nicht gesetzt: bestehendes Verhalten bleibt (Profile-basiert).

**Wie es integriert wird:**

- `AgentFactory` bekommt eine kleine Erweiterung: “create agent from agent definition”.
- Tool-Validation wird **nicht hard-coded** über Business Rules, sondern über **Service Tool Catalog** (bestehende Tools + ggf. MCP Tools) allowlisted.
- MCP Server sind **optional**. Falls konfiguriert, werden MCP Tools wie bisher als `ToolProtocol` wrapped.

**Success criteria:**

- User kann via API einen Agent definieren und später per `agent_id` ausführen.
- Tool-Lists werden strikt auf “Service-Tools” begrenzt (inkl. MCP Tools nur, wenn MCP integriert/erlaubt).
- Bestehende `/execute` und `/execute/stream` Calls bleiben kompatibel (optional neue Felder).

---

## Developer Specification (MVP)

### 1) Custom Agent YAML: Schema (normativ)

**Ablageort:**
- `taskforce/configs/custom/{agent_id}.yaml`

**Filename Rules:**
- `{agent_id}` wird direkt aus dem Dateinamen abgeleitet (ohne `.yaml`)
- Erlaubte Zeichen: `[a-z0-9][a-z0-9-_]{2,63}` (lowercase, 3–64 chars)

**Schema (YAML):**
- `agent_id` (optional): wenn vorhanden, muss es mit dem Dateinamen matchen
- `name` (required, 1–100 chars)
- `description` (required, 1–500 chars)
- `prompt.system_prompt` (required, non-empty string)
- `tools.allowlist` (required, list[str], min 1)
- `mcp_servers` (optional, list)
- `mcp_tools.allowlist` (optional, list[str])
- `created_at` / `updated_at` (optional, ISO string; vom Service verwaltet)

### 2) Custom Agent YAML: Beispiel (Minimal, ohne MCP)

```yaml
agent_id: "invoice-extractor"
name: "Invoice Extractor"
description: "Extrahiert strukturierte Felder aus Rechnungs-Text und gibt JSON zurück."
prompt:
  system_prompt: |
    Du bist ein LeanAgent. Nutze Tools nur, wenn es nötig ist.
    Antworte standardmäßig mit sauberem JSON.
    Wenn du Dateien lesen musst: nutze file_read.
tools:
  allowlist:
    - "file_read"
    - "file_write"
    - "python"
created_at: "2025-12-12T10:00:00Z"
updated_at: "2025-12-12T10:00:00Z"
```

### 3) Custom Agent YAML: Beispiel (mit MCP Server + MCP Tool Allowlist)

```yaml
agent_id: "devops-wiki-agent"
name: "DevOps Wiki Agent"
description: "Interagiert mit Azure DevOps Wiki über MCP Tools."
prompt:
  system_prompt: |
    Du bist ein LeanAgent.
    Nutze bevorzugt MCP Tools, wenn sie verfügbar sind.
    Liste Wiki-Seiten kurz und strukturiert.
tools:
  allowlist:
    - "ask_user"
    - "web_search"
mcp_servers:
  - type: stdio
    command: npx
    args:
      - "-y"
      - "azure-devops-wiki-mcp"
    env:
      AZURE_DEVOPS_URL: "${AZURE_DEVOPS_URL}"
      AZURE_DEVOPS_PROJECT: "${AZURE_DEVOPS_PROJECT}"
      AZURE_DEVOPS_PAT: "${AZURE_DEVOPS_PAT}"
      AZURE_DEVOPS_ORGANIZATION: "${AZURE_DEVOPS_ORGANIZATION}"
mcp_tools:
  allowlist:
    - "list_wiki"
    - "get_wiki_page"
```

### 4) Tool Catalog (Service Offered Tools): API Contract

**Endpoint:** `GET /api/v1/tools`

**Purpose:** Liefert alle Tools, die dieses Service anbieten kann (native + optional MCP Tools, wenn “global MCP servers” konfiguriert sind).

**Response (Beispiel):**
- `tools[]`:
  - `name`: string (ToolProtocol.name) — *das ist der Name in `tools.allowlist`*
  - `description`: string
  - `parameters_schema`: JSON schema / OpenAI function schema (dict)
  - `origin`: `"native" | "mcp"`
  - `mcp_server_id`: optional string (wenn origin=mcp)

**Error Handling:**
- 500 nur bei echten Serverfehlern; ansonsten leere Liste wenn keine Tools verfügbar sind (sollte praktisch nie passieren).

### 5) Agents API: Contracts (CRUD)

#### 5.1 Create Agent

**Endpoint:** `POST /api/v1/agents`

**Request (JSON, Beispiel):**
```json
{
  "agent_id": "invoice-extractor",
  "name": "Invoice Extractor",
  "description": "Extrahiert strukturierte Felder aus Rechnungs-Text und gibt JSON zurück.",
  "system_prompt": "Du bist ein LeanAgent ...",
  "tool_allowlist": ["file_read", "file_write", "python"],
  "mcp_servers": [],
  "mcp_tool_allowlist": []
}
```

**Response (JSON, Beispiel):**
```json
{
  "agent_id": "invoice-extractor",
  "name": "Invoice Extractor",
  "description": "Extrahiert strukturierte Felder aus Rechnungs-Text und gibt JSON zurück.",
  "system_prompt": "Du bist ein LeanAgent ...",
  "tool_allowlist": ["file_read", "file_write", "python"],
  "mcp_servers": [],
  "mcp_tool_allowlist": [],
  "created_at": "2025-12-12T10:00:00Z",
  "updated_at": "2025-12-12T10:00:00Z"
}
```

**Validation Rules:**
- `agent_id`: required, muss Filename Rules entsprechen, darf noch nicht existieren
- `tool_allowlist`: required, min 1, muss Subset von `GET /api/v1/tools` (origin=native) sein
- `mcp_servers`: optional
  - wenn gesetzt: nur `type in {stdio, sse}`
  - stdio: `command` required, `args` optional list, `env` optional dict
  - sse: `url` required
- `mcp_tool_allowlist`: optional
  - wenn gesetzt: muss Subset der durch `mcp_servers` discoverten Tools sein

**Error Codes:**
- 400: invalid payload / invalid tool names / invalid MCP config
- 409: agent_id already exists

#### 5.2 List Agents (IMPORTANT: vollständige Übersicht)

**Endpoint:** `GET /api/v1/agents`

**Purpose:** Liefert eine **vollständige Übersicht** aller Agenten, die über das System nutzbar sind:
- **Custom Agents** aus `taskforce/configs/custom/*.yaml` (source=`custom`)
- **Profile Agents** aus `taskforce/configs/*.yaml` (source=`profile`)

**Rationale:** User sollen über die API **alles discovern** können, was sie ausführen können (ohne die Projektstruktur zu kennen).

**Response (JSON, Beispiel):**
```json
{
  "agents": [
    {
      "source": "custom",
      "agent_id": "invoice-extractor",
      "name": "Invoice Extractor",
      "description": "Extrahiert strukturierte Felder aus Rechnungs-Text und gibt JSON zurück.",
      "system_prompt": "Du bist ein LeanAgent ...",
      "tool_allowlist": ["file_read", "file_write", "python"],
      "mcp_servers": [],
      "mcp_tool_allowlist": [],
      "created_at": "2025-12-12T10:00:00Z",
      "updated_at": "2025-12-12T10:00:00Z"
    },
    {
      "source": "profile",
      "profile": "dev",
      "specialist": "generic",
      "tools_config": [
        {"type": "WebSearchTool", "module": "taskforce.infrastructure.tools.native.web_tools", "params": {}}
      ],
      "mcp_servers": [],
      "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"}
    }
  ]
}
```

**Behavior Notes:**
- Listing basiert auf Directory Scan:
  - `taskforce/configs/custom/*.yaml` → Custom Agents
  - `taskforce/configs/*.yaml` → Profile Agents (exkludiere `llm_config.yaml` und `custom/`)
- Corrupt YAML → Agent wird übersprungen und als Warnung geloggt (optional: `include_invalid=true` später)

#### 5.3 Get Agent

**Endpoint:** `GET /api/v1/agents/{agent_id}`
- 404 wenn nicht gefunden

#### 5.4 Update Agent

**Endpoint:** `PUT /api/v1/agents/{agent_id}`

**Rules:**
- `agent_id` im Path ist authoritative
- Update ist “replace” (PUT) oder “merge” (optional) – MVP: replace
- `updated_at` wird server-side aktualisiert

**Error Codes:**
- 400 invalid payload
- 404 not found

#### 5.5 Delete Agent

**Endpoint:** `DELETE /api/v1/agents/{agent_id}`
- 204 no content (recommended)
- 404 not found

### 6) Execution Contract Update (LeanAgent-only for agent_id)

**Existing Endpoint:** `POST /api/v1/execute`

**Additive Fields:**
- `agent_id`: optional string

**Rules:**
- Wenn `agent_id` gesetzt ist:
  - Service lädt AgentDefinition
  - Service erstellt **LeanAgent** (unabhängig vom Request Feld `lean`)
  - Toolset ist: `native tools filtered by tool_allowlist` + `MCP tools filtered by mcp_tool_allowlist` (falls konfiguriert)
  - `profile` dient weiterhin für LLM settings (default_model, llm_config, persistence work_dir), aber Prompt/Tools kommen aus AgentDefinition
- Wenn `agent_id` nicht gesetzt ist: bestehendes Verhalten (profile-based, `lean` steuert Agent Type)

**Kompatibilitäts-Callout (Profile Agents):**
- Profile Agents werden weiterhin wie bisher ausgeführt:
  - **API:** setze `profile` auf den Profilnamen aus `taskforce/configs/<profile>.yaml`
  - **CLI:** setze `--profile <profile>`
- Dieses Epic fügt nur eine zusätzliche Option hinzu (`agent_id`), ersetzt aber nicht das Profile-System.

**Error Codes:**
- 404: agent_id not found
- 400: agent config invalid (should be rare; indicates stored YAML invalid)

### 7) Wiring Details (Implementation Notes)

**New components (suggested placement):**
- `taskforce/src/taskforce/infrastructure/persistence/file_agent_registry.py`
  - `list_agents()`, `get_agent(agent_id)`, `create_agent(def)`, `update_agent(agent_id, def)`, `delete_agent(agent_id)`
  - YAML read/write using existing `yaml` dependency
  - directory: `taskforce/configs/custom/`

**API routes:**
- `taskforce/src/taskforce/api/routes/agents.py`
  - Implements CRUD endpoints
- `taskforce/src/taskforce/api/routes/tools.py`
  - Implements tool catalog
- Register routers in `taskforce/src/taskforce/api/server.py`

**Factory / Executor:**
- Extend `AgentFactory` with:
  - `create_lean_agent_from_definition(definition, profile, user_context=None)`
  - uses existing tool creation methods:
    - instantiate native tools from a “tools_config synthesized from allowlist”
    - call `_create_mcp_tools` if definition has `mcp_servers`
- Extend `AgentExecutor.execute_mission` to accept `agent_id`
  - if `agent_id` set: load from registry and create LeanAgent via factory method above

### 8) Non-Goals (MVP)

- Keine AuthN/AuthZ / Ownership / per-user scoping
- Keine DB Persistenz (YAML reicht)
- Keine UI (nur API)
- Kein “agent composition” / inheritance / prompt templating engine

---

## Stories

### Story 1: Agent Registry (CRUD) + File Persistence

**Beschreibung:** Implementiere AgentDefinition + YAML-basierte Persistenz (`configs/custom/`) und CRUD Endpoints.

**Änderungen (high level):**
- Neue Komponente im Infrastructure-Persistenz Layer: `FileAgentRegistry` (ähnlicher Stil wie `FileStateManager`)
- Neue API Routes `api/routes/agents.py` + Router in `api/server.py`

**Akzeptanzkriterien:**
- [ ] `POST /api/v1/agents` erstellt einen Agenten und persistiert ihn
- [ ] `GET /api/v1/agents` listet **alle** Agenten inkl. `description`, `system_prompt`, `tool_allowlist`, `mcp_servers`, `mcp_tool_allowlist`
- [ ] `GET/PUT/DELETE /api/v1/agents/{agent_id}` funktionieren
- [ ] Persistenz liegt unter `taskforce/configs/custom/` und ist YAML (kompatibel zum vorhandenen Config-Stil)
- [ ] Fehlerfälle: Duplicate ID, not found, invalid payload (400/404)

---

### Story 2: Tool Catalog + Allowlist Validation (inkl. MCP)

**Beschreibung:** Der User darf nur Tools auswählen, die das Service tatsächlich anbietet. Dafür wird ein Tool-Katalog bereitgestellt und im Agent-Create/Update validiert.

**Änderungen (high level):**
- Neuer Endpoint `GET /api/v1/tools` (oder Erweiterung bestehender CLI Funktionalität in REST)
- Validierung: `tool_allowlist` muss Subset von `available_tools` sein (native + optional MCP)
- Optional: `mcp_servers` pro AgentDefinition → discovery + `mcp_tool_allowlist` (wenn gesetzt)

**Akzeptanzkriterien:**
- [ ] Tool-Katalog liefert Tool-Namen + Parameter-Schema
- [ ] Create/Update rejectet unbekannte Tools mit klarer Fehlermeldung
- [ ] Wenn `mcp_servers` gesetzt: MCP discovery wird versucht; Failures werden graceful gehandhabt (log warning, nur native tools bleiben)

---

### Story 3: Execution by `agent_id` (Prompt + Tools) ohne Breaking Changes

**Beschreibung:** Execution Endpoints unterstützen die Ausführung eines gespeicherten Agenten.

**Änderungen (high level):**
- `ExecuteMissionRequest` bekommt optional `agent_id`
- `AgentExecutor`/`AgentFactory` bauen Agent anhand der AgentDefinition (Prompt + Tools + MCP)
- Backward Compatibility: wenn `agent_id` nicht gesetzt ist → bestehendes profile-based Verhalten

**Akzeptanzkriterien:**
- [ ] `/api/v1/execute` unterstützt `agent_id` und führt den Agenten aus
- [ ] `/api/v1/execute/stream` unterstützt `agent_id` (Streaming bleibt erhalten)
- [ ] Wenn `agent_id` nicht existiert → 404
- [ ] Logs enthalten `agent_id` (für Traceability)
- [ ] Wenn `agent_id` gesetzt ist, wird nur LeanAgent verwendet (Legacy bleibt unberührt)

---

## Compatibility Requirements

- [x] Existing APIs remain unchanged (nur additive Felder/Endpoints)
- [x] File-based persistence bleibt Standard (keine DB-Migration erforderlich für MVP)
- [x] MCP Integration bleibt optional

---

## Risk Mitigation

- **Primary Risk:** Sicherheits-/Abuse-Risiko durch frei definierbare Prompts + potente Tools (Shell/File/Git).
  - **Mitigation:** Tool-Allowlist ist verpflichtend; optional spätere AuthN/AuthZ + per-user scope.
- **Secondary Risk:** MCP Server Instabilität kann Tool Discovery verlangsamen.
  - **Mitigation:** Timeouts + graceful degradation (Server wird übersprungen).
- **Rollback Plan:** Neue Endpoints entfernen; gespeicherte Agent-Dateien können ignoriert/gelöscht werden.

---

## Definition of Done

- [ ] CRUD AgentDefinition via API + persistiert
- [ ] Tool-Katalog + Allowlist Validation
- [ ] Execution via `agent_id` inkl. Streaming
- [ ] Keine Regression in bestehenden Execution-/Session-Endpunkten
- [ ] Dokumentation: API Beispiele + JSON Payload Beispiele

---

## Story Manager Handoff

> Bitte entwickle detaillierte User Stories für dieses Brownfield Epic. Key considerations:
>
> - Integration Points: `AgentFactory` (Tools/MCP), `execution.py` (ExecuteMissionRequest), Persistenz unter `.taskforce/*`
> - Kritisch: Tool-Allowlist muss auf Service-Angebot begrenzt sein
> - MCP ist optional und muss robust (timeouts, graceful degradation) sein
> - Backward Compatibility: bestehende Profile-basierte Calls dürfen nicht brechen


