# Butler Role Specialization - Implementation Plan

## Problem

Der Butler ist aktuell ein Alleskönner mit hardcoded Sub-Agents (pc-agent, research_agent, doc-agent, coding_agent), einem festen `BUTLER_SPECIALIST_PROMPT` und einer fixen Tool-Liste. Es gibt keine saubere Möglichkeit, ihn für einen bestimmten Zweck zu konfigurieren (z.B. Buchhalter, IT-Support).

## Design: Role = Overlay YAML

Eine **Butler Role** ist eine separate YAML-Datei, die definiert WAS der Butler ist (Persona, Sub-Agents, Tools), während `butler.yaml` definiert WIE er läuft (Persistence, LLM, Scheduler, Security).

```
butler.yaml (Chassis)      +    accountant.yaml (Rolle)
├── persistence             │    ├── persona_prompt (System-Anweisungen)
├── llm                     │    ├── sub_agents (spezialisierte Agenten)
├── scheduler               │    ├── tools (erlaubte Werkzeuge)
├── security                │    ├── event_sources (optionale Quellen)
├── notifications           │    ├── rules (optionale Trigger-Regeln)
└── context_policy          │    └── mcp_servers (optionale MCP-Server)
                            │
                  ──────────┘
                  = vollständige Butler-Konfiguration
```

### Suchpfade für Rollen-YAMLs
1. `src/taskforce/configs/butler_roles/{name}.yaml` (mitgeliefert)
2. `.taskforce/butler_roles/{name}.yaml` (projekt-lokal)

### Merge-Semantik
- `sub_agents`: **REPLACED** (Rolle definiert komplett)
- `tools`: **REPLACED** (Rolle definiert komplett)
- `event_sources`: **APPENDED** (Basis + Rolle)
- `rules`: **APPENDED** (Basis + Rolle)
- `mcp_servers`: **APPENDED** (Basis + Rolle)
- `system_prompt`: **SET** aus `persona_prompt` der Rolle
- `specialist`: **CLEARED** → `None` (Rolle ersetzt den Specialist-Lookup)

### Backward Compatibility
- Kein `role` in `butler.yaml` → `specialist: butler` + hardcoded Prompt → **exakt wie bisher**
- `role: accountant` → Rolle wird geladen und gemerged → neues Verhalten

---

## Implementierungsschritte

### Step 1: Domain Model — `src/taskforce/core/domain/butler_role.py` (NEU)

Pures frozen Dataclass ohne Dependencies:

```python
@dataclass(frozen=True)
class ButlerRole:
    name: str
    description: str = ""
    persona_prompt: str = ""
    sub_agents: list[dict[str, str]] = field(default_factory=list)
    tools: list[str | dict[str, Any]] = field(default_factory=list)
    event_sources: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    skills_directories: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
```

### Step 2: Role Loader — `src/taskforce/application/butler_role_loader.py` (NEU)

Application-Layer Service:
- `load(role_name: str) -> ButlerRole` — Sucht YAML in Suchpfaden, erstellt ButlerRole
- `merge_into_config(base: dict, role: ButlerRole) -> dict` — Merged Rolle in Butler-Config
- `list_available() -> list[ButlerRole]` — Listet verfügbare Rollen mit Name+Description

### Step 3: Default-Rolle — `src/taskforce/configs/butler_roles/personal_assistant.yaml` (NEU)

Extrahiert den aktuellen `BUTLER_SPECIALIST_PROMPT`-Inhalt und die Sub-Agents/Tools aus `butler.yaml` in eine Rollen-Datei. Nutzt `{{SUB_AGENTS_SECTION}}` Placeholder für dynamische Sub-Agent-Liste.

### Step 4: Beispiel-Rolle — `src/taskforce/configs/butler_roles/accountant.yaml` (NEU)

Buchhalter-Rolle mit:
- Persona-Prompt für Buchhaltung
- Eigene Sub-Agents (doc-agent für Belege, research_agent für Steuerrecht)
- Reduziertes Tool-Set (memory, ask_user, file_read, calendar, schedule)

### Step 5: `butler.yaml` anpassen

Neues optionales Feld `role:` hinzufügen. Kein Default-Wert (= Backward Compat). Kommentar zur Nutzung.

### Step 6: `ButlerDaemon` anpassen — `src/taskforce/api/butler_daemon.py`

- `__init__` bekommt `role: str | None = None` Parameter
- `_load_config()`: Wenn `role` (aus CLI oder YAML), dann `ButlerRoleLoader.load()` + `merge_into_config()`
- Die gemergte Config setzt `system_prompt` + `sub_agents` → der bestehende Factory-Pfad übernimmt

### Step 7: `SystemPromptAssembler` minimal anpassen

Der Assembler unterstützt bereits `custom_prompt` und `{{SUB_AGENTS_SECTION}}`. Einzige Änderung: `{{SUB_AGENTS_SECTION}}` muss auch im `custom_prompt`-Pfad ersetzt werden (aktuell nur im `specialist`-Pfad).

### Step 8: Butler CLI anpassen — `src/taskforce/api/cli/commands/butler.py`

- `taskforce butler start --role accountant` (neuer `--role` Parameter)
- `taskforce butler roles list` — Zeigt verfügbare Rollen
- `taskforce butler roles show <name>` — Zeigt Rollen-Details

### Step 9: Tests

- `tests/unit/core/domain/test_butler_role.py` — ButlerRole Dataclass
- `tests/unit/application/test_butler_role_loader.py` — Laden, Merge, Suchpfade, Fehlerfall

### Step 10: Dokumentation

- `docs/adr/adr-013-butler-role-specialization.md` — ADR
- `docs/features/butler-roles.md` — Feature-Guide
- `docs/adr/index.md` aktualisieren
- `CLAUDE.md` Butler-Sektion aktualisieren

---

## Dateien

### Neu erstellen
- `src/taskforce/core/domain/butler_role.py`
- `src/taskforce/application/butler_role_loader.py`
- `src/taskforce/configs/butler_roles/personal_assistant.yaml`
- `src/taskforce/configs/butler_roles/accountant.yaml`
- `tests/unit/core/domain/test_butler_role.py`
- `tests/unit/application/test_butler_role_loader.py`
- `docs/adr/adr-013-butler-role-specialization.md`
- `docs/features/butler-roles.md`

### Modifizieren
- `src/taskforce/configs/butler.yaml` — `role:` Feld
- `src/taskforce/api/butler_daemon.py` — Role-Loading
- `src/taskforce/application/system_prompt_assembler.py` — `{{SUB_AGENTS_SECTION}}` im custom_prompt-Pfad
- `src/taskforce/api/cli/commands/butler.py` — `--role` + `roles` Subcommand
- `docs/adr/index.md`
- `CLAUDE.md`

### Nicht modifizieren (nutzt bestehende Flows)
- `application/factory.py` — Versteht bereits `system_prompt` + `sub_agents` in Config
- `core/prompts/autonomous_prompts.py` — `BUTLER_SPECIALIST_PROMPT` bleibt als Fallback
