# Epic 5: Minimal-JSON Architecture Refactoring - Brownfield Enhancement

<!-- Powered by BMAD™ Core -->

## Epic Goal

Stabilisierung des ReAct-Loops durch radikale Reduktion der JSON-Oberfläche: JSON wird **nur noch für Tool-Calls** verwendet, während Planungslisten und User-Antworten als natürlicher Text/Markdown verarbeitet werden. Dies eliminiert die häufigen JSON-Parse-Fehler und verhindert, dass rohes JSON als User-Output erscheint.

---

## Epic Description

### Existing System Context

- **Current relevant functionality**: Der Agent führt einen ReAct-Loop aus, bei dem `_generate_thought()` vom LLM ein komplexes JSON-Objekt erwartet (step_ref, rationale, action, expected_outcome, confidence). Bei Parse-Fehlern wird `raw_content` als Fallback-Summary an den User durchgereicht.
- **Technology stack**: Python 3.11, OpenAI API mit `response_format={"type": "json_object"}`, Clean Architecture
- **Integration points**: 
  - `taskforce/src/taskforce/core/domain/agent.py` – `_generate_thought()`, Fallback-Logik
  - `taskforce/src/taskforce/core/domain/events.py` – `ActionType`, `Action`, `Thought` Dataclasses
  - `taskforce/src/taskforce/core/prompts/autonomous_prompts.py` – Schema-Definitionen im Kernel-Prompt
  - `taskforce/src/taskforce/core/domain/plan.py` – `PlanGenerator` (optional: Markdown-Plan statt JSON)

### Enhancement Details

**Was geändert wird:**

1. **Fallback-Entschärfung**: Niemals `raw_content` als User-Summary verwenden. Stattdessen generische Fehlermeldung + Retry-Logik.

2. **Thought-Schema Vereinfachung**: Das JSON-Schema wird auf die minimal notwendigen Felder reduziert:
   ```json
   {
     "action": "tool_call" | "respond" | "ask_user",
     "tool": "tool_name",
     "tool_input": {...},
     "question": "...",
     "answer_key": "..."
   }
   ```
   - Entfernt: `rationale`, `expected_outcome`, `confidence`, `step_ref`
   - `summary` wird NICHT mehr im Thought-JSON erzwungen

3. **Zwei-Phasen-Response für User-Antworten**: 
   - Phase 1: Minimales Action-JSON (Steuerlogik)
   - Phase 2: Bei `action: "respond"` → separater LLM-Call **ohne** JSON-Zwang für natürliche Markdown-Antwort

4. **Prompt-Konsistenz**: Einheitliches Vokabular für Action-Typen zwischen Kernel-Prompt und Code.

**Wie es integriert wird:**
- Inkrementelle Änderung innerhalb des bestehenden ReAct-Loops
- Backward-compatible durch Feature-Flag oder schrittweises Rollout
- Keine API/CLI-Breaking Changes

**Success criteria:**
- Keine rohen JSON-Outputs mehr an User sichtbar
- JSON-Parse-Fehler reduziert um >80% (messbar via Logs)
- Thought-Schema hat maximal 4-5 Top-Level-Felder
- Alle bestehenden Tests passieren

---

## Stories

### Story 1: Fallback-Entschärfung und Retry-Logik

**Beschreibung**: Implementiere sichere Fallback-Behandlung bei JSON-Parse-Fehlern in `_generate_thought()`.

**Änderungen:**
- `_generate_thought()`: Bei Parse-Fehler niemals `raw_content` als Summary verwenden
- Stattdessen: Generische User-Message + optionaler Retry mit erhöhter Temperature
- Logging des `raw_content` für Debugging, aber nicht an User weiterreichen

**Akzeptanzkriterien:**
- [ ] Bei JSON-Parse-Fehler erscheint eine freundliche Fehlermeldung (kein Raw-JSON)
- [ ] Fehlerhafte JSON-Responses werden im Log gespeichert (Debug-Level)
- [ ] Optional: Bis zu 1 Retry mit leicht angepasstem Prompt
- [ ] Bestehende Tests für `_generate_thought` angepasst

---

### Story 2: Minimales Action-Schema und Prompt-Refactoring

**Beschreibung**: Vereinfache das Thought-JSON-Schema auf das absolute Minimum und bringe Prompt + Code in Einklang.

**Änderungen:**
- `events.py`: `Thought` Dataclass vereinfachen (optionale Felder oder komplett entfernen)
- `autonomous_prompts.py`: Neues minimales Schema im Kernel-Prompt
- `agent.py`: Parsing-Logik an neues Schema anpassen
- Action-Typen konsistent machen: `tool_call`, `respond`, `ask_user` (kein `complete`, `replan`, `finish_step` mehr im LLM-Output)

**Akzeptanzkriterien:**
- [ ] Thought-JSON hat nur noch: `action`, `tool`, `tool_input`, `question`, `answer_key`
- [ ] Kernel-Prompt und Code verwenden identische Action-Type-Namen
- [ ] `rationale`, `expected_outcome`, `confidence` werden nicht mehr vom LLM gefordert
- [ ] Alle bestehenden Execution-Flows funktionieren weiterhin

---

### Story 3: Zwei-Phasen-Response für User-Antworten (Optional)

**Beschreibung**: Implementiere separaten LLM-Call für finale User-Antworten ohne JSON-Zwang.

**Änderungen:**
- Neuer Action-Type `respond` im Agent-Code
- Bei `action: "respond"`: Zweiter LLM-Call mit `response_format=None`
- Prompt für Phase 2: "Formuliere eine schöne Markdown-Antwort basierend auf den Ergebnissen"
- Entfernung von `summary` aus dem Thought-JSON

**Akzeptanzkriterien:**
- [ ] User-Antworten werden immer als reines Markdown generiert
- [ ] Kein `summary`-Feld mehr im Thought-JSON erforderlich
- [ ] Markdown-Output ist korrekt formatiert (keine JSON-Artefakte)
- [ ] Performance-Impact <500ms pro Antwort (akzeptabler Trade-off)

---

## Compatibility Requirements

- [x] Existing APIs remain unchanged (keine Breaking Changes an CLI/API)
- [x] Database schema changes are backward compatible (keine DB-Änderungen)
- [x] UI changes follow existing patterns (Markdown-Outputs wie bisher)
- [x] Performance impact is minimal (ein zusätzlicher LLM-Call nur bei `respond`)

---

## Risk Mitigation

**Primary Risk:** Bestehende Agents könnten sich auf die bisherige JSON-Struktur verlassen (z.B. für Logging/Tracing)

**Mitigation:** 
- Feature-Flag `USE_MINIMAL_JSON_SCHEMA` für schrittweises Rollout
- Alte Felder (`rationale`, `confidence`) können optional mitgeloggt werden, auch wenn nicht mehr vom LLM gefordert
- Umfassende Regression-Tests vor Merge

**Rollback Plan:**
- Feature-Flag auf `false` setzen → alte Logik greift
- Keine Datenbank-Migrationen = kein Daten-Rollback nötig
- Git revert des Feature-Branches

---

## Definition of Done

- [ ] Alle 3 Stories completed mit Akzeptanzkriterien erfüllt
- [ ] Bestehende Funktionalität verifiziert durch Test-Suite
- [ ] Integration Points funktionieren korrekt (CLI, API)
- [ ] Dokumentation in `autonomous_prompts.py` aktualisiert
- [ ] Keine Regression in bestehenden Features

---

## Validation Checklist

### Scope Validation

- [x] Epic kann in 2-3 Stories completed werden
- [x] Keine Architektur-Dokumentation erforderlich
- [x] Enhancement folgt bestehenden Patterns (ReAct-Loop, Clean Architecture)
- [x] Integrations-Komplexität ist manageable

### Risk Assessment

- [x] Risiko für bestehendes System ist gering (Feature-Flag)
- [x] Rollback-Plan ist machbar
- [x] Testing-Ansatz deckt bestehende Funktionalität ab
- [x] Team hat ausreichend Wissen über Integration Points

### Completeness Check

- [x] Epic-Ziel ist klar und erreichbar
- [x] Stories sind angemessen abgegrenzt
- [x] Success Criteria sind messbar
- [x] Dependencies sind identifiziert

---

## Story Manager Handoff

> **Für den Story Manager:**
>
> Bitte entwickle detaillierte User Stories für dieses Brownfield Epic. Wichtige Hinweise:
>
> - Dies ist ein Enhancement für ein bestehendes System mit **Python 3.11, OpenAI API, Clean Architecture**
> - **Integration Points**: `agent.py::_generate_thought()`, `events.py::ActionType/Action/Thought`, `autonomous_prompts.py`
> - **Bestehende Patterns**: ReAct-Loop, Dataclasses für Domain Events, Structured Logging
> - **Kritische Kompatibilitäts-Anforderungen**: Keine Breaking Changes an CLI/API, Feature-Flag für Rollout
> - Jede Story muss Verifizierung enthalten, dass bestehende Funktionalität intakt bleibt
>
> Das Epic soll die Systemintegrität wahren und dabei **stabilere LLM-Responses durch minimale JSON-Oberfläche** liefern.

---

## Technical References

| File | Relevante Bereiche |
|------|-------------------|
| `core/domain/agent.py` | `_generate_thought()`, `_extract_summary_from_invalid_json()`, Fallback-Logik (Zeilen 473-612) |
| `core/domain/events.py` | `ActionType`, `Action`, `Thought` Dataclasses (Zeilen 18-81) |
| `core/prompts/autonomous_prompts.py` | `GENERAL_AUTONOMOUS_KERNEL_PROMPT`, Schema-Definition (Zeilen 98-114) |
| `core/domain/plan.py` | `PlanGenerator.generate_plan()` – optional für Markdown-Plan (Zeilen 366-418) |

---

*Epic erstellt basierend auf Architektur-Analyse vom 03.12.2025*

