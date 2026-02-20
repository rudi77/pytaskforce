# Epic 21: Vereinheitlichung von Skills und Slash Commands

**Status:** Planned
**ADR:** [ADR-011](../adr/adr-011-unified-skills-system.md)
**Branch:** `claude/unify-commands-skills-D8MmZ`
**Priorität:** Mittel
**Aufwand:** M (Medium) — hauptsächlich Umstrukturierung, kein neues fachliches Konzept

---

## 1. Ziel

Slash Commands und Skills werden zu einem einzigen, kohärenten **Skills-System** zusammengeführt. Slash Commands verschwinden als eigenständiges Konzept. Der Skill-Typ (`context` | `prompt` | `agent`) bestimmt, wie ein Skill aktiviert und ausgeführt wird.

**Vorher:** zwei Systeme, zwei Speicherorte, zwei Protokolle
**Nachher:** ein System, ein Speicherort (`.taskforce/skills/`), ein Protokoll

---

## 2. Story-Übersicht

| Story | Titel | Schicht | Aufwand |
|-------|-------|---------|---------|
| 1 | Domain-Modell erweitern | Core / Domain | S |
| 2 | Protokolle konsolidieren | Core / Interfaces | S |
| 3 | Parser & Loader erweitern | Infrastructure | M |
| 4 | SkillService erweitern | Application | M |
| 5 | Chat-Integration umbauen | API / CLI | M |
| 6 | CLI-Commands zusammenführen | API / CLI | S |
| 7 | Slash-Command-Code löschen | Cross-cutting | S |
| 8 | Tests aktualisieren | Test | M |
| 9 | Dokumentation aktualisieren | Docs | S |

---

## 3. Story 1 — Domain-Modell erweitern

**Schicht:** `core/domain/`
**Dateien:** `enums.py`, `skill.py`

### 3.1 `SkillType`-Enum in `enums.py`

```python
class SkillType(str, Enum):
    CONTEXT = "context"   # Standard: Instruktionen → System-Prompt
    PROMPT  = "prompt"    # Einmal-Prompt mit $ARGUMENTS, direkt via /name aufrufbar
    AGENT   = "agent"     # Temporäre Agent-Konfigurationsübersteuerung, via /name aufrufbar
```

### 3.2 `SkillAgentConfig`-Dataclass in `skill.py`

Neues Dataclass für Agent-Konfigurationsüberschreibung (bisher: `agent_config: dict` in `SlashCommandDefinition`):

```python
@dataclass
class SkillAgentConfig:
    """Agent-Konfiguration für Skills vom Typ AGENT."""
    profile: str | None = None
    tools: list[str] | None = None
    mcp_servers: list[dict[str, Any]] | None = None
    specialist: str | None = None
```

### 3.3 `SkillMetadataModel` und `Skill` erweitern

Neue Felder in `SkillMetadataModel` (und damit auch in `Skill`):

| Feld | Typ | Standard | Beschreibung |
|------|-----|---------|--------------|
| `skill_type` | `SkillType` | `SkillType.CONTEXT` | Ausführungsverhalten |
| `slash_name` | `str \| None` | `None` | Expliziter `/name`, Fallback auf `name` |
| `agent_config` | `SkillAgentConfig \| None` | `None` | Nur für `type: agent` |

### 3.4 Neue Methode `substitute_arguments` auf `Skill`

```python
def substitute_arguments(self, arguments: str) -> str:
    """Ersetzt $ARGUMENTS im instructions-Body.

    Args:
        arguments: Nutzereingabe nach dem Skill-Namen.

    Returns:
        Instruction-Text mit ersetztem $ARGUMENTS-Platzhalter.
    """
    return self.instructions.replace("$ARGUMENTS", arguments)
```

### 3.5 Property `effective_slash_name` auf `Skill`

```python
@property
def effective_slash_name(self) -> str:
    """Gibt den für /name-Aktivierung verwendeten Namen zurück."""
    return self.slash_name or self.name
```

### 3.6 Namensvalidierung anpassen

`validate_skill_name()` muss hierarchische Namen mit `:` als Trennzeichen erlauben:
- Erlaubt: `agents:reviewer`, `tools:python-helper`
- Format: `[a-z0-9-]+(:[ a-z0-9-]+)*`, max 64 Zeichen
- Bestehende Kebab-Case-Validierung für jeden Namensteil beibehalten

---

## 4. Story 2 — Protokolle konsolidieren

**Schicht:** `core/interfaces/`
**Dateien:** `skills.py` (erweitern), `slash_commands.py` (löschen vorbereiten)

### 4.1 `SkillProtocol` in `skills.py` erweitern

Neue Pflicht-Properties im Protokoll:

```python
class SkillProtocol(Protocol):
    # ... bestehende Properties ...

    @property
    def skill_type(self) -> SkillType: ...

    @property
    def slash_name(self) -> str | None: ...

    @property
    def agent_config(self) -> SkillAgentConfig | None: ...

    @property
    def effective_slash_name(self) -> str: ...

    def substitute_arguments(self, arguments: str) -> str: ...
```

### 4.2 `SlashCommandLoaderProtocol` in `slash_commands.py`

Datei bleibt bestehen bis Story 7 (Löschen), wird aber nicht mehr referenziert.

---

## 5. Story 3 — Parser & Loader erweitern

**Schicht:** `infrastructure/skills/`
**Dateien:** `skill_parser.py`, `skill_loader.py`, `skill_registry.py`

### 5.1 `skill_parser.py` — Neue Frontmatter-Felder

`parse_skill_markdown()` und `parse_skill_metadata()` müssen folgende neue Felder lesen:

| YAML-Schlüssel | Python-Feld | Typ | Standardwert |
|----------------|-------------|-----|-------------|
| `type` | `skill_type` | `SkillType` | `SkillType.CONTEXT` |
| `slash-name` | `slash_name` | `str \| None` | `None` |
| `profile` | `agent_config.profile` | `str \| None` | `None` |
| `tools` | `agent_config.tools` | `list[str] \| None` | `None` |
| `mcp_servers` | `agent_config.mcp_servers` | `list[dict] \| None` | `None` |
| `specialist` | `agent_config.specialist` | `str \| None` | `None` |

**Validierungsregeln:**
- `type: agent` erfordert mind. eines von `profile`, `tools`, `mcp_servers`
- `type: prompt` benötigt kein `$ARGUMENTS` im Body (aber Warnung wenn fehlt)
- `type: context` ignoriert `profile`, `tools`, `mcp_servers`, `slash-name`

**Hilfsfunktion `_parse_agent_config()`:**

```python
def _parse_agent_config(frontmatter: dict[str, Any]) -> SkillAgentConfig | None:
    """Extrahiert Agent-Konfiguration aus Frontmatter (nur für type: agent)."""
    has_config = any(
        frontmatter.get(k) for k in ("profile", "tools", "mcp_servers", "specialist")
    )
    if not has_config:
        return None
    return SkillAgentConfig(
        profile=frontmatter.get("profile"),
        tools=frontmatter.get("tools"),
        mcp_servers=frontmatter.get("mcp_servers"),
        specialist=frontmatter.get("specialist"),
    )
```

### 5.2 `skill_loader.py` — Hierarchische Skill-Namen

Aktuell: Skill-Name aus `SKILL.md`-Frontmatter, Verzeichnisname nur zur Validierung.

**Neu:** Hierarchische Namen aus Unterverzeichnispfad ableiten (als Ergänzung zur Validierung).

Die Methode `_derive_hierarchical_name(skill_dir: Path, base_dir: Path) -> str` berechnet den Namen aus dem relativen Pfad:
- `base_dir/.../agents/reviewer/` → `agents:reviewer`
- `base_dir/.../pdf-processing/` → `pdf-processing`

Diese Ableitung dient **nur zur Aufnahme in die Discovery**. Der kanonische Name bleibt der im `SKILL.md`-Frontmatter definierte `name`. Bei Nichtübereinstimmung wird eine Warnung geloggt (kein Fehler, um bestehende Skills nicht zu brechen).

### 5.3 `skill_registry.py` — Lookup via `slash_name`

Neuer Index `_slash_name_index: dict[str, str]` (slash_name → canonical_name):

```python
def get_skill_by_slash_name(self, slash_name: str) -> SkillProtocol | None:
    """Findet Skill anhand seines slash_name (für /name-Aktivierung)."""
    canonical = self._slash_name_index.get(slash_name)
    if canonical:
        return self.get_skill(canonical)
    # Fallback: direkter Namensabgleich
    return self.get_skill(slash_name)

def list_slash_command_skills(self) -> list[str]:
    """Gibt Namen aller Skills zurück, die via /name aktivierbar sind."""
    return [
        meta.name
        for meta in self.get_all_metadata()
        if meta.skill_type in (SkillType.PROMPT, SkillType.AGENT)
    ]
```

---

## 6. Story 4 — SkillService erweitern

**Schicht:** `application/`
**Dateien:** `skill_service.py`

### 6.1 Neue Methode: `resolve_slash_command()`

```python
def resolve_slash_command(
    self, command_input: str
) -> tuple[SkillProtocol | None, str]:
    """Löst einen /command-Eingabestring in Skill + Argumente auf.

    Args:
        command_input: Raw input starting with "/" (e.g. "/code-review def foo(): pass")

    Returns:
        Tuple (skill, arguments). Skill ist None wenn kein passender Skill gefunden.

    Raises:
        ValueError: Wenn command_input nicht mit "/" beginnt.
    """
    if not command_input.startswith("/"):
        raise ValueError(f"Expected command starting with '/': {command_input!r}")

    stripped = command_input.lstrip("/")
    parts = stripped.split(maxsplit=1)
    slash_name = parts[0].lower()
    arguments = parts[1] if len(parts) > 1 else ""

    # Versuche hierarchischen Namen: "/agents reviewer" → "agents:reviewer"
    skill = self._registry.get_skill_by_slash_name(slash_name)
    return skill, arguments
```

### 6.2 Neue Methode: `prepare_skill_prompt()`

```python
def prepare_skill_prompt(self, skill: SkillProtocol, arguments: str) -> str:
    """Bereitet den Prompt für einen PROMPT-Skill vor (ersetzt $ARGUMENTS).

    Args:
        skill: Ein Skill mit type=PROMPT.
        arguments: Nutzereingabe nach dem Skill-Namen.

    Returns:
        Finaler Prompt-Text.

    Raises:
        ValueError: Wenn skill.skill_type != SkillType.PROMPT.
    """
    if skill.skill_type != SkillType.PROMPT:
        raise ValueError(f"Skill {skill.name!r} is not of type PROMPT")
    return skill.substitute_arguments(arguments)
```

### 6.3 Neue Methode: `list_slash_command_skills()`

```python
def list_slash_command_skills(self) -> list[SkillMetadata]:
    """Gibt Metadaten aller via /name aufrufbaren Skills zurück."""
    return [
        meta
        for meta in self._registry.get_all_metadata()
        if meta.skill_type in (SkillType.PROMPT, SkillType.AGENT)
    ]
```

### 6.4 `SkillManager` — Keine Änderungen erforderlich

`SkillManager` für agentinterne Skill-Verwaltung (Intent-Routing, automatisches Switching) bleibt unverändert. Die neuen Skill-Typen werden transparent unterstützt, da der Manager nur `activate_skill()` und `enhance_prompt()` nutzt.

---

## 7. Story 5 — Chat-Integration umbauen

**Schicht:** `api/cli/`
**Dateien:** `simple_chat.py`

### 7.1 `SlashCommandRegistry` durch `SkillService` ersetzen

**Vorher:**
```python
# simple_chat.py
from taskforce.application.slash_command_registry import SlashCommandRegistry
# ...
self.command_registry = SlashCommandRegistry()
```

**Nachher:**
```python
# simple_chat.py
from taskforce.application.skill_service import get_skill_service
# ...
self.skill_service = get_skill_service(...)
```

### 7.2 `_handle_command()` umschreiben

Der Handler unterscheidet zwischen Built-in-Commands und Skill-basierten Commands:

```python
async def _handle_command(self, message: str) -> bool:
    """Verarbeitet /command-Eingaben.

    Reihenfolge:
    1. Built-in-Commands (help, clear, exit, debug, ...)
    2. Prompt/Agent-Skills (type: prompt oder type: agent)
    3. Context-Skills via /activate (explizite Aktivierung)
    4. Plugin-Wechsel
    5. Unbekannt → Fehlermeldung
    """
    parts = message.lstrip("/").split(maxsplit=1)
    cmd_name = parts[0].lower()
    arguments = parts[1] if len(parts) > 1 else ""

    # 1. Built-ins
    if cmd_name in BUILTIN_COMMANDS:
        return await self._handle_builtin(cmd_name, arguments)

    # 2. Skill-basierte Commands (type: prompt oder type: agent)
    skill, args = self.skill_service.resolve_slash_command(message)
    if skill and skill.skill_type == SkillType.PROMPT:
        prompt = self.skill_service.prepare_skill_prompt(skill, args)
        await self._handle_chat_message(prompt)
        return False
    if skill and skill.skill_type == SkillType.AGENT:
        await self._execute_agent_skill(skill, args)
        return False

    # 3. Context-Skill direkt aktivieren
    if skill and skill.skill_type == SkillType.CONTEXT:
        self.skill_service.activate_skill(skill.name)
        self._print_system(f"Skill '{skill.name}' aktiviert.", style="success")
        return False

    # 4. Plugin-Wechsel
    if await self._try_switch_plugin(cmd_name):
        return False

    self._print_system(f"Unbekannter Befehl: /{cmd_name}", style="warning")
    return False
```

### 7.3 `_execute_agent_skill()` — Neuer privater Handler

Ersetzt `_execute_custom_command()` für Agent-type Commands:

```python
async def _execute_agent_skill(self, skill: SkillProtocol, arguments: str) -> None:
    """Führt einen AGENT-Skill aus: erzeugt temporären Agent und verarbeitet Prompt."""
    agent_config = skill.agent_config or SkillAgentConfig()
    agent = await self._create_agent_for_skill(agent_config)
    prompt = skill.substitute_arguments(arguments) if "$ARGUMENTS" in skill.instructions else arguments
    await self._handle_chat_message(prompt, agent_override=agent)
```

### 7.4 `/skills`-Built-in anpassen

Die Built-in `/skills`-Liste zeigt Skills gruppiert nach Typ:

```
📚 Skills (3 context, 2 prompt, 1 agent)

KONTEXT-SKILLS (via activate_skill-Tool oder Intent):
  • pdf-processing       – Extrahiert Text und Tabellen aus PDFs
  • smart-booking-auto   – Automatische Buchungsvorschläge

PROMPT-COMMANDS (direkt via /name aufrufbar):
  • code-review          – /code-review <code>
  • translate            – /translate <text>

AGENT-COMMANDS (temporäre Agent-Übersteuerung):
  • python-expert        – /python-expert <aufgabe>
```

### 7.5 `/commands`-Built-in entfernen

Der Built-in-Command `/commands` wird gelöscht. Die Skill-Liste via `/skills` zeigt alle aufrufbaren Einheiten.

---

## 8. Story 6 — CLI-Commands zusammenführen

**Schicht:** `api/cli/commands/`
**Dateien:** `skills.py` (erweitern), `commands.py` (löschen), `main.py` (anpassen)

### 8.1 `skills.py` — Neue Subcommands

`taskforce skills` bekommt neue/geänderte Subcommands:

| Alter Command | Neuer Command | Änderung |
|---------------|---------------|---------|
| `taskforce commands list` | `taskforce skills list --type prompt,agent` | Filter nach Typ |
| `taskforce commands show <name>` | `taskforce skills show <name>` | Zeigt auch `type`, `slash-name` |
| `taskforce commands paths` | `taskforce skills paths` | Zeigt `.taskforce/skills/` |
| `taskforce skills list` | `taskforce skills list` | Jetzt mit `--type`-Filter |

```bash
# Alle aufrufbaren Slash-artigen Skills anzeigen
taskforce skills list --type prompt,agent

# Alle Skills aller Typen
taskforce skills list

# Mit Typ-Spalte in der Ausgabe
taskforce skills list --verbose
```

### 8.2 `main.py` — `commands`-Subcommand entfernen

```python
# Entfernen:
from taskforce.api.cli.commands.commands import commands_app
app.add_typer(commands_app, name="commands")
```

---

## 9. Story 7 — Slash-Command-Code löschen

**Zu löschende Dateien:**

| Datei | Begründung |
|-------|-----------|
| `src/taskforce/core/interfaces/slash_commands.py` | Ersetzt durch erweiterte `skills.py` |
| `src/taskforce/infrastructure/slash_commands/command_loader.py` | Ersetzt durch `SkillLoader` |
| `src/taskforce/infrastructure/slash_commands/command_parser.py` | Ersetzt durch `skill_parser.py` |
| `src/taskforce/infrastructure/slash_commands/__init__.py` | Verzeichnis entfällt |
| `src/taskforce/application/slash_command_registry.py` | Ersetzt durch `SkillService` |
| `src/taskforce/api/cli/commands/commands.py` | Ersetzt durch erweiterte `skills.py` |

**Zu bereinigende Referenzen:**

| Datei | Referenz | Aktion |
|-------|----------|--------|
| `src/taskforce/application/command_loader_service.py` | Slash-Command-Loader | Import und Aufruf entfernen |
| `src/taskforce/api/cli/main.py` | `commands_app` | Import + `add_typer()` entfernen |
| `src/taskforce/api/cli/simple_chat.py` | `SlashCommandRegistry` | Durch `SkillService` ersetzt (Story 5) |
| `pyproject.toml` | Keine Änderung erwartet | Prüfen ob Entry-Points betroffen |

**Zu aktualisierende Imports:**

Nach dem Löschen: Grep-Lauf über die gesamte Codebase nach `slash_command` und `SlashCommand`:

```bash
grep -r "slash_command\|SlashCommand\|command_loader\|CommandType" src/ tests/ --include="*.py"
```

---

## 10. Story 8 — Tests aktualisieren

### 10.1 Zu löschende Tests

| Datei | Begründung |
|-------|-----------|
| `tests/unit/application/test_slash_command_registry.py` | Registry wird gelöscht |
| `tests/unit/infrastructure/slash_commands/` (falls vorhanden) | Loader/Parser werden gelöscht |

### 10.2 Zu erweiternde Tests

**`tests/unit/core/domain/test_skill.py`** — Neue Fälle:
```python
def test_skill_type_defaults_to_context() -> None: ...
def test_skill_with_type_prompt_has_substitute_arguments() -> None: ...
def test_skill_substitute_arguments_replaces_placeholder() -> None: ...
def test_skill_agent_config_is_none_for_context_type() -> None: ...
def test_skill_name_validation_allows_colon_separator() -> None: ...
def test_skill_effective_slash_name_falls_back_to_name() -> None: ...
```

**`tests/unit/infrastructure/skills/test_skill_parser.py`** — Neue Fälle:
```python
def test_parse_prompt_type_skill() -> None: ...
def test_parse_agent_type_skill_with_tools() -> None: ...
def test_parse_agent_config_from_frontmatter() -> None: ...
def test_parse_slash_name_field() -> None: ...
def test_parse_hierarchical_skill_name() -> None: ...
```

**`tests/unit/application/test_skill_service.py`** — Neue Fälle:
```python
async def test_resolve_slash_command_finds_prompt_skill() -> None: ...
async def test_resolve_slash_command_returns_none_for_context_skill() -> None: ...
async def test_resolve_slash_command_extracts_arguments() -> None: ...
async def test_prepare_skill_prompt_substitutes_arguments() -> None: ...
async def test_list_slash_command_skills_filters_by_type() -> None: ...
```

**`tests/unit/api/cli/test_simple_chat.py`** — Neue Fälle:
```python
async def test_handle_command_dispatches_prompt_skill() -> None: ...
async def test_handle_command_dispatches_agent_skill() -> None: ...
async def test_handle_command_activates_context_skill() -> None: ...
async def test_handle_command_unknown_shows_warning() -> None: ...
```

### 10.3 Migrationstests

Ein Integrationstest prüft das End-to-End-Szenario:

**`tests/integration/test_unified_skills_flow.py`**:
```python
async def test_prompt_skill_invoked_via_slash_command(tmp_path) -> None:
    """Prompt-Skill via /name args wird korrekt ausgeführt."""
    # Setup: Skill in tmp_path anlegen
    # SkillService initialisieren
    # resolve_slash_command() aufrufen
    # prepare_skill_prompt() prüfen
    ...
```

---

## 11. Story 9 — Dokumentation aktualisieren

### 11.1 `docs/slash-commands.md` → löschen oder ersetzen

Inhalt in `docs/features/skills.md` integrieren. Eine Redirect-Seite ist nicht nötig (Backward Compatibility nicht gefordert).

### 11.2 `docs/features/skills.md` erweitern

Neue Abschnitte:
- **Skill-Typen:** `context`, `prompt`, `agent` mit Beispielen
- **Slash-Aktivierung:** `/skill-name args`-Syntax
- **Agent-Konfiguration in Skills:** `profile`, `tools`, `mcp_servers`
- **Hierarchische Benennung:** Unterverzeichnisstruktur
- **Migrationsleitfaden:** Commands → Skills

### 11.3 `CLAUDE.md` aktualisieren

Abschnitt "Skills, Slash Commands, and Plugins":
- Slash-Commands-Unterabschnitt entfernen
- Skills-Abschnitt um Typen und Chat-Aktivierung erweitern
- `docs/slash-commands.md` aus der Tabelle entfernen

### 11.4 `docs/adr/index.md` aktualisieren

ADR-011 eintragen.

### 11.5 `README.md` prüfen

Auf Verweise auf Slash Commands prüfen und aktualisieren.

---

## 12. Implementierungsreihenfolge

Die Stories müssen in folgender Abhängigkeitsreihenfolge implementiert werden:

```
Story 1 (Domain-Modell)
    ↓
Story 2 (Protokolle)
    ↓
Story 3 (Parser & Loader)
    ↓
Story 4 (SkillService)     Story 8 (Tests — parallel möglich ab hier)
    ↓
Story 5 (Chat)    Story 6 (CLI)
    ↓
Story 7 (Löschen — erst nach Story 5+6)
    ↓
Story 9 (Dokumentation)
```

---

## 13. Migrations-Anleitung für Nutzer

Bestehende `.taskforce/commands/`-Dateien müssen in `.taskforce/skills/` überführt werden.

### Prompt-Command → Prompt-Skill

**Alt:** `.taskforce/commands/code-review.md`
```markdown
---
description: Überprüft Code
type: prompt
---

Überprüfe diesen Code: $ARGUMENTS
```

**Neu:** `.taskforce/skills/code-review/SKILL.md`
```markdown
---
name: code-review
description: Überprüft Code
type: prompt
---

Überprüfe diesen Code: $ARGUMENTS
```

### Agent-Command → Agent-Skill

**Alt:** `.taskforce/commands/agents/python-expert.md`
```markdown
---
description: Python-Experte
type: agent
profile: dev
tools: [python, file_read, web_search]
---

Du bist ein Python-Experte.
```

**Neu:** `.taskforce/skills/agents/python-expert/SKILL.md`
```markdown
---
name: agents:python-expert
description: Python-Experte
type: agent
profile: dev
tools:
  - python
  - file_read
  - web_search
---

Du bist ein Python-Experte.
```

---

## 14. Offene Fragen

| Frage | Empfehlung |
|-------|-----------|
| Soll `/activate skill-name` als Built-in erhalten bleiben? | Ja — Context-Skills brauchen eine explizite Chat-Aktivierungsmöglichkeit |
| Soll `taskforce commands` einen Deprecation-Hinweis bekommen statt sofort gelöscht zu werden? | Nein — Backward Compatibility ist nicht gefordert |
| Sollen Skills in Unterverzeichnissen automatisch gruppiert in der CLI-Liste erscheinen? | Ja — nach erstem `:` gruppieren |
| Was passiert mit `command_loader_service.py` wenn keine Slash Commands mehr geladen werden? | Datei prüfen — ggf. umbenennen oder entfernen wenn Slash-Command-Ladung der einzige Zweck war |
