---
name: create-role
type: prompt
description: Interaktiv eine neue Butler-Rolle erstellen. Verwende /create-role <Beschreibung> um den Assistenten zu starten, z.B. /create-role IT-Support für Helpdesk-Anfragen
---

# Butler-Rolle erstellen

Der Benutzer möchte eine neue Butler-Rolle erstellen. Die Beschreibung lautet:

**$ARGUMENTS**

## Deine Aufgabe

Führe den Benutzer durch die Erstellung einer neuen Butler-Rolle. Erstelle am Ende eine vollständige YAML-Datei.

## Schritt 1: Anforderungen klären

Frage den Benutzer (mit `ask_user`) nach folgenden Informationen, sofern sie nicht bereits aus der Beschreibung hervorgehen:

1. **Name** der Rolle (kurz, lowercase, z.B. `accountant`, `it_support`, `project_manager`)
2. **Sprache** — In welcher Sprache soll der Butler antworten?
3. **Kernaufgaben** — Was sind die 3-5 wichtigsten Aufgaben?
4. **Fachregeln** — Gibt es fachspezifische Regeln oder Standards? (z.B. SKR03/04 für Buchhaltung, ITIL für IT-Support)
5. **Benötigte Sub-Agents** — Welche Spezialisten braucht die Rolle? Zur Auswahl stehen:
   - `pc-agent` — Lokale Datei-/Systemoperationen, Dokumentverarbeitung (PDF, Office, Extraktion, Klassifikation)
   - `research_agent` — Web-Recherche, Faktenprüfung
   - `coding_agent` — Code schreiben, testen, reviewen
   - Oder eigene Sub-Agents (erfordern separate Config in `configs/custom/`)

## Schritt 2: Persona-Prompt generieren

Erstelle einen klaren, strukturierten Persona-Prompt für die Rolle. Der Prompt muss enthalten:

- **Identität** — Wer ist der Butler? (1-2 Sätze)
- **Kernregeln** — Was tut er, was nicht?
- **Specialist routing** — Muss den Placeholder `{{SUB_AGENTS_SECTION}}` enthalten
- **Arbeitsweise** — Schritt-für-Schritt-Workflow für typische Aufgaben
- **Ausgabeformat** — Wie sollen Ergebnisse formatiert sein?

## Schritt 3: Tool-Auswahl

Wähle die passenden Tools aus dem verfügbaren Set:

| Tool | Zweck |
|------|-------|
| `memory` | Langzeit-Wissen speichern/abrufen |
| `send_notification` | Benachrichtigungen senden |
| `ask_user` | Rückfragen an den Benutzer |
| `activate_skill` | Skills aktivieren |
| `calendar` | Kalender lesen/schreiben |
| `schedule` | Jobs planen (cron/interval) |
| `reminder` | Erinnerungen setzen |
| `rule_manager` | Trigger-Regeln verwalten |
| `gmail` | E-Mail lesen/senden |
| `google_drive` | Google Drive Dateien |
| `file_read` | Lokale Dateien lesen |
| `file_write` | Lokale Dateien schreiben |

Standard-Tools die fast jede Rolle braucht: `memory`, `ask_user`, `send_notification`, `activate_skill`

## Schritt 4: YAML generieren

Erstelle die fertige YAML-Datei mit exakt dieser Struktur:

```yaml
# Butler Role: {Rollenname}
#
# {Kurzbeschreibung}

name: {name}
description: "{Beschreibung}"

persona_prompt: |
  # {Titel}

  {Identität und Kernregeln}

  ## Specialist routing

  {{SUB_AGENTS_SECTION}}

  ## Arbeitsweise

  {Workflow-Schritte}

  ## Ausgabeformat

  {Format-Regeln}

sub_agents:
  - specialist: {agent1}
    description: "{Beschreibung1}"

tools:
  - memory
  - ask_user
  - {weitere tools}
  - type: parallel_agent
    profile: butler
    max_concurrency: 2
```

## Schritt 5: Datei speichern

Speichere die YAML-Datei mit dem `file_write`-Tool nach:

`.taskforce/butler_roles/{name}.yaml`

Bestätige dem Benutzer, dass die Rolle erstellt wurde und erkläre, wie sie aktiviert wird:

```
taskforce butler start --role {name}
```

## Wichtige Regeln

- Der `persona_prompt` muss IMMER `{{SUB_AGENTS_SECTION}}` enthalten (mit doppelten geschweiften Klammern)
- Tools als einfache Strings (Short Names), außer `parallel_agent` das ein Dict ist
- Sub-Agent-Descriptions sollten klar abgrenzen, wofür der Agent zuständig ist
- Der Prompt soll in der Sprache sein, die der Benutzer bevorzugt
