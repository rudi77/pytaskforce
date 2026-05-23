# Code Review 2026-05-23 — Follow-Up Backlog

**Source:** Repo-weiter Code Review vom 2026-05-23 (siehe Commits
`2e4566d..f38a354` auf Branch `claude/code-review-architecture-qhM1q`).
**Last verified:** 2026-05-23 (Unit-Suite 3673/3673 grün; 1 pre-existing
shell-tool failure auf HEAD unrelated zu diesen Änderungen).
**Status legend:** ☐ open · ☑ done · ⊘ explicitly out of scope

Dieses Dokument trackt die Findings aus dem Code Review, die in der
Session vom 2026-05-23 **nicht** behoben wurden — entweder weil sie
Multi-Session-Refactors sind oder weil wir bewusst pausiert haben.
Geschlossene Items haben einen Commit-Hash und werden nach 30 Tagen
aus diesem Dokument in den Architecture-Changelog überführt.

---

## Erledigt in dieser Session (zur Referenz)

| Commit | Finding |
|--------|---------|
| `2e4566d` | P1 Race in `FileExperienceStore` — per-session Lock + `atomic_write_text` |
| `b800ebc` | P0/P1 Perf — `EncryptedTokenStore` Fernet-Key-Erzeugung off-event-loop |
| `c70c87e` | P1 Silent-Fail — `FileJobStore` quarantänet korrupte Job-Files |
| `0ab5c7a` | P1 Silent-Fail — `FileToolResultStore` quarantänet korrupte Result-Files |
| `78ead0b` | **P0 Architektur** — `core/domain/lean_agent.py` importiert kein Application mehr (Approval-Provider per DI) |
| `fdb0324` | P2 DoS — `POST /api/v1/events/{source_name}` Pydantic-Validierung |
| `c0c1554` | P2 DoS — `DELETE /api/v1/oauth/connections/{provider}` Pydantic-Validierung |
| `6b5a628` | P2 Smell — Magic Strings → Enums in `streaming_renderer` + `run` CLI |
| `95425bf` | P1 Silent-Fail — `IMAPEmailEventSource` narrow excepts |
| `cf26a48` | P1 Silent-Fail — `TelegramOutboundSender` narrow excepts in Markdown-Konverter |
| `f38a354` | P2 Cleanup — `PollingEventSource` als async Context-Manager |

---

## Offene Items

### Mittelgroß (je 30–90 Min, isoliert)

#### ☐ F1 — `FileConversationStore` Index-Double-Read

**Where:** `src/taskforce/infrastructure/persistence/file_conversation_store.py:120–137` (`append_message`), `:187–227` (`list_active/archived`).

**Problem:** `append_message()` liest `index.json` **zweimal pro Call** (load + Re-Read für Metadata-Update). `list_active/archived` parst + sortiert den Index bei jedem Aufruf neu. Bei einer Session mit 200 Turns × 50 aktiven Conversations summiert sich das spürbar.

**Target:** In-Memory-Index mit `mtime`/Version-Check; flush nur bei Schreibvorgang. Vorhandenes `replace_messages()` (Zeile 139) wird in `append_message` aktuell nicht aufgerufen — eventuell konsolidieren.

**Touches:** `file_conversation_store.py`, `tests/unit/infrastructure/persistence/test_file_conversation_store*.py`.

**Acceptance:** Profil-Lauf mit `py-spy record` über 200-Turn-Session — `_save_index` Calls halbiert. Concurrent-Test mit `asyncio.gather`(50× `append_message`) ohne Lost-Updates.

---

#### ☐ F2 — `SkillService` mtime-Scan pro Request

**Where:** `src/taskforce/application/skill_service.py:121–158` (`_max_skill_mtime_ns`), `:179` (`refresh_dynamic_skill_dirs`).

**Problem:** Bei jedem CLI- oder API-Aufruf wird `rglob("*.md")` über alle registrierten Skill-Verzeichnisse ausgeführt — O(n) Stat-Calls pro Request. Bei 500 .md-Files spürbar.

**Target:** mtime-Cache für 10–30 s, oder Re-Scan nur wenn `_skill_dir_provider` sich geändert hat. `watchdog` ist bereits Core-Dep und könnte hier andocken.

**Touches:** `skill_service.py`, `tests/unit/application/test_skill_service.py`.

**Acceptance:** Mikrobenchmark mit 500 .md-Files — Cold-Run unverändert, Warm-Run < 1 ms.

---

#### ☐ F3 — DI-Smell: `WikiTool` instanziiert `FileWikiStore` inline

**Where:** `src/taskforce/infrastructure/tools/native/wiki_tool.py:113–114`.

**Problem:** `WikiTool.__init__()` instanziiert `FileWikiStore`, wenn kein Store passed wird. Infrastructure-Klasse trifft also konkrete Store-Wahl statt nur das Protokoll entgegenzunehmen. Verhindert Multi-Tenant-Override-Tests.

**Target:** Store muss immer per DI reingereicht werden. Factory baut `FileWikiStore` und passed in.

**Touches:** `wiki_tool.py`, `application/tool_builder.py`, `tests/unit/infrastructure/tools/test_wiki_tool*.py`.

**Acceptance:** `WikiTool(...)` ohne `wiki_store=` raised `ValueError` / `TypeError`. Alle bestehenden Tests passieren explizit einen Store rein.

---

#### ☐ F4 — DI-Smell: `gateway_registry._load_bot_configs_from_settings` instanziiert `FileSettingsStore`

**Where:** `src/taskforce/infrastructure/communication/gateway_registry.py:106–107`.

**Problem:** Inline-Instanziierung statt Injection. Wichtig wegen Multi-Tenant-Override-Hook (`set_settings_store_override`) — aktuell wird der Override nicht respektiert.

**Target:** Settings-Store als Dependency reingereicht; nimmt den Override-Hook korrekt mit.

**Touches:** `gateway_registry.py`, `application/infrastructure_builder.py`.

**Acceptance:** Test mit gesetztem Override-Hook — der Override wird tatsächlich konsultiert.

---

#### ☐ F5 — Atomic-Write-Pattern vereinheitlichen

**Where:** Alle `File*Store`-Klassen unter `infrastructure/persistence/`, `infrastructure/scheduler/`, `infrastructure/memory/`.

**Problem:** `core/utils/atomic_io.py::atomic_write_text` ist der kanonische Helper. Migration läuft, aber `FileConversationStore._write_json` (Zeile 360–368) hat noch sein eigenes temp-file-rename-Pattern. (`FileExperienceStore` wurde im aktuellen Review bereits migriert.)

**Target:** Alle Stores auf `atomic_write_text` umstellen; Custom-Patterns entfernen.

**Touches:** `file_conversation_store.py` und ggf. weitere Stellen via `git grep "tempfile.*replace"`.

**Acceptance:** `git grep "tempfile.NamedTemporaryFile.*replace"` außer in `atomic_io.py` → 0 Treffer.

---

### Groß (Multi-Session, mehrere Stunden, viele Files)

#### ☐ F6 — 9 Infrastructure → Application Imports (Service-Locator-Anti-Pattern)

**Where:** Folgende Dateien importieren Lookups aus `application.infrastructure_overrides` bzw. `application.*_registry`:

| Datei:Zeile | Ziel |
|---|---|
| `infrastructure/tools/native/schedule_tool.py:157` | `application.infrastructure_overrides::get_current_tenant_id` |
| `infrastructure/tools/native/shell_tool.py:21` | `application.infrastructure_overrides::get_sandboxed_executor` |
| `infrastructure/tools/registry.py:260` | `application.agent_plugin_registry` |
| `infrastructure/tools/orchestration/parallel_agent_tool.py:231` | `application.infrastructure_overrides` |
| `infrastructure/acp/peer_registry.py:10` | `application.infrastructure_overrides::get_current_tenant_id` |
| `infrastructure/acp/runtime.py:108` | `application.infrastructure_overrides::get_cross_tenant_acp_authorizer` |
| `infrastructure/llm/token_analytics_callback.py:169,183` | `application.token_ledger`, `application.run_registry` |
| `infrastructure/persistence/plugin_scanner.py:41` | `application.plugin_loader` |
| `infrastructure/event_sources/__init__.py:14` | `application.event_source_registry` |

**Problem:** Layer-Direktive sagt: Infrastructure darf nur Core kennen. Aktuell hängt Infrastructure direkt am Application-Service-Locator. Erschwert Plugin- und Test-Isolation.

**Target:** Jede dieser Lookup-Funktionen bekommt ein Protokoll in `core/interfaces/runtime_lookups/` (oder ähnlich). Application registriert konkrete Implementations; Infrastructure-Klassen nehmen das Protokoll per Konstruktor-DI. Selbes Muster wie der P0-Fix in Commit `78ead0b` für `ApprovalServiceProvider`.

**Touches:** ~9 Infrastructure-Files + ~9 Konstruktor-Signaturen + jeweils Factory-Wiring in `infrastructure_builder.py` + Test-Stubs.

**Acceptance:** `rg "from taskforce\.application" src/taskforce/infrastructure/` → 0 Treffer.

---

#### ☐ F7 — `application/factory.py` (1659 LOC) splitten

**Where:** `src/taskforce/application/factory.py` — gesamtes File.

**Problem:** God-Object: mischt DI-Wiring, Profile-Loading, Tool-Assembly, MCP-Setup, Infrastructure-Building. Vier Methoden über 100 LOC:

| Methode | LOC |
|---|---|
| `_load_framework_defaults` (Z. 1075) | 307 |
| `_instantiate_agent` (Z. 575) | 163 |
| `_build_definition_from_config` (Z. 867) | 130 |
| `_apply_extensions` (Z. 256) | 125 |

**Target:**
- `_load_framework_defaults` aufteilen in `_load_default_tools`, `_load_default_skills`, `_load_default_planning`, …
- `_apply_extensions` raus in eigene Klasse `FactoryExtensionDispatcher`.
- `_instantiate_agent` — Builder-Pattern (Agent hat 22 Konstruktor-Args).
- Bestehende `infrastructure_builder.py` (819 LOC) und `agent_creation_pipeline.py` (17 LOC — leeres Shim!) als Zielort nutzen.

**Touches:** `factory.py`, `infrastructure_builder.py`, `agent_creation_pipeline.py`, neue Module, **dutzende Tests**.

**Acceptance:** Kein File > 800 LOC; keine Methode > 50 LOC; `factory.py` ≤ 400 LOC; `agent_creation_pipeline.py` entweder voll genutzt oder gelöscht.

**Empfehlung:** Eigener Branch + PR. Inkrementell migrieren, jede Extraktion ein Commit + grüner Test-Lauf.

---

#### ☐ F8 — `application/gateway.py` (1595 LOC) splitten

**Where:** `src/taskforce/application/gateway.py`.

**Problem:** God-Object für die `CommunicationGateway`. Drei monströse Methoden:

| Methode | LOC |
|---|---|
| `_resolve_conversation_manager` (Z. 361) | **512** |
| `_trim_history` (Z. 1105) | 394 |
| `_maybe_append_footer` (Z. 925) | 180 |

**Target:**
- `_resolve_conversation_manager`: Strategy-Klassen pro Manager-Typ (File / DB / Gateway). Eigene Module unter `application/conversation_managers/`.
- `_trim_history`: nach `core/domain/conversation_compressor.py`.
- `_maybe_append_footer`: nach `application/message_footer_builder.py`.

**Touches:** `gateway.py`, neue Module, **dutzende Tests**.

**Acceptance:** Kein File > 800 LOC; keine Methode > 50 LOC.

**Empfehlung:** Eigener Branch + PR. Wie F7 inkrementell.

---

#### ☐ F9 — 10 lange Methoden refactoren (Rest)

**Where:** Nicht in F7/F8 abgedeckt:

| Datei:Zeile | Methode | LOC |
|---|---|---|
| `api/cli/simple_chat.py:730` | `_ensure_agent_skill_manager` | 284 |
| `api/cli/simple_chat.py:475` | `skill_service` (Property!) | 173 |
| `api/cli/simple_chat.py:269` | `_setup_scheduler` | 125 |

**Problem:** `simple_chat.py` (1434 LOC) ist die dritte God-Object-Datei. Drei Methoden weit über CLAUDE.md's 30-LOC-Limit. Property mit 173 LOC ist besonders riskant — als Property ist sie unsichtbar im Stack.

**Target:**
- `_ensure_agent_skill_manager` → `SkillDiscoveryService` in `application/`.
- `skill_service` Property → entweder eager init im Konstruktor oder explizite `_ensure_skill_service()`-Methode.
- `_setup_scheduler` → `SchedulerBuilder` in `application/`.

**Touches:** `simple_chat.py`, neue Module, CLI-Tests.

**Acceptance:** Keine Methode/Property > 50 LOC; `simple_chat.py` ≤ 800 LOC.

---

### Klein / niedrige Priorität (P2-P3, je < 30 Min)

#### ☐ F10 — Application → API Imports in `agent_daemon.py`

**Where:** `src/taskforce/application/agent_daemon.py:139,178,191,201,481,562`.

**Problem:** 6 Imports aus `taskforce.api.dependencies`, jeweils in `try/except` versteckt. Funktional ok ("wenn API embedded, sonst skippen"), formal die strengste Layer-Verletzung der Hexagonal-Direktive.

**Target:** Callback-Protokoll im Daemon; API registriert sich beim Start. Vermutlich am elegantesten zusammen mit F7 zu lösen.

**Touches:** `agent_daemon.py`, `api/server.py` lifespan, `core/interfaces/api_callback.py` (neu).

---

#### ☐ F11 — Drei-Schichten-Wiring `factory → infrastructure_builder → agent_creation_pipeline`

**Where:** `application/factory.py`, `application/infrastructure_builder.py`, `application/agent_creation_pipeline.py`.

**Problem:** Drei Lagen Indirection mit Logik-Duplikat. `agent_creation_pipeline.py` ist 17 LOC praktisch leer. Sowohl `factory._build_infrastructure()` als auch `infrastructure_builder.build_*()` bauen State-Manager / LLM / Context-Policy.

**Target:** Pipeline-Layer entweder konsequent füllen oder ersatzlos streichen. Hängt am Ausgang von F7.

---

#### ☐ F12 — Registry-Klassen ohne gemeinsamen Vertrag

**Where:** `AgentRegistry`, `ToolRegistry`, `EventSourceRegistry`, `AgentPluginRegistry`, `AgentRuntimeRegistry`, `RunRegistry` in `application/`.

**Problem:** Jede Registry hat eigenen `get`/`list`/`register`-Stil. Kein gemeinsamer Protokoll-Contract.

**Target:** Optional `RegistryProtocol[T]` in `core/interfaces/registry.py`. Nur lohnt sich wenn jemand sie generisch konsumieren will — sonst YAGNI.

---

#### ☐ F13 — `tool_registry.py` / `tool_builder.py` / `tool_resolver.py`-Trio

**Where:** drei Module unter `application/`.

**Problem:** Verantwortlichkeiten überlappen (Mapping, Build, Resolve). Performance-Agent hat keine harte Duplikation gefunden, aber Trennung verschwimmt in der Praxis.

**Target:** Lese-Tag durch alle drei mit der Frage "Würde ein neuer Beitragender beim ersten Kontakt diese Trennung verstehen?". Wenn nicht, konsolidieren.

---

#### ☐ F14 — Restliche Magic Strings → Enums

**Where:** `src/taskforce/core/domain/context_builder.py:287-293` — Plan-Step-Status (`"completed"`, `"pending"`, `"in_progress"`).

**Problem:** Diese Strings beschreiben **Plan-Steps**, nicht `ExecutionStatus`. `"in_progress"` existiert in keinem Enum. Brauchen entweder neues `PlanStepStatus`-Enum oder die Plan-Steps modellieren überhaupt typed.

**Target:** Entscheidung: eigenes Enum oder dataclass für Plan-Steps. Aktuelle String-Konvention bleibt bewusst bis dahin.

---

#### ☐ F15 — Restliche `list_active/archived` re-parse

**Where:** `file_conversation_store.py:187–227`.

**Problem:** Bei jedem List-Call wird `index.json` neu geparst + sortiert.

**Target:** Fällt mit F1 (Index-Cache) automatisch weg.

---

#### ⊘ F16 — `time.sleep(0.5)` in `cli/src/taskforce_cli/commands/up.py:44`

**Status:** Out of scope — läuft im ThreadPool-Thread (nicht event-loop-blockierend). Stilistisch suboptimal, aber kein realer Schaden. Migrieren wenn die Funktion ohnehin async-isiert wird.

---

## CLAUDE.md-Anpassungen?

**Empfehlung: aktuell nicht nötig.** Die Fixes dieser Session enforcen
existierende Regeln (Layer-Disziplin, no-silent-failures, atomic
writes) — sie ändern keine Konventionen, die CLAUDE.md beschreibt.

**Optional erwähnenswert** (low priority, eigener Commit wenn jemand Zeit hat):

* Im "Persistence Adapter"-Recipe einen Verweis auf das **Quarantäne-Pattern**:
  Bei korrupten Persisted-Files niemals silent `None` zurückgeben — Datei
  via `path.rename(path.with_name(f"{path.name}.corrupt-{int(time.time())}"))`
  wegrücken, ERROR loggen. Referenz: `FileJobStore._quarantine` und
  `FileToolResultStore._quarantine`.
* Im "Layer Import Matrix"-Kapitel einen Verweis auf das
  **Provider-Injection-Pattern für tenant-globale Lookups**: statt
  `from taskforce.application.infrastructure_overrides import get_xxx`
  in Core/Infrastructure direkt aufzurufen, Provider als
  `Callable[[], T]` per Konstruktor injizieren. Referenz: Commit
  `78ead0b` für `ApprovalServiceProvider`.

Wer F6 angeht, sollte diese beiden Patterns auf jeden Fall in CLAUDE.md
übernehmen, weil F6 das gleiche Muster großflächig anwendet.

---

**Reviewed by:** Claude Code (Opus 4.7)
**Original review:** Chat-Output 2026-05-23
**Branch:** `claude/code-review-architecture-qhM1q`
