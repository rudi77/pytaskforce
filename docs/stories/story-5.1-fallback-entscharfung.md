# Story 5.1: Fallback-Entschärfung und Retry-Logik - Brownfield Addition

<!-- Powered by BMAD™ Core -->
<!-- Epic: epic-5-minimal-json-architecture.md -->

## User Story

**Als** Entwickler/User des TaskForce-Agents,  
**möchte ich** dass bei JSON-Parse-Fehlern niemals rohes JSON als Antwort erscheint,  
**damit** ich immer lesbare, benutzerfreundliche Antworten erhalte – selbst bei internen Fehlern.

---

## Story Context

### Existing System Integration

- **Integrates with:** `Agent._generate_thought()` in `core/domain/agent.py`
- **Technology:** Python 3.11, OpenAI API mit `response_format={"type": "json_object"}`
- **Follows pattern:** Bestehende Fehlerbehandlung mit strukturiertem Logging
- **Touch points:** 
  - `_generate_thought()` (Zeilen 473-612)
  - `_extract_summary_from_invalid_json()` (Zeilen 450-471)
  - `ActionType.COMPLETE` Fallback-Action

### Problem Statement

Aktuell bei JSON-Parse-Fehler in `_generate_thought()`:

```python
# PROBLEMATISCH (aktuell):
else:
    fallback_summary = raw_content  # <-- Rohes JSON an User!

fallback_action = Action(
    type=ActionType.COMPLETE,
    summary=fallback_summary,  # <-- Wird dem User angezeigt
)
```

**Ergebnis:** User sieht unverständliches JSON statt einer hilfreichen Fehlermeldung.

---

## Acceptance Criteria

### Functional Requirements

1. **Keine rohen JSON-Outputs:** Bei Parse-Fehlern wird eine generische, benutzerfreundliche Fehlermeldung angezeigt
2. **Debug-Logging:** Das fehlerhafte `raw_content` wird im Log auf DEBUG-Level gespeichert (nicht an User)
3. **Retry-Mechanismus (optional):** Bei Parse-Fehler ein Retry mit leicht erhöhter Temperature (0.3 statt 0.2)

### Integration Requirements

4. Bestehende `_generate_thought()` Logik bleibt intakt für erfolgreiche JSON-Responses
5. Fehlerbehandlung folgt dem bestehenden `structlog` Logging-Pattern
6. `ActionType.COMPLETE` Fallback-Verhalten bleibt erhalten (nur mit besserer Summary)

### Quality Requirements

7. Unit-Tests für Fallback-Szenarien (ungültiges JSON, leerer Response, abgeschnittener Response)
8. Bestehende Agent-Tests passieren weiterhin
9. Keine Regression bei erfolgreichen Thought-Generierungen

---

## Technical Implementation

### Änderungen in `agent.py`

**Vorher (problematisch):**
```python
except (json.JSONDecodeError, KeyError) as e:
    extracted_summary = self._extract_summary_from_invalid_json(raw_content)
    
    if extracted_summary:
        fallback_summary = extracted_summary
    else:
        fallback_summary = raw_content  # <-- PROBLEM
```

**Nachher (sicher):**
```python
except (json.JSONDecodeError, KeyError) as e:
    extracted_summary = self._extract_summary_from_invalid_json(raw_content)
    
    if extracted_summary:
        fallback_summary = extracted_summary
    else:
        # NIEMALS raw_content als User-Output
        self.logger.debug(
            "thought_parse_raw_content",
            raw_content=raw_content[:500],  # Truncated für Logs
        )
        fallback_summary = (
            "Es ist ein interner Verarbeitungsfehler aufgetreten. "
            "Ich versuche, die Anfrage erneut zu bearbeiten."
        )
```

### Optionaler Retry-Mechanismus

```python
async def _generate_thought_with_retry(
    self, context: dict[str, Any], max_retries: int = 1
) -> Thought:
    """Generate thought with optional retry on parse failure."""
    for attempt in range(max_retries + 1):
        try:
            return await self._generate_thought(
                context, 
                temperature=0.2 + (attempt * 0.1)  # Leicht höher bei Retry
            )
        except ThoughtParseError as e:
            if attempt == max_retries:
                return self._create_fallback_thought(context, str(e))
            self.logger.warning("thought_retry", attempt=attempt + 1)
```

---

## Technical Notes

- **Integration Approach:** Minimale Änderung im `except`-Block von `_generate_thought()`
- **Existing Pattern Reference:** Strukturiertes Logging wie in `_execute_tool()` implementiert
- **Key Constraints:** 
  - Fallback muss immer ein valides `Thought`-Objekt zurückgeben
  - Keine Breaking Changes an der `Thought`-Dataclass

---

## Definition of Done

- [x] Fallback-Summary ist immer benutzerfreundlich (kein Raw-JSON)
- [x] `raw_content` wird auf DEBUG-Level geloggt
- [x] Unit-Tests für Parse-Fehler-Szenarien vorhanden
- [x] Bestehende Agent-Tests passieren
- [x] Code folgt bestehenden Patterns und Standards
- [x] Optionaler Retry-Mechanismus implementiert (oder bewusst deferred) → **Deferred**: Extraction-Mechanismus bietet bereits Recovery

---

## Risk and Compatibility Check

### Minimal Risk Assessment

- **Primary Risk:** Fallback könnte zu oft greifen und wichtige LLM-Antworten verschlucken
- **Mitigation:** DEBUG-Logging des `raw_content` ermöglicht Analyse; Retry gibt zweite Chance
- **Rollback:** Git revert des Commits – keine Daten-Migration

### Compatibility Verification

- [x] Keine Breaking Changes an bestehenden APIs
- [x] Keine Datenbankänderungen
- [x] Keine UI-Änderungen (nur bessere Fehlermeldungen)
- [x] Performance-Impact vernachlässigbar (Retry nur bei Fehler)

---

## Validation Checklist

### Scope Validation

- [x] Story kann in einer Development-Session abgeschlossen werden (~2-3h)
- [x] Integration-Ansatz ist straightforward
- [x] Folgt bestehenden Error-Handling-Patterns
- [x] Kein Design oder Architektur-Work erforderlich

### Clarity Check

- [x] Anforderungen sind eindeutig
- [x] Integration Points sind klar spezifiziert (`_generate_thought()`)
- [x] Success Criteria sind testbar
- [x] Rollback ist simpel (Git revert)

---

## Files to Modify

| File | Änderung |
|------|----------|
| `core/domain/agent.py` | Fallback-Logik in `_generate_thought()` |
| `tests/test_agent.py` | Unit-Tests für Parse-Fehler-Szenarien |

---

## Dev Agent Record

### Status: Ready for Review

### Agent Model Used
Claude Opus 4.5 (via Cursor)

### File List

| File | Action | Description |
|------|--------|-------------|
| `src/taskforce/core/domain/agent.py` | Modified | Fallback-Logik in `_generate_thought()` – ersetzt raw_content mit benutzerfreundlicher Nachricht |
| `tests/unit/test_agent.py` | Modified | 7 neue Unit-Tests für Parse-Fehler-Szenarien hinzugefügt |

### Change Log

| Date | Change |
|------|--------|
| 2025-12-03 | Fallback-Summary geändert: Nie mehr `raw_content` als User-Output |
| 2025-12-03 | DEBUG-Level Logging für `raw_content` hinzugefügt |
| 2025-12-03 | 7 Unit-Tests für Parse-Fehler hinzugefügt (invalid JSON, empty, missing keys, extraction) |
| 2025-12-03 | Retry-Mechanismus bewusst deferred – Extraction bietet bereits Recovery |

### Completion Notes

- Alle 24 Agent-Tests bestanden (17 bestehende + 7 neue)
- 97 Core/Integration-Tests bestanden – keine Regression
- Retry-Mechanismus als nicht notwendig eingestuft:
  - `_extract_summary_from_invalid_json()` deckt bereits die meisten Fälle ab
  - Benutzerfreundliche Fehlermeldung ist ausreichend für verbleibende Edge Cases

---

## QA Results

### Gate Decision: **PASS** ✅

**Review Date:** 2025-12-03  
**Reviewer:** Quinn (Test Architect)  
**Gate File:** `docs/qa/gates/5.1-fallback-entscharfung.yml`

### Requirements Traceability

| AC # | Requirement | Test Coverage | Status |
|------|-------------|---------------|--------|
| 1 | Keine rohen JSON-Outputs | `test_thought_parse_invalid_json_returns_friendly_message` | ✅ PASS |
| 2 | Debug-Logging auf DEBUG-Level | Code review: `logger.debug("thought_parse_raw_content", ...)` | ✅ PASS |
| 3 | Retry-Mechanismus (optional) | Deferred with documented rationale | ✅ WAIVED |
| 4 | Bestehende Logik intakt | 17 existing tests pass | ✅ PASS |
| 5 | structlog Logging-Pattern | Code review: follows existing pattern | ✅ PASS |
| 6 | ActionType.COMPLETE Fallback | Verified in fallback tests | ✅ PASS |
| 7 | Unit-Tests für Parse-Fehler | 7 new tests cover all scenarios | ✅ PASS |
| 8 | Bestehende Agent-Tests | 24/24 tests pass | ✅ PASS |
| 9 | Keine Regression | 97 core/integration tests pass | ✅ PASS |

### Test Coverage Analysis

**New Tests Added:** 7 comprehensive unit tests
- `test_thought_parse_invalid_json_returns_friendly_message` - Invalid JSON → friendly message
- `test_thought_parse_empty_response_returns_friendly_message` - Empty response → friendly message
- `test_thought_parse_missing_action_key_returns_friendly_message` - Missing key → friendly message
- `test_thought_parse_extracts_summary_from_invalid_json` - Extraction recovery path
- `test_extract_summary_from_invalid_json_with_escaped_quotes` - Edge case: escaped quotes
- `test_extract_summary_from_invalid_json_with_newlines` - Edge case: newlines
- `test_extract_summary_from_invalid_json_returns_none_when_not_found` - No extraction → None

**Test Results:** ✅ All 24 agent tests pass (17 existing + 7 new)  
**Regression Tests:** ✅ 97 core/integration tests pass - no regression

### Risk Assessment

**Risk Level:** LOW

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|------------|--------|
| Fallback too aggressive, hiding valid responses | Low | Medium | DEBUG logging enables analysis; extraction recovers most cases | ✅ Mitigated |
| User confusion from generic error message | Low | Low | Message is clear and actionable | ✅ Acceptable |
| Performance impact from logging | Very Low | Very Low | DEBUG-level only, truncation to 500 chars | ✅ Negligible |

### Code Quality Assessment

**Strengths:**
- ✅ Follows existing error handling patterns (structlog, defensive coding)
- ✅ Clear separation of concerns (extraction → fallback → user message)
- ✅ Comprehensive logging for observability (DEBUG + WARNING levels)
- ✅ Well-documented code with clear comments
- ✅ No breaking changes to existing APIs
- ✅ Appropriate error message (user-friendly, actionable)

**Minor Observations:**
- ⚠️ Error message is hardcoded German - consider i18n if multi-language support planned
- ℹ️ Retry mechanism deferred appropriately - extraction provides sufficient recovery

### Non-Functional Requirements Validation

| NFR | Status | Notes |
|-----|--------|-------|
| Security | ✅ PASS | No new attack vectors; generic error messages prevent information leakage |
| Performance | ✅ PASS | Negligible impact - fallback only on rare parse errors |
| Reliability | ✅ PASS | Robust error handling with extraction recovery; no regression |
| Maintainability | ✅ PASS | Clean code following existing patterns; comprehensive tests |

### Recommendations

**Immediate Actions:**
- Monitor fallback frequency in production via DEBUG logs to assess if retry mechanism becomes necessary

**Future Enhancements:**
- Consider metrics/alerting if fallback rate exceeds threshold (>1% of requests)
- Consider internationalization if multi-language support is planned

### Quality Score: **95/100**

**Deductions:**
- -5 points: Hardcoded German error message (minor i18n consideration)

**Overall Assessment:** Excellent implementation with comprehensive test coverage, proper error handling, and no regression. Ready for production deployment.

---

*Story erstellt: 03.12.2025 | Epic: 5 - Minimal-JSON Architecture*

