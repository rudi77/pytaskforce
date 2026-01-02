<!-- Powered by BMAD™ Core -->
<!-- Epic: epic-9-context-pack-rehydration.md -->

# Story 9.3: TokenBudgeter + Safe Compression (budget-basiert, handle-aware) - Brownfield Addition

## User Story

**Als** Betreiber/Entwickler des Taskforce-Agents,  
**möchte ich** ein robustes Budget-Management für Prompt-Länge (Preflight) und eine sichere Message-Compression ohne Raw Dumps,  
**damit** „input tokens exceed limit“ zuverlässig vermieden wird — auch in Tool-Heavy Sessions.

---

## Story Context

### Existing System Integration

- **Integrates with:**
  - `taskforce/src/taskforce/core/domain/lean_agent.py` – `_compress_messages()` (aktuell message-count-basiert + `json.dumps(..., indent=2)`)
  - (aus Story 9.1/9.2) Tool Handles + Context Pack
  - `taskforce/src/taskforce/infrastructure/tools/tool_converter.py` – Tool message content (nur Preview/Handle)
- **Technology:** Python 3.11, LLM messages, heuristische Token-Schätzung (ok)
- **Follows pattern:** Guardrails (preflight) + graceful degradation

### Problem Statement

Aktuell triggert Compression nach **Message Count**, nicht nach Budget. Zudem wird im Summary-Prompt `json.dumps(old_messages, indent=2)` genutzt — das skaliert schlecht und kann selbst zum Token-Overflow führen, bevor die „Kompression“ überhaupt hilft.

---

## Acceptance Criteria

### Functional Requirements

1. **TokenBudgeter:** Es gibt eine Budget-Komponente (Heuristik ist ok), die:
   - aus `messages + context_pack` eine Token-Schätzung macht (z.B. chars/4 + overhead),
   - ein `max_input_tokens`/Budget respektiert.
2. **Preflight Guard:** Vor jedem LLM-Call wird geprüft:
   - wenn > Budget → trim/summarize/sanitize wird ausgeführt (ohne Raw Tool Outputs).
3. **sanitize_message():** Es gibt eine zentrale Sanitization/Truncation pro Message Content (harte Caps), bevor Inhalte in Summaries oder Prompts gehen.
4. **Safe Compression:** `_compress_messages()` wird so angepasst, dass:
   - **kein** vollständiger JSON Dump der alten Messages genutzt wird,
   - Summary-Input nur aus sanitisierten Turns + Handle/Preview-Liste besteht,
   - Tool Raw Payloads nie in die Summary-Prompt gelangen.
5. **Budget-basierter Trigger:** Compression wird nicht nur über `SUMMARY_THRESHOLD` (Count) ausgelöst, sondern primär über Budget-Überschreitung.

### Integration Requirements

6. **Handle-aware:** Compression und Preflight verstehen, dass Tool-Ergebnisse als Handles vorliegen und holen nur Previews/Excerpts (capped).
7. **Graceful fallback:** Wenn Summarization fehlschlägt:
   - keep recent messages + system prompt + minimal context pack (capped)

### Quality Requirements

8. **Tests:** Mindestens:
   - Unit-Test: `_compress_messages()` erzeugt keinen Prompt mit `json.dumps(old_messages, indent=2)`-ähnlichem Raw Dump
   - Unit-Test: Preflight trimmt, wenn Budget überschritten wird

---

## Definition of Done

- [x] TokenBudgeter implementiert und in LeanAgent genutzt
- [x] Safe Compression implementiert (ohne raw dumps)
- [x] Budget-basierte Trigger-Logik aktiv
- [x] Tests grün
- [x] Kurze Dokumentation der Budget/Cap-Defaults

---

## Files to Create/Modify

- **Modify:**
  - `taskforce/src/taskforce/core/domain/lean_agent.py`
- **Create (suggested):**
  - `taskforce/src/taskforce/core/domain/token_budgeter.py`
  - `taskforce/tests/unit/core/test_token_budgeter.py`
  - `taskforce/tests/unit/core/test_safe_compression.py`

---

## Dev Agent Record

### Status
**Ready for Review**

### Agent Model Used
Claude Sonnet 4.5

### Tasks
- [x] Create TokenBudgeter class with heuristic token estimation
- [x] Implement sanitize_message() for safe content truncation
- [x] Add preflight budget check before LLM calls in LeanAgent
- [x] Refactor _compress_messages() to use safe compression (no raw dumps)
- [x] Add budget-based trigger logic for compression
- [x] Write unit tests for TokenBudgeter (23 tests, all passing)
- [x] Write unit tests for safe compression (11 tests, all passing)

### Completion Notes
- Implemented TokenBudgeter with heuristic token estimation (chars/4 + overhead)
- Added preflight budget checks before all LLM calls in execute() and execute_stream()
- Refactored _compress_messages() to use _build_safe_summary_input() instead of json.dumps()
- Safe summary input extracts only previews from tool results, not raw payloads
- Budget-based compression trigger is now primary, message count is fallback
- All 34 tests passing (23 TokenBudgeter + 11 safe compression)
- Default budget: 100k tokens max input, 80k tokens compression trigger
- Hard caps: 50k chars per message, 20k chars per tool output, 10k chars context pack

### File List
- Created: `taskforce/src/taskforce/core/domain/token_budgeter.py`
- Modified: `taskforce/src/taskforce/core/domain/lean_agent.py`
- Created: `taskforce/tests/unit/core/test_token_budgeter.py`
- Created: `taskforce/tests/unit/core/test_safe_compression.py`

### Change Log
- Added TokenBudgeter class with estimate_tokens(), is_over_budget(), should_compress(), sanitize_message(), extract_tool_output_preview()
- Added token_budgeter initialization in LeanAgent.__init__()
- Added _preflight_budget_check() method for emergency truncation
- Refactored _compress_messages() to trigger on budget (primary) or count (fallback)
- Added _build_safe_summary_input() to create safe previews without raw JSON dumps
- Fixed compression to handle tool messages separately (preview only, no raw content)


