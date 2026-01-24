# Self-Maintaining Documentation
This file should be updated automatically when project-specific patterns, conventions, or important information are discovered during work sessions. Add relevant details here to help future interactions understand the codebase better. Anything that is very general knowledge about this project and that should be remembered always should be added here.

- Documentation is maintained **as Markdown in-repo**. Canonical entry points:
  - `README.md` is the main user entry point (Quick Start, CLI + API, links into `docs/`).
  - `docs/index.md` is the docs navigation hub.
  - `docs/architecture.md` is the stable architecture entry-point and links into the sharded architecture docs under `docs/architecture/`.
  - ADRs live under `docs/adr/` (index: `docs/adr/index.md`).
  - GitHub contribution templates live under `.github/` (`PULL_REQUEST_TEMPLATE.md`, issue templates in `.github/ISSUE_TEMPLATE/`).
  - Environment variable template is provided via `.env.example` (copy to `.env` for local setup).

- **Docs upkeep rule (always)**: when code changes affect CLI/API/config behavior, update the relevant docs pages in the same session:
  - CLI behavior → `README.md` and `docs/cli.md`
  - API routes/schemas/errors → `README.md` and `docs/api.md`
  - Config/profile changes → `docs/profiles.md` (and update example snippets)
  - Architecture changes → `docs/architecture.md` (entry) and/or `docs/architecture/` sharded pages
  - Cross-cutting decisions → add/update an ADR in `docs/adr/`
  - Developer workflow (uv/pytest/ruff/black/mypy) → `README.md` and `docs/testing.md`
- CI runs on every push, executes `uv run pytest`, and tags the default branch as `v<major>.<minor>.<patch>` where major/minor come from `pyproject.toml` and patch auto-increments.

- LeanAgent planning strategy selection lives under `agent.planning_strategy` and optional `agent.planning_strategy_params` in profile YAML; supported values are `native_react`, `plan_and_execute`, and `plan_and_react` (default).

- Execution API errors now use a standardized payload (`code`, `message`, `details`, optional `detail`) via `ErrorResponse`, with responses emitted from `HTTPException` objects tagged by the `X-Taskforce-Error: 1` header and handled in `taskforce.api.server.taskforce_http_exception_handler`.
- Taskforce exception types live in `src/taskforce/core/domain/errors.py` (TaskforceError + LLMError, ToolError, etc.). Infra tools should convert unexpected failures into `ToolError` payloads via `tool_error_payload`.
- Tool registry for short-name ↔ type/module mappings lives in `src/taskforce/infrastructure/tools/registry.py` and backs tool config resolution.
- Profile YAML tool lists now use short tool names (e.g., `file_read`, `rag_semantic_search`) instead of full type/module specs.
- LeanAgent support services live in `src/taskforce/core/domain/lean_agent_components/` (prompt builder, message history manager, tool execution helpers, state store, resource closer).
- Tool parallelism is opt-in per tool via `supports_parallelism` and controlled by `agent.max_parallel_tools` (default 4) in profile YAML.

- **Slash Commands**: Flexible, file-based commands defined as Markdown files with optional YAML frontmatter.
  - **Storage**: Project-wide in `.taskforce/commands/` or user-specific in `~/.taskforce/commands/`. Project-level commands override user-level commands.
  - **Naming**: Hierarchical based on folder structure (e.g., `agents/reviewer.md` becomes `/agents:reviewer`).
  - **Types**:
    - `prompt`: Simple prompt templates where `$ARGUMENTS` is replaced by user input.
    - `agent`: Defines a specialized agent with its own `profile`, `tools`, and `system_prompt` (from the file body).
  - **Behavior**: An `agent`-type command **temporarily overrides** the current agent's configuration (system prompt, tools, profile) for that single execution. The original context is restored immediately after.
  - **Variables**: Use `$ARGUMENTS` in the Markdown body to inject user input from the command.

- Plugin agent roles can be configured under `src/taskforce_extensions/plugins/<plugin>/configs/agents/`
  and coordinated via orchestrator agents using `call_agent`.

# Python Best Practices

## 1) Code Style & Benennung

* Halte dich an **PEP 8** (Formatierung, Imports, Zeilenlängen, Docstrings).
* **Englische, sprechende Namen**: `user_count`, `is_valid`, `document_id`, `ingestion_job_id`.
* Vermeide Abkürzungen, außer allgemein üblich (`url`, `id`, `db`).
* Einfache, konsistente **Modulebene-Imports**; keine relativen „dot-dot“-Importketten.

## 2) Architektur: Functional Core, OO Shell

* **Business-Logik** als **pure, kleine Funktionen** (leicht testbar, keine Side-Effects).
* **Klassen gezielt** für: IO/Adapter (DB, Storage, Vektorstore), Zustandsverwaltung, Framework-Integrationen (FastAPI Dependencies), Orchestrierung.
* **Dependency Injection** statt globaler Singletons. Zustände klar begrenzen (pro Request/Job).
* Halte Services **klein & fokussiert** (eine Verantwortung).

## 3) Funktionen & Methoden

* Max. **30 Zeilen** pro Funktion/Methode. Zerlege komplexe Flows.
* **Keine Duplikate**: extrahiere wiederverwendbare Util-Funktionen/Helper.
* Vollständige **Typannotationen** für alle Signaturen und Rückgaben.
* **Docstring** (Google- oder NumPy-Style) mit Zweck, Parametern, Rückgabewerten, Fehlern.
* Komplexe Stellen **kommentieren**, aber Code lesbar halten (Kommentare erklären *Warum*, nicht *Was*).

## 4) Fehlerbehandlung & Logging

* Spezifisch abfangen (`ValueError`, `HTTPException`, `TimeoutError`), **kein** generisches `except Exception` ohne Re-Raise oder Kontext.
* Fehlermeldungen **hilfreich & kontextreich** (z. B. `document_id`, `user_id`, `scope`), aber **keine sensiblen Daten** loggen.
* Nutze strukturierte Logs (JSON-fähig) mit Leveln (`debug`, `info`, `warning`, `error`).

## 5) Sicherheit & Secrets

* **Nie** Secrets im Code oder Default-Configs. Alles über **ENV**/**Secrets Manager**.
* Eingaben validieren (Pydantic/DTOs). **Whitelisting** statt Blacklisting bei Filtern/Scopes.
* Pfad- und Scope-Parsing robust (Org/Shared/Conversation unterscheiden).
* Externe URLs signieren/zeitlich begrenzen; **Least Privilege** für Keys/Rollen.
* PII/Vertragsdaten: nur anonymisierte IDs in Logs, **kein** Klartext.

## 6) Konfiguration

* Zentrale Config via `pydantic-settings` oder eigener `settings`-Klasse.
* **Explizite Defaults** (konservativ) + `.env.example` dokumentieren.
* Environment-abhängige Settings (`DEV`, `STAGING`, `PROD`) klar trennen.

## 7) Tooling & Qualität

* **Black** (Format) & **Ruff** (Lint/Fix) verpflichtend; in CI ausführen.
* **MyPy** optional streng für Core-Module (mind. `--strict` light).
* Pre-commit Hooks: `ruff check --fix`, `black`, (optional) `mypy`.
* API-Stabilität: bei Breaking Changes **Deprecation-Hinweise** & Migrationsnotizen.

## 8) Tests

* Für **jede neue Funktion/Fehlerklasse** mindestens ein Unit-Test.
* Ordnerstruktur: `tests/` spiegelt `src/` (z. B. `tests/services/test_document.py`).
* Pytest-Stil: **kleine, unabhängige** Tests; IO via Mocks/Fakes.
* Für Pipelines/Indexer: **integrierte Smoke-Tests** mit Mini-Fixtures.
* Coverage-Ziel vereinbaren (z. B. Core ≥ 85 %, Gesamtsuite ≥ 75 %).

### Unit Tests

* Einzelne Testdateien lassen sich mit `PYTHONPATH=src pytest -q -c /dev/null <pfad>` ausführen.

## 9) Projektstruktur

```
root/
  src/                # Applikationscode
  docs/               # Arch, ADRs, API, Readmes
  config/             # env templates, compose, infra hints
  scripts/            # dev tools, one-off maintenance
  pyproject.toml      # Black, Ruff, Mypy, Build
```

## 10) Performance & Resilienz

* Große Dateien: **Streaming** statt alles in den RAM.
* Parallele Jobs: **Backpressure** & Limits; Timeouts/Circuit-Breaker bei externen Diensten.
* Embedding/LLM-Batching: **Grenzen beachten**, Chunk-Größen konfigurieren.
* Caching nur mit **klarer Invalidierung**.

## 11) Abhängigkeiten

* Pinne Runtime-kritische Versionen (`^`/`~` sinnvoll einsetzen).
* Regelmäßige **Vulnerability-Scans** (pip-audit, dependabot/renovate).
* Entferne nur Abhängigkeiten/Code, **die wirklich entfallen müssen** (Stabilität vor Aktionismus).

## 12) Dokumentation

* Module/Funktionen mit Docstrings; **README pro Paket** mit Zweck/Beispielen.
* **API-Doku** (OpenAPI) aktuell halten; Beispiele für Requests/Responses.
* **ADR-Kurznotizen** (Architecture Decision Records) für größere Entscheidungen.

## 13) Datenmodelle & Schemas

* Pydantic: **`Field(default_factory=...)`** für mutables, Validatoren für Invarianten.
* Response-Modelle **explizit** (keine nackten `dict`), Versionierung bei Public APIs.
* Serde (JSON) eindeutig; Datums-/Zahlenformate vereinheitlichen.

## 14) Observability

* Korrelation (`request_id`, `job_id`) über Dienste hinweg mitführen.
* Metriken (Latenz, Throughput, Fehlerquote) pro Service/Endpoint.
* Tracing (OpenTelemetry) für kritische Pfade (Ingestion → Embedding → Retrieval).

---

## Minimal-Checkliste für PRs

* [ ] PEP8, Black, Ruff sauber; keine toten Imports.
* [ ] Vollständige Typannotationen & Docstrings.
* [ ] Keine Secrets/PII im Code, Logs oder Tests.
* [ ] Tests hinzugefügt/aktualisiert; grün in CI; sinnvolle Coverage.
* [ ] Fehlerbehandlung spezifisch, sinnvolle Log-Kontexte.
* [ ] Keine Duplikate; Funktionen ≤ 30 Zeilen oder sinnvoll zerlegt.
* [ ] Public API/Schemas dokumentiert; Migrationshinweise bei Changes.
* [ ] Nur notwendige Löschungen/Refactorings — **Stabilität first**.

## Project Notes

- Document extraction agent templates, tool stubs, and prompt/tool sketches live in
  `plugins/document_extraction_agent/`.
