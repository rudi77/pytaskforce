# Agent Efficiency Benchmark Missions

Drei Missions zum Messen und Optimieren der Token-Effizienz.
Jeweils mit `taskforce run mission "..." --profile dev` ausfuehren und Token Analytics vergleichen.

---

## Mission 1: Minimal (Baseline)

Einfache Aufgabe, die in 1-2 Steps loesbar sein sollte. Misst den Overhead
des System-Prompts und der ReAct-Loop-Initialisierung.

```
Lies die Datei pyproject.toml und nenne mir die aktuelle Version von taskforce sowie die Python-Mindestversion. Antworte in genau zwei Zeilen.
```

**Erwartung:** 1 Tool-Call (file_read), 1 Final-Answer. Wenig Tokens.
**Optimierungsziel:** Minimaler Prompt-Overhead, kein unnoetig grosser System-Prompt.

---

## Mission 2: Multi-Step Tool Chain

Aufgabe mit 3-5 Steps und verschiedenen Tools. Misst den Kontext-Aufbau
ueber mehrere Schritte und ob der Agent direkt zum Ziel kommt.

```
Finde alle Python-Dateien unter src/taskforce/core/domain/ die das Wort "dataclass" importieren. Zaehle wie viele es sind und liste fuer jede Datei den Dateinamen und die Anzahl der darin definierten Dataclasses auf. Gib das Ergebnis als Markdown-Tabelle aus.
```

**Erwartung:** 1 Search/Grep, dann mehrere file_read Calls, 1 Final-Answer.
**Optimierungsziel:** Agent sollte grep statt einzelne file_read nutzen,
keine Dateien doppelt lesen, keine unnoetige Planung.

---

## Mission 3: Reasoning-Heavy (Analyse + Synthese)

Aufgabe die echtes Reasoning erfordert und prueft ob der Agent effizient
Informationen zusammenfuehrt statt redundant nachzulesen.

```
Vergleiche die drei Planning-Strategien native_react, plan_and_execute und spar anhand des Quellcodes in src/taskforce/core/domain/planning_strategy.py. Fuer jede Strategie: (1) wie viele LLM-Calls pro Durchlauf minimal noetig sind, (2) welche Phase-Hints sie emittiert, (3) ob sie Reflection nutzt. Fasse das Ergebnis in einer kompakten Vergleichstabelle zusammen.
```

**Erwartung:** 1-2 file_read (planning_strategy.py ist gross, evtl. 2 Reads),
dann Analyse und Synthese im Final-Answer.
**Optimierungsziel:** Agent sollte die Datei einmal komplett lesen statt
stueckweise, und die Analyse im Kopf machen statt unnoetige Tool-Calls.

---

## Auswertung

Nach jeder Mission die Token Analytics vergleichen:

| Metrik | Mission 1 | Mission 2 | Mission 3 |
|--------|-----------|-----------|-----------|
| Steps | | | |
| Total In | | | |
| Total Out | | | |
| Tool Calls | | | |
| Latency | | | |
| In/Out Ratio | | | |

Ziel: Bei Optimierungen (System-Prompt, Context-Policy, Compression) diese
drei Missions erneut laufen lassen und die Werte vergleichen.
