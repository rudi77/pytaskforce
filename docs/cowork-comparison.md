# Taskforce ↔ Claude Cowork — Vergleich & Roadmap

**Stand:** 2026-05-15
**Branch:** `claude/taskforce-cowork-comparison-cvrWp`
**Ziel:** Was muss passieren, damit die Taskforce Community Edition zum Open-Source-Pendant von Claude Cowork wird – inkl. Desktop-App.

---

## 1. Was ist Claude Cowork heute (Mai 2026)?

Claude Cowork ist Anthropics agentic Layer **außerhalb** des Terminals. Die
Desktop-App hat drei Tabs: **Chat**, **Cowork** (Dispatch / Knowledge-Work)
und **Code** (Claude Code Desktop). Die wichtigsten Bausteine:

### Kernfeatures

| Feature | Funktion |
|---------|----------|
| **Direct local file access** | Liest/schreibt lokale Dateien ohne Upload/Download |
| **Sub-agent coordination** | Spaltet komplexe Aufgaben automatisch in parallele Sub-Agent-Workstreams |
| **Office-Outputs** | Generiert `.xlsx` (mit Formeln, VLOOKUP, Bedingter Formatierung), `.pptx`, `.docx`, `.pdf` |
| **Long-running tasks** | Keine Conversation-Timeouts, autom. Context-Compaction |
| **Scheduled tasks** | `/schedule` oder Sidebar → hourly/daily/weekly/weekdays/manual. Läuft nur wenn App offen + Rechner wach |
| **Dispatch** | Persistente Konversation, die Tasks empfängt und entscheidet, ob sie als Code-Session, Cowork-Task oder Computer-Use ausgeführt werden |
| **Computer Use** | Klickt/tippt/scrollt auf deinem Bildschirm wenn kein Connector/Tool greift (View-only/Click-only/Full Tiers pro App) |
| **Connectors** | Google Drive, Gmail, Calendar, Slack, GitHub, Linear, Notion, … MCP mit GUI-Setup |
| **Plugins / Skills** | Wiederverwendbare Bundles aus Skills + Connectors + Sub-Agents |
| **Remote / Cloud sessions** | Optional auf Anthropic-Cloud auslagern (überlebt App-Schließen) |
| **Mobile Dispatch** | Vom Handy Tasks starten, Push-Benachrichtigungen, Approval on demand |

### Desktop-App (Code-Tab) – UI-Bausteine

| Pane / UI-Element | Zweck |
|---|---|
| **Sidebar mit Parallelsessions** | `Cmd/Ctrl+N` neue Session, `Ctrl+Tab` zyklisch, Split-View per `Cmd/Ctrl`-Klick |
| **Git-Worktrees pro Session** | `.claude/worktrees/`, isolierte Branches, Auto-Archive nach PR-Merge |
| **Chat-Pane** | Streaming, Tool-Call-Folds, View-Modes (Normal/Verbose/Summary) |
| **Diff-Pane** | File-by-File-Review, Inline-Kommentare → Claude reagiert |
| **Preview-Pane** | Embedded Browser, Auto-Verify (Screenshot + DOM-Check nach jeder Änderung), Persist Cookies |
| **Terminal-Pane** | Integriertes Terminal in Session-Working-Dir, gleiche ENV wie Claude |
| **File-Pane** | Click-to-open, Save mit Konflikterkennung, "Open in VS Code / Cursor / Zed", Show in Finder |
| **Plan-Pane** | Plan-Mode Ergebnisse |
| **Tasks-Pane** | Hintergrund-Sub-Agents, Background-Shell, Workflows |
| **Subagent-Pane** | Output eines spezifischen Sub-Agents |
| **Side-Chat** (`Cmd/Ctrl+;`, `/btw`) | Frage mit Session-Kontext, ohne Hauptthread zu stören |
| **CI/PR-Bar** | gh-CLI Polling, Auto-Fix-Toggle, Auto-Merge-Toggle, Desktop-Notif bei CI-Done |
| **Permission-Mode-Switcher** | Ask / Auto-Accept-Edits / Plan / Auto / Bypass |
| **Usage-Ring** | Context-Window + Plan-Usage, `/compact` Trigger |
| **Continue in…** | Session an Web/IDE/Cloud weiterreichen |
| **Customize** Sidebar | Connectors/Skills/Plugins zentral verwalten |
| **@mention + Drag-and-Drop** | Files in Prompt, Bilder/PDFs |
| **OS-Benachrichtigungen** | bei Session-Done, CI-Done, Approval-Needed |

---

## 2. Was hat Taskforce heute?

### Vorhanden ✅

- **Backend**: 4-Layer Clean-Architecture, ReAct/Plan-and-Execute/SPAR, ContextManager, Tool-Registry, MCP-Client, ACP-Federation, Sub-Agent-Spawner, Parallel-Agent-Tool, Skills (context/prompt/agent), Plugins, OAuth2, Multi-Tenant-Override-Hooks
- **Persistente Conversations** (ADR-016) + `FileConversationStore`
- **Communication Gateway**: Telegram/Teams/Slack/REST, proaktive Push-Notifications, `/link <code>` Pairing
- **Butler-Agent**: Event-driven Daemon, Scheduler (Cron/Interval), Rule-Engine, Polling/Webhook/IMAP/Calendar/GitHub Event-Sources, Standing Goals (ADR-024)
- **Coding-Agent**: Epic-Orchestration, Sub-Agents (Planner/Worker/Reviewer/Test-Engineer)
- **LLM-Router** (multi-provider, dynamic routing per Phase-Hint)
- **Wiki-Memory** (ADR-020), Learning-Service (Post-Mission Knowledge-Extraction)
- **REST-API** + Streaming (`/api/v1/execute`, `/conversations/*/messages/stream`)
- **Settings-Store** mit Fernet-verschlüsseltem JSON, Hot-Reload via Hydrator

### Frontend (`ui/`) – aktueller Stand

React 18 + Vite + Tailwind + Zustand + React-Query + Radix-UI.

Bestehende Seiten:
- `/` Dashboard
- `/agents` + `/agents/:id` + `/agents/new` + `/agents/compare` (5-Step-Wizard, YAML-Diff)
- `/chat` + `/chat/:conversationId` (SSE-Streaming, Markdown, Tool-Call-List, File-Attachments)
- `/monitoring` + `/monitoring/runs/:sessionId` (Cost/Token-Analytics, Run-Tracing)
- `/workflows` (Schedule/Webhook/Event/Chat/Manual-Trigger CRUD)
- `/capabilities` (Tool+Skill-Katalog, Approval-Badges)
- `/acp` (Federation-Peers)
- `/evals` (minimal)
- `/settings` (5 Tabs: General/LLM-Providers/Channels/Agent-Visibility/Integrations)
- `/login` (Tenant + Email/Password)

---

## 3. Gap-Analyse (Cowork vs. Taskforce)

Legende: ✅ vorhanden · 🟡 teilweise · ❌ fehlt

### A. Konversation & Mission

| Cowork | Taskforce |
|---|---|
| ✅ Streaming Chat | ✅ SSE in `/chat/:id` |
| ✅ Markdown / Code-Blöcke | ✅ react-markdown + GFM |
| ✅ Tool-Call-Folds, View-Modes (Normal/Verbose/Summary) | 🟡 `ToolCallList`, **kein** View-Mode-Toggle |
| ✅ File-Attachments + @mention | 🟡 Attachment-Chips, **kein** @mention-Picker |
| ✅ Drag-and-Drop in Prompt | ❌ |
| ✅ Side-Chat (`/btw`) | ❌ |
| ✅ `/compact` Context-Trigger | 🟡 Backend kann komprimieren, **kein** UI-Button |
| ✅ Usage-Ring (Context + Plan-Usage) | 🟡 Cost-Charts in Monitoring, **nicht** im Chat-Header |
| ✅ Permission-Mode-Switcher in Session | ❌ (Approval-Flags nur als Badges) |
| ✅ Stop-Button mid-stream | 🟡 Backend hat `executor.interrupt`, UI-Button fehlt |

### B. Parallel-Sessions & Workspace

| Cowork | Taskforce |
|---|---|
| ✅ Multi-Session-Sidebar | ❌ (Conversations-Liste = sequenziell pro User) |
| ✅ `Cmd+N` / `Ctrl+Tab` Hotkeys | ❌ |
| ✅ Split-View (zwei Sessions nebeneinander) | ❌ |
| ✅ Git-Worktrees pro Session | ❌ |
| ✅ Drag-and-Drop Pane-Layout | ❌ (keine Pane-Engine) |
| ✅ Session-Filter (Status/Project/Env) + Group-by-Project | ❌ |
| ✅ Auto-Archive bei PR-Merge | ❌ |
| ✅ Per-Session-Working-Directory | ❌ (Working-Dir global pro Profil) |

### C. Datei- & Code-Erlebnis

| Cowork | Taskforce |
|---|---|
| ✅ File-Pane mit Inline-Edit + Save | ❌ |
| ✅ Diff-Viewer mit Inline-Kommentar → Claude antwortet | 🟡 YAML-Diff für Profile, **kein** allg. Code-Diff im Chat |
| ✅ Click-to-open in VS Code / Cursor / Zed | ❌ |
| ✅ Show-in-Finder/Explorer | ❌ |
| ✅ Preview-Pane (Embedded Browser, Auto-Verify) | ❌ |
| ✅ Embedded Terminal mit Session-ENV | ❌ |
| ✅ PDF/Image/Video-Inline-Preview | ❌ |
| ✅ Office-Outputs (.xlsx mit Formeln, .pptx, .docx) | 🟡 Backend hat `docx`/`pptx`/`excel`-Tools, **keine** UI-Anzeige der erzeugten Files |

### D. Git & PR-Integration

| Cowork | Taskforce |
|---|---|
| ✅ PR-Status-Bar im Session-Header | ❌ |
| ✅ Auto-Fix / Auto-Merge Toggles | 🟡 nur als Subscription via MCP, kein UI |
| ✅ Worktree-Management | ❌ |
| ✅ "Open PR" Button im Chat | ❌ |
| ✅ Visual Diff Review + Code-Review Button | ❌ |

### E. Long-Running / Background / Scheduled

| Cowork | Taskforce |
|---|---|
| ✅ Tasks-Pane (Sub-Agents + Background-Shell live) | 🟡 `/monitoring` Run-Liste, kein Live-Pane in Chat |
| ✅ Scheduled-Tasks Sidebar + `/schedule` | ✅ Backend `Workflows` + Butler-Scheduler, **UI** nur via `/workflows` Page |
| ✅ Remote/Cloud-Session Handoff | 🟡 ACP-Federation existiert technisch, **kein** "Continue in Cloud"-Button |
| ✅ Mobile Dispatch + Push | 🟡 Telegram-Gateway funktioniert, **kein** dezidiertes Mobile-Dispatch-UI |

### F. Dispatch / Computer Use / Connectors

| Cowork | Taskforce |
|---|---|
| ✅ Dispatch (persistent Triage-Agent) | 🟡 Butler kommt nahe, **keine** Dispatch-UI |
| ✅ Computer Use (Screen-Click/Type, Tiered Permissions) | ❌ (komplett fehlend) |
| ✅ Connector-Browser mit GUI-Setup | 🟡 `/capabilities` ist Read-only, OAuth-Flow nur über `authenticate`-Tool |
| ✅ Plugin-Marketplace | 🟡 Plugin-System existiert, **keine** Marketplace-UI |
| ✅ Slash-Command-Browser via `/` oder `+` Button | ❌ (Skills nur über Backend-API) |

### G. Approvals & Permission Modes

| Cowork | Taskforce |
|---|---|
| ✅ 5 Permission-Modes umschaltbar live | ❌ |
| ✅ Per-Action Approval-Prompt mit Allow/Deny/Allow-for-Session | 🟡 `ask_user` Events tracked, **kein** UI-Modal |
| ✅ App-Permission-Tiers (View/Click/Full) | n/a (kein Computer Use) |

### H. Desktop-App-Verpackung

| Cowork | Taskforce |
|---|---|
| ✅ macOS .dmg, Windows .exe (x64+ARM64) | ❌ (nur Web-Vite-App) |
| ✅ OS-Notifications | ❌ |
| ✅ System-Tray / Auto-Start | ❌ |
| ✅ Custom URL-Scheme (`claude://…`) | ❌ |
| ✅ Auto-Updater | ❌ |
| ✅ Code-Signing / Notarization | ❌ |

---

## 4. Frontend-Roadmap zur Cowork-Parität

Geordnet nach Aufwand × Impact. Jeder Block ist als eigene Epic/PR konzipiert.

### Phase 1 – Chat-Erlebnis auf Cowork-Niveau (1–2 Wochen)

**Ziel:** Was du heute in `/chat` machst, fühlt sich wie Cowork an.

1. **Permission-Mode-Switcher** im Chat-Header (`Ask | Auto-Accept | Plan | Auto | Bypass`). Bindet an einen neuen `agent.permission_mode`-State, der pro Conversation persistiert wird und im Backend in `executor.execute_mission` als Pre-Tool-Hook ausgewertet wird.
2. **Approval-Modal** für `ask_user` und Tool-Approvals: Drei Buttons `Allow once · Allow for session · Deny`. Konsumiert die bereits vorhandenen `ask_user`-Events aus dem SSE-Stream.
3. **Stop-Button** mid-stream → `POST /api/v1/missions/{request_id}/cancel` (existiert bereits).
4. **View-Mode-Toggle** (Normal/Verbose/Summary) → reines Frontend-Filter über `EventType`.
5. **Side-Chat** (`/btw` oder `Cmd+;`): Neue Komponente, die Conversation-Snapshot bis Punkt X kopiert und in einer Drawer-View einen Read-only-Agent startet.
6. **Usage-Ring** im Header: Context-% aus letztem `LLMStreamEventType.done`-Event, Plan-Usage aus `/api/v1/monitoring/usage`.
7. **`/compact` Button**: triggert `agent.context.compress()` über neuen REST-Endpoint.
8. **@mention File-Picker** in Prompt-Box, gefüttert vom Working-Dir des Profils.
9. **Drag-and-Drop** für Bilder/PDFs → `POST /api/v1/files/`.

### Phase 2 – Multi-Session Workspace (2–3 Wochen)

**Ziel:** Parallele Sessions mit Hot-Switch und (für Code-Profile) Git-Worktrees.

1. **Sidebar-Refactor**: aus der Conversations-Liste eine echte Session-Sidebar machen – mit Status-Badges (running/idle/needs-input/done), Filter, Group-by-Project. Hotkeys `Ctrl+N`, `Ctrl+Tab`, `Ctrl+Shift+Tab`.
2. **Split-View**: `Cmd/Ctrl + Click` öffnet eine zweite Session im rechten Pane. Layout-State pro User in localStorage + Server-Settings-Store.
3. **Per-Session Working-Directory** im Profile-Override: neuer Schema-Block `session.working_dir` der bei Conversation-Create gesetzt wird (Backend-Erweiterung in `ConversationManager`).
4. **Worktree-Adapter** (für Code-Profile): neues Modul `infrastructure/git/worktree_manager.py`, das bei Session-Start `git worktree add .taskforce/worktrees/<session_id> -b <prefix>/<session_id>` ausführt. Sidebar bekommt Worktree-Indicator + Archive-Button.
5. **Auto-Archive bei PR-Merge**: subscribe via existierender GitHub-Event-Source, Conversation-Status auf `archived` setzen.

### Phase 3 – Workspace-Panes (Diff, Preview, Terminal, File) (3–4 Wochen)

**Ziel:** Aus dem Chat eine echte IDE-artige Oberfläche machen.

1. **Pane-Engine** einführen (z.B. `react-resizable-panels` oder `dockview`). Layout speichern pro User.
2. **Diff-Pane**: Backend liefert bereits `tool_call`-Events für `edit`/`file_write`. Neuer Komponente `<DiffPane>` mit `react-diff-viewer-continued`, Inline-Kommentar → schickt Kommentar als neue User-Message mit Datei+Line-Kontext.
3. **File-Pane**: Click auf Datei-Pfad im Chat öffnet Read+Edit-View, `Save` schreibt via `POST /api/v1/files/{path}`. Konfliktdetection per `mtime`.
4. **Preview-Pane** (Embedded Browser): `<iframe>` mit Proxy-Konfiguration aus `.taskforce/launch.json`. Reuse `auto-verify`-Idee per Playwright (Browser-Tool ist schon installiert).
5. **Terminal-Pane**: `xterm.js` + WebSocket-Endpoint `ws://…/api/v1/terminals/{session_id}` der eine echte Shell im Session-Working-Dir startet (auf Server-Seite via `pty`). Im Desktop-Mode lokal via Node-PTY (siehe Phase 5).
6. **Tasks-Pane**: Live-View der Sub-Agents einer Session über SSE `/api/v1/runs/{id}/subagents/stream` (Backend-Endpoint neu).

### Phase 4 – PR-Integration & Office-Outputs (1–2 Wochen)

1. **PR-Status-Bar**: GitHub-MCP-Server bzw. `github`-Tool liefert Checks. Bar zeigt `running/passing/failing` mit Auto-Fix/Auto-Merge-Toggles. Auto-Fix nutzt die bereits vorhandene `subscribe_pr_activity`-Logik im Coding-Agent.
2. **"Open PR"-Action**: aus dem Diff-Pane direkt PR erstellen.
3. **Office-Output-Preview**: erzeugte `.xlsx`/`.pptx`/`.docx` aus `tool_result`-Events identifizieren → Thumbnail + "Open externally"-Button. Optional: Inline-Viewer für `.docx` (mammoth.js → HTML) und `.xlsx` (SheetJS).

### Phase 5 – Desktop-App (3–5 Wochen)

**Empfehlung: Tauri 2** (statt Electron). Gründe:
- Bundle-Size ~10–20 MB statt 150 MB
- Rust-Backend kann lokales `git worktree`, lokale Shells, Filesystem-Watcher und MCP-Stdio-Server direkt verwalten ohne separates Python-Backend
- Cross-Platform inkl. ARM64 für Win/Mac (Tauri 2 unterstützt Mobile-Targets als Bonus für späteres Dispatch-Mobile)
- Code-Signing/Notarization out-of-the-box

Schritte:
1. **`apps/desktop/`** Tauri-Projekt anlegen. `ui/`-Build wird als Frontend-Asset gebundelt.
2. **Embedded Backend**: Taskforce-Server (`uvicorn taskforce.api.server:app`) wird als Sidecar-Prozess gestartet. Tauri lifecycle-hooks managen Start/Stop. Port wird automatisch vergeben und via IPC ans Frontend übergeben.
3. **Lokale Filesystem-APIs** über Tauri-Commands: `read_file`, `write_file`, `list_dir`, `open_in_editor` (VS Code / Cursor / Zed via URL-Scheme).
4. **Lokales PTY** für Terminal-Pane via `tauri-plugin-shell` + `pty-rs`.
5. **OS-Notifications** via `tauri-plugin-notification`.
6. **System-Tray**: Quick-Access für laufende Sessions, "Schedule due" Indicator.
7. **Auto-Updater** via `tauri-plugin-updater`, signiert mit Ed25519.
8. **Deep-Links** (`taskforce://session/<id>`) für Dispatch-from-Mobile später.
9. **Code-Signing**: Apple Developer ID + Windows EV Cert. CI-Pipeline in `.github/workflows/desktop-release.yml`.

### Phase 6 – Dispatch & Mobile (4–6 Wochen)

1. **Dispatch-Agent**: neues Profile `dispatch` als Triage-Agent (Butler-Variante), das Tasks empfängt, klassifiziert (Code/Knowledge/ComputerUse) und an entsprechende Sub-Agents weiterleitet. Vorhandener `intent_router` ist die Basis.
2. **Mobile-PWA**: ui/ ist bereits SPA – PWA-Manifest + Service-Worker hinzufügen. Push-Notifications via VAPID + bestehende Gateway-Notification.
3. **Optional native Mobile**: Tauri 2 Mobile-Target nutzt dieselbe UI-Codebasis.

### Phase 7 – Connectors & Plugin-Marketplace (2–3 Wochen)

1. **Connectors-Page** mit OAuth-Setup-Wizard pro Provider (Google/Slack/GitHub/Linear/Notion). Reuse `application/auth_manager.py`.
2. **Plugin-Marketplace**: lokale plus remote Indexe (analog zu Cowork Marketplaces). UI um Install/Uninstall/Enable per Tenant. Backend hat bereits `PluginLoader`.
3. **Skill/Slash-Command-Browser** im Chat-Input (`/` öffnet Popover mit verfügbaren Skills + Args-Preview).

### Phase 8 – Computer Use (Optional, hoher Aufwand)

Wenn du wirklich Feature-Parität willst:
- Native Tauri-Commands für Screen-Capture (per `screenshots-rs`) und Input-Injection (per `enigo`).
- Permission-Tier-System wie bei Cowork (View/Click/Full pro App).
- Vision-Modell-Routing für Screenshot-Analyse (bereits in Multimedia-Tool angelegt).
- Pro-App-Allowlist/Denylist im Settings-Store.

---

## 5. Empfohlene Reihenfolge & Quick Wins

**Sofort umsetzbar (1–2 Tage je)**, hoher UX-Gewinn:

1. Stop-Button im Chat (Backend-Endpoint existiert)
2. View-Mode-Toggle (Normal/Verbose/Summary)
3. `/compact`-Button
4. Permission-Mode-Switcher (UI-only, Hooks im Backend optional nachziehen)
5. Drag-and-Drop für File-Attachments

**Größte Hebel für Cowork-Feeling**:

1. **Phase 2** (Multi-Session-Sidebar + Worktrees) → das ist das prägendste Cowork-Element
2. **Phase 3** (Pane-Engine + Diff/File/Terminal) → macht Taskforce zur echten IDE
3. **Phase 5** (Tauri-Desktop-App) → von hier ab "Open-Source-Cowork" wirklich greifbar

**Was Taskforce schon JETZT besser kann als Cowork** und nicht verloren gehen darf:
- Multi-Provider-LLM-Routing (Cowork ist auf Claude-Modelle festgenagelt)
- ACP-Federation zwischen Agenten
- Multi-Tenant-Override-Hooks
- Eigene Skills/Plugins lokal entwickeln ohne Marketplace-Approval

---

## 6. Architektonische Hinweise

- **Pane-Engine** sollte über alle drei Render-Targets gleich funktionieren (Web, Desktop, Mobile). Empfehlung: `dockview` (kommerzfreundliche Lizenz) – es unterstützt Drag-and-Drop und Persistierung von Layouts out-of-the-box.
- **Backend-Endpoints** brauchen für Phase 3 ein paar gezielte Erweiterungen:
  - `WS /api/v1/terminals/{session_id}` (PTY-Stream)
  - `GET/PUT /api/v1/files/{path}` (mit Session-Working-Dir-Sandbox)
  - `GET /api/v1/runs/{id}/subagents/stream` (SSE der parallelen Sub-Agents)
  - `POST /api/v1/conversations/{id}/compact`
- **Permission-Modes** sollten als neues Concept in `core/domain/agent.py` definiert werden (`PermissionMode` Enum) und vom `ToolExecutor` pre-execution gecheckt werden.
- **Worktree-Manager** gehört in `infrastructure/git/` (neuer Block), Protokoll `WorktreeManagerProtocol` in `core/interfaces/`.

---

## 7. Bottom Line

Taskforce **hat das gesamte agentic Backend** schon: Sub-Agents, Scheduling,
Multi-Channel, Event-Driven Rules, OAuth, MCP, Tools. Was fehlt, ist
**ausschließlich Frontend** und das **Desktop-Wrapping**. In drei Worten:

> **Multi-Session-Sidebar · Pane-Workspace · Tauri-Bundle**

Mit Phase 1+2+5 (≈ 6–8 Wochen Fokusarbeit) ist die Community Edition ein
glaubwürdiges Open-Source-Cowork. Phasen 3+4+6+7 bringen sie auf
Feature-Parität. Phase 8 (Computer Use) ist Kür.

---

**Quellen**:
- [Claude Cowork Product Page](https://claude.com/product/cowork)
- [Claude Code Desktop Docs](https://code.claude.com/docs/en/desktop)
- [Cowork Scheduled Tasks](https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-cowork)
- [Cowork Computer Use](https://support.claude.com/en/articles/14128542-let-claude-use-your-computer-in-cowork)
- [Cowork Dispatch](https://support.claude.com/en/articles/13947068-assign-tasks-from-anywhere-in-cowork)
