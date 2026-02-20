# ADR 011: Slash Commands als Subset von Skills — Vereinheitlichtes Skills-System

## Status

Proposed

## Kontext

Taskforce hat zwei separate Systeme für dateibasierte, nutzerdefinierte Agentenerweiterungen:

### Slash Commands (`SlashCommandDefinition`)
- **Speicherort:** `.taskforce/commands/*.md` oder `~/.taskforce/commands/*.md`
- **Format:** Flache Markdown-Datei mit optionalem YAML-Frontmatter
- **Aktivierung:** Benutzer tippt `/command args` im Chat
- **Typen:** `prompt` (Template mit `$ARGUMENTS`), `agent` (überschreibt Agent-Konfiguration)
- **Hierarchie:** Unterverzeichnisse ergeben `:` separierte Namen (`agents/reviewer.md` → `/agents:reviewer`)
- **Keine Ressourcendateien**, kein Workflow-Support

### Skills (`Skill`)
- **Speicherort:** `.taskforce/skills/<name>/SKILL.md` oder `~/.taskforce/skills/`
- **Format:** Verzeichnis mit `SKILL.md` + optionalen Ressourcen
- **Aktivierung:** Via `activate_skill`-Tool (LLM-intern), Intent-Routing, oder `/skills` (Listing)
- **Typ:** Immer "context" — Instruktionen werden ins System-Prompt injiziert
- **Hierarchie:** Flache Namen (Kebab-Case)
- **Unterstützt:** Ressourcendateien, deterministische Workflows

### Das Problem

Beide Systeme teilen dieselbe Grundidee: dateibasierte, nutzerdefinierte Konfigurationen, die das Agentenverhalten erweitern. Sie überlappen konzeptuell:
- Slash Commands vom Typ `agent` sind im Wesentlichen Skills, die den Agenten temporär umkonfigurieren
- Slash Commands vom Typ `prompt` sind Skills mit direktem Prompt-Template
- Skills hätten genausogut via `/name` aktivierbar sein können

Die Parallelstruktur erzeugt unnötigen Overhead:
- Zwei Parser, zwei Loader, zwei Registries, zwei Protokolle
- Zwei CLI-Subcommands (`taskforce commands *` vs. `taskforce skills *`)
- Zwei Speicherorte mit leicht unterschiedlichem Format
- Mentale Hürde für Nutzer: "Wann nutze ich ein Command, wann ein Skill?"

## Entscheidung

**Slash Commands werden abgeschafft. Skills übernehmen alle Funktionen.**

Das bestehende Skills-System wird erweitert, sodass:

1. **Skills können direkt via `/skill-name args` im Chat aufgerufen werden** (opt-in via `type: prompt` oder `type: agent`)
2. **Skills unterstützen `$ARGUMENTS`-Substitution** (bisher nur in Slash Commands)
3. **Skills unterstützen Agent-Konfigurationsübersteuerung** (profile, tools, mcp_servers)
4. **Skills unterstützen hierarchische Namen** via Unterverzeichnisstruktur
5. **Ein einziger Speicherort:** `.taskforce/skills/`

### Neues Unified Skill-Format

Skills erhalten einen `type`-Parameter im Frontmatter:

| Type | Bisheriges Äquivalent | Verhalten |
|------|----------------------|-----------|
| `context` (Standard) | Skill (bisherig) | Instruktionen werden ins System-Prompt injiziert. Aktivierung via `activate_skill`-Tool oder Intent-Routing. |
| `prompt` | Slash Command `type: prompt` | Direkt via `/name args` aufrufbar. `$ARGUMENTS` im Body wird ersetzt. Einmaliger Prompt. |
| `agent` | Slash Command `type: agent` | Direkt via `/name args` aufrufbar. Überschreibt Agent-Konfiguration temporär. |

### Neues Unified SKILL.md Format

```markdown
---
name: code-review             # Pflicht: kebab-case, unterstützt auch "namespace:name"
description: Überprüft Code   # Pflicht
type: prompt                  # Optional: context (Standard) | prompt | agent

# Für type: prompt und type: agent — direkte Chat-Aktivierung via /name:
slash-name: review            # Optional: Überschreibt den /name (Standard = name)

# Nur für type: agent:
profile: dev                  # Optional: Basis-Profil
tools:                        # Optional: Tool-Liste
  - python
  - file_read
  - web_search
mcp_servers: []               # Optional: MCP-Server
specialist: null              # Optional

# Bestehende Skill-Felder (unverändert):
allowed-tools: python file_read
license: MIT
compatibility: taskforce >= 1.0
metadata:
  category: development
workflow:
  steps:
    - tool: python
---

Überprüfe diesen Code auf Bugs und Qualitätsprobleme:

$ARGUMENTS

Fokus auf:
- Potenzielle Bugs
- Performance
- Lesbarkeit
```

### Hierarchische Skill-Benennung

Skills können in Unterverzeichnissen organisiert werden. Der Skill-Name wird aus dem relativen Pfad abgeleitet:

```
.taskforce/skills/
├── pdf-processing/             # Skill: "pdf-processing"
│   ├── SKILL.md
│   └── scripts/extract.py
├── agents/                     # Gruppierungsverzeichnis (kein SKILL.md)
│   ├── reviewer/               # Skill: "agents:reviewer"
│   │   └── SKILL.md
│   └── python-expert/          # Skill: "agents:python-expert"
│       └── SKILL.md
└── code-review/                # Skill: "code-review" (type: prompt)
    └── SKILL.md
```

Chat-Aktivierung:
- `/code-review "def foo(): pass"` → Skill `code-review` mit `type: prompt`
- `/agents:reviewer file.py` → Skill `agents:reviewer` mit `type: agent`
- `/agents reviewer file.py` → Alternative Syntax (Leerzeichen statt `:`)

## Konsequenzen

### Positiv

- **Reduktion der Codebasis:** ~5 Dateien werden gelöscht (command_loader, command_parser, slash_command_registry, SlashCommandLoaderProtocol, commands CLI)
- **Einheitliches mentales Modell:** Ein Konzept (Skills) deckt alle Use Cases ab
- **Erweiterbarkeit:** Prompt- und Agent-Skills profitieren automatisch von allen zukünftigen Skill-Features (Ressourcen, Workflows, Intent-Routing)
- **Konsistenter Speicherort:** `.taskforce/skills/` für alles
- **Hierarchie natürlich:** Unterverzeichnisstruktur statt künstlichem `:` in Dateinamen

### Negativ / Risiken

- **Kein Upgrade-Pfad** (explizite Entscheidung gegen Backward Compatibility): Bestehende `.taskforce/commands/`-Dateien müssen manuell migriert werden
- **Skill-Namensvalidierung** muss `:` für hierarchische Namen zulassen
- **Mehr Felder im SKILL.md** — Format wird komplexer, aber durch Optionalität und gute Dokumentation handhabbar

## Alternativen erwogen

### Alternative A: Slash Commands bleiben, Skills werden um `/`-Aktivierung ergänzt
Abgelehnt: Löst das Kernproblem nicht (zwei parallele Systeme).

### Alternative B: Flache `.md`-Dateien als Skill-Format akzeptieren (neben Verzeichnissen)
Abgelehnt: Erhöht die Komplexität des Loaders. Directory-basierte Skills bleiben die einzige kanonische Form.

### Alternative C: Slash Commands werden Plugins
Abgelehnt: Zu schwerfällig. Skills sind die leichtgewichtige Erweiterungseinheit.

## Verwandte Entscheidungen

- [ADR-002](adr-002-clean-architecture-layers.md): Vier-Schichten-Architektur (bleibt erhalten)
- [ADR-007](adr-007-unified-memory-service.md): Unified Memory (ähnlicher Vereinheitlichungsgedanke)
