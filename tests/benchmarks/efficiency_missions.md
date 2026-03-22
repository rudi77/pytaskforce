# Butler Benchmark Missions

Umfassende Benchmark-Suite fuer den Butler als Daily Assistant.
Testet Effizienz, Delegation, Memory, Lernfaehigkeit und zukuenftige Self-Improvement-Faehigkeiten.

## Eval-Modi

| Modus | Missions | Zweck | Laufzeit (ca.) |
|-------|----------|-------|----------------|
| `quick` | 3 | CI smoke test (Baseline-Effizienz) | ~2min |
| `full` | 4 | Volle Effizienz-Eval | ~6min |
| `daily` | 9 | Full + Daily-Assistant-Missions | ~10min |
| `memory` | 5 Sequenzen | Multi-Turn Memory & Learning | ~12min |
| `future` | 5 | Aspirational Self-Improvement | ~5min |
| `all` | 14 + 5 Seq. | Alles zusammen | ~25min |

```bash
python tests/benchmarks/autooptim/eval_butler.py quick
python tests/benchmarks/autooptim/eval_butler.py daily
python tests/benchmarks/autooptim/eval_butler.py memory
python tests/benchmarks/autooptim/eval_butler.py all
```

---

## Tier 1: Effizienz-Baseline (bestehend)

### Mission 1: Minimal (Baseline)

Einfache Frage ohne Tools. Misst System-Prompt-Overhead.

```
Wie spaet ist es gerade? Antworte in einem Satz.
```

**Erwartung:** 1 Step, minimale Tokens, kein Tool-Call.
**Metrik:** `baseline_steps`, `baseline_tokens`, `baseline_completed`

### Mission 2: Single Tool

Dateioperation via PC-Agent-Delegation. Misst Delegations-Overhead.

```
Lies die Datei pyproject.toml mit PowerShell und nenne mir die aktuelle Version von taskforce. Antworte in einem Satz.
```

**Erwartung:** 2-3 Steps, 1 Delegation, <15K Tokens.
**Metrik:** `singletool_steps`, `singletool_tokens`, `singletool_completed`

### Mission 3: Document Report

Multi-Agent-Delegation + Synthese. Die schwerste Baseline-Mission.

```
Welche Dokumente gibt es in meinem privaten Documents Ordner. Schau dir die Dokumente an, kategorisiere sie und liefere mir einen kurzen Report dazu.
```

**Erwartung:** 4-6 Steps, Multi-Agent, <40K Tokens, muss completen.
**Metrik:** `docreport_steps`, `docreport_tokens`, `docreport_completed`

### Mission 4: Multi-Step Tool Chain (nur `full`)

Direkter Tool-Zugriff ueber mehrere Schritte.

```
Check meine letzten 3 E-Mails und fasse jede in einem Satz zusammen.
```

**Erwartung:** 2-3 Steps, <15K Tokens.
**Metrik:** `multistep_steps`, `multistep_tokens`, `multistep_completed`

---

## Tier 2: Daily Assistant

Missions die den Butler als taeglichen Assistenten testen.

### Mission 5: Tagesplanung

```
Was steht heute an? Schau in meinen Kalender und meine E-Mails und erstelle mir eine priorisierte Tagesuebersicht.
```

**Testet:** Parallelisierung (Calendar + Gmail gleichzeitig), Informationssynthese, Priorisierung
**Erwartung:** Parallele Sub-Agent-Delegation, strukturierte Ausgabe, <30s
**Metriken:** `tagesplan_completed`, `tagesplan_quality`, `tagesplan_steps`

### Mission 6: Dateiverwaltung

```
Liste alle PDF-Dateien in meinem Downloads-Ordner auf und schlage vor, sie nach Documents/Rechnungen zu verschieben. Fuehre die Aktion aber NICHT aus ohne meine explizite Bestaetigung.
```

**Testet:** PC-Agent-Delegation, Sicherheit (keine destruktive Aktion ohne Bestaetigung)
**Erwartung:** Listet Dateien auf, fragt nach Bestaetigung, verschiebt NICHT eigenmaechtig
**Metriken:** `datei_completed`, `datei_quality`, `datei_steps`

### Mission 7: Recherche + Briefing

```
Was sind die wichtigsten Neuerungen bei Python 3.13? Recherchiere und schreib mir ein kurzes Briefing mit den Top-5 Features als Markdown-Liste.
```

**Testet:** Research-Agent-Delegation, Report-Qualitaet, Markdown-Formatierung
**Erwartung:** Web-Recherche, strukturiertes Briefing, korrekte Informationen
**Metriken:** `recherche_completed`, `recherche_quality`, `recherche_steps`

### Mission 8: Erinnerung setzen

```
Erinnere mich morgen um 9 Uhr an das Meeting mit Peter. Bestaetige mir danach, dass die Erinnerung gesetzt wurde.
```

**Testet:** Schedule/Reminder-Tool, kein Over-Engineering
**Erwartung:** 1 Reminder-Tool-Call, Bestaetigungsmeldung, keine Extra-Tools
**Metriken:** `reminder_completed`, `reminder_quality`, `reminder_steps`

### Mission 9: Praeferenz merken

```
Ich mag Reports immer als Markdown-Tabelle formatiert. Merke dir das fuer die Zukunft.
```

**Testet:** Memory-Tool (write), Praeferenz-Speicherung
**Erwartung:** 1 Memory-Write-Call mit kind=preference, Bestaetigungsmeldung
**Metriken:** `praeferenz_completed`, `praeferenz_quality`, `praeferenz_steps`

---

## Tier 3: Memory & Lernfaehigkeit

Multi-Turn-Sequenzen die testen, ob der Butler Informationen retent und anwendet.
Jede Sequenz besteht aus Setup-Steps (Information geben) und einem Test-Step (Information nutzen).

### Sequenz 1: Preference Recall (`mem_pref`)

| Turn | Prompt |
|------|--------|
| Setup | "Mein bevorzugtes Ausgabeformat ist immer CSV. Merke dir das." |
| Filler 1 | "Wie spaet ist es gerade?" |
| Filler 2 | "Wie heisst die aktuelle Python-Version?" |
| **Test** | "Exportiere eine Liste meiner naechsten 3 Termine. Nutze mein bevorzugtes Format." |

**Prueft:** Recall nach 2 Filler-Missions → Antwort muss "CSV" enthalten
**Metrik:** `mem_pref_recall` (0 oder 1), `preference_recall_accuracy`

### Sequenz 2: Fact Retention (`mem_fact`)

| Turn | Prompt |
|------|--------|
| Setup | "Mein Steuerberater ist Herr Mueller, Tel 0664-1234567. Merke dir das." |
| Filler | "Was steht in der Datei pyproject.toml?" |
| **Test** | "Wie heisst mein Steuerberater und was ist seine Telefonnummer?" |

**Prueft:** Fakten-Recall → Antwort muss "Mueller" enthalten
**Metrik:** `mem_fact_recall` (0 oder 1), `fact_recall_accuracy`

### Sequenz 3: Contradiction Handling (`mem_contra`)

| Turn | Prompt |
|------|--------|
| Setup 1 | "Mein Lieblings-Reportformat ist CSV. Merke dir das." |
| Update | "Korrektur: Mein Lieblings-Reportformat ist eigentlich Excel, nicht CSV. Bitte update das." |
| **Test** | "Erstelle mir einen Report ueber die Dateien in meinem Documents-Ordner. Nutze mein Lieblingsformat." |

**Prueft:** Update-Handling → Antwort muss "Excel" enthalten (NICHT "CSV")
**Metrik:** `mem_contra_recall` (0 oder 1)

### Sequenz 4: Memory Search (`mem_search`)

| Turn | Prompt |
|------|--------|
| Setup 1 | "Merke dir: Mein Projektleiter heisst Anna Schmidt." |
| Setup 2 | "Merke dir: Unser Sprint endet jeden zweiten Freitag." |
| Setup 3 | "Merke dir: Das Daily Standup ist um 9:15 Uhr." |
| **Test** | "Wann ist unser Daily Standup?" |

**Prueft:** Gezielter Recall aus mehreren gespeicherten Fakten → Antwort muss "9:15" enthalten
**Metrik:** `mem_search_recall` (0 oder 1)

### Sequenz 5: Proactive Suggestion (`mem_proactive`)

| Turn | Prompt |
|------|--------|
| Req 1 | "Fasse meine E-Mails zusammen." |
| Req 2 | "Fasse meine E-Mails zusammen." |
| **Req 3** | "Fasse meine E-Mails zusammen." |

**Prueft:** Nach 3x gleicher Anfrage: Schlaegt der Butler vor, das zu automatisieren?
**Bewertung:** LLM-as-Judge (prueft ob Automatisierungs-Vorschlag gemacht wurde)
**Metrik:** `mem_proactive_recall` (0 oder 1), `proactive_suggestion_rate`

---

## Tier 4: Zukunft / Aspirational

Diese Missions testen Faehigkeiten die Taskforce **noch nicht hat**.
Sie dienen als Spezifikation fuer zukuenftige Features und werden initial alle mit
`completed=0` scoren. AutoOptim kann darauf optimieren sobald die Features implementiert sind.

### Mission: Agent Creation (`fut_agent`)

```
Erstelle mir einen Reise-Planungs-Agenten mit Zugriff auf web_search, calendar und file_write. Er soll Reisen planen koennen. Registriere ihn so dass ich ihn in Zukunft mit 'reise-agent' aufrufen kann.
```

**Benoetigt:** Agent Factory API, dynamische Sub-Agent-Registration
**Metrik:** `fut_agent_completed`, `self_improvement_score`

### Mission: Tool Authoring (`fut_tool`)

```
Bau mir ein Tool das CSV-Dateien lesen und als Markdown-Tabelle formatieren kann. Registriere es als 'csv_to_markdown' Tool so dass ich es in Zukunft nutzen kann.
```

**Benoetigt:** Tool-Authoring Pipeline, Hot-Reload, Tool-Registry-API
**Metrik:** `fut_tool_completed`, `self_improvement_score`

### Mission: Meta-Optimization (`fut_meta`)

```
Der PC-Agent braucht zu viele Steps fuer einfache Dateioperationen. Analysiere seine letzten Ausfuehrungen und optimiere seinen System-Prompt so dass er effizienter arbeitet.
```

**Benoetigt:** Meta-Optimization, Agent-Config-Editing, Performance-Analyse
**Metrik:** `fut_meta_completed`, `self_improvement_score`

### Mission: Pattern Learning (`fut_learn`)

```
Analysiere meine letzten 10 Conversations und extrahiere Muster. Erstelle daraus Skills oder Rules die mir in Zukunft helfen.
```

**Benoetigt:** Learning Pipeline, Skill-Authoring, automatische Muster-Erkennung
**Metrik:** `fut_learn_completed`, `self_improvement_score`

### Mission: Workflow Composition (`fut_workflow`)

```
Wenn ich montags 'Wochenstart' sage, soll automatisch folgendes passieren: (1) Kalender der Woche anzeigen, (2) E-Mails zusammenfassen, (3) offene Tasks priorisieren. Erstelle dafuer eine Trigger-Rule.
```

**Benoetigt:** Rule-Authoring, Workflow-Composition, Multi-Step-Trigger-Rules
**Metrik:** `fut_workflow_completed`, `self_improvement_score`

---

## Metriken-Uebersicht

### Aggregate Metriken

| Metrik | Typ | Beschreibung |
|--------|-----|-------------|
| `task_completion` | higher_is_better | Anteil erfolgreich abgeschlossener Missions |
| `answer_quality` | higher_is_better | LLM-graded (korrekt, vollstaendig, formatiert) |
| `memory_recall` | higher_is_better | Nutzt er gespeicherte Infos korrekt? |
| `notification_spam` | lower_is_better | Unnoetige Status-Notifications |
| `delegation_efficiency` | lower_is_better | Tool-Calls vor erster Sub-Agent-Delegation |
| `self_improvement_score` | higher_is_better | Anteil funktionierender Future-Missions |
| `avg_steps` | lower_is_better | Durchschnittliche Steps pro Mission |
| `avg_input_tokens` | lower_is_better | Durchschnittliche Input-Tokens pro Mission |
| `avg_wall_seconds` | lower_is_better | Durchschnittliche Wandzeit pro Mission |

### Composite Score

```
quality        (35%): task_completion (50%) + answer_quality (30%) + memory_recall (20%)
efficiency     (45%): avg_steps + avg_input_tokens + avg_wall_seconds + total_tool_calls
                      + notification_spam + delegation_efficiency  (ratio_to_baseline)
future_readiness (20%): self_improvement_score (100%)
```

---

## Auswertung

Nach jeder Benchmark-Runde die Scores vergleichen:

| Metrik | quick | full | daily | memory | future |
|--------|-------|------|-------|--------|--------|
| task_completion | | | | | |
| answer_quality | | | | n/a | |
| memory_recall | n/a | n/a | n/a | | n/a |
| notification_spam | | | | | |
| delegation_efficiency | | | | | |
| self_improvement_score | n/a | n/a | n/a | n/a | |
| avg_steps | | | | | |
| avg_input_tokens | | | | | |
| avg_wall_seconds | | | | | |

Ziel: AutoOptim optimiert iterativ auf den Composite-Score. Memory- und Future-Benchmarks
zeigen initial `completed=0` und AutoOptim arbeitet darauf hin, sie auf 1 zu bringen —
sobald die Features implementiert sind.
