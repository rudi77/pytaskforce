---
name: smart-booking-auto
description: |
  Automatischer Buchungsworkflow für Rechnungen mit hoher Confidence (>=95%).
  Aktivieren wenn: INVOICE_PROCESSING Intent erkannt wurde.
  Dieser Skill führt den deterministischen Workflow aus und wechselt automatisch
  zu smart-booking-hitl wenn Confidence <95% oder Hard Gates ausgelöst werden.
allowed_tools: docling_extract invoice_extract check_compliance semantic_rule_engine confidence_evaluator rule_learning audit_log hitl_review ask_user

workflow:
  steps:
    # Step 1: PDF zu Markdown extrahieren
    - tool: docling_extract
      params:
        file_path: "${input.file_path}"
      output: markdown_content
      optional: true  # Kann übersprungen werden wenn bereits Markdown

    # Step 2: Strukturierte Rechnungsdaten extrahieren
    - tool: invoice_extract
      params:
        markdown_content: "${markdown_content}"
        expected_currency: "EUR"
      output: invoice_data

    # Step 3: Compliance prüfen (§14 UStG)
    - tool: check_compliance
      params:
        invoice_data: "${invoice_data}"
      output: compliance_result
      abort_on_error: true  # Bei kritischen Fehlern abbrechen

    # Step 4: Kontierungsregeln anwenden
    - tool: semantic_rule_engine
      params:
        invoice_data: "${invoice_data}"
        chart_of_accounts: "SKR03"
      output: rule_result

    # Step 4b: KRITISCH - Prüfe ob Buchungsvorschläge vorhanden sind
    # WENN rules_applied = 0 → SOFORT zu HITL wechseln!
    - switch:
        "on": rule_result.rules_applied
        cases:
          "0":
            skill: smart-booking-hitl
            reason: "Keine passende Buchungsregel gefunden - User muss entscheiden"

    # Step 5: Confidence bewerten (NUR wenn booking_proposals vorhanden!)
    - tool: confidence_evaluator
      params:
        invoice_data: "${invoice_data}"
        rule_match: "${rule_result.rule_matches[0]}"
        booking_proposal: "${rule_result.booking_proposals[0]}"
      output: confidence_result

    # Step 6: Entscheidung - Auto oder HITL?
    # KRITISCH: Wenn recommendation = hitl_review, MUSS ask_user aufgerufen werden!
    - switch:
        "on": confidence_result.recommendation
        cases:
          hitl_review:
            # PFLICHT-SEQUENZ für HITL:
            # 1. hitl_review(action="create") aufrufen
            # 2. ask_user aufrufen mit Buchungsvorschlag
            # 3. Warten auf User-Antwort
            # 4. hitl_review(action="process") mit User-Entscheidung
            # 5. rule_learning aufrufen
            skill: smart-booking-hitl
          auto_book:
            continue: true

    # Step 7: Bei Auto-Booking - Regel lernen
    - tool: rule_learning
      params:
        action: "create_from_booking"
        invoice_data: "${invoice_data}"
        booking_proposal: "${rule_result.booking_proposals[0]}"
        confidence: "${confidence_result.overall_confidence}"
      output: learned_rule
      optional: true

    # Step 8: Audit-Log erstellen
    - tool: audit_log
      params:
        action: "booking_created"
        invoice_data: "${invoice_data}"
        booking_proposal: "${rule_result.booking_proposals[0]}"
        confidence: "${confidence_result.overall_confidence}"
        auto_booked: true
      output: audit_entry

  on_complete: "Buchung erfolgreich erstellt"
  on_error: "Buchung konnte nicht abgeschlossen werden"
---

# Smart Booking - Automatischer Workflow

Dieser Skill führt einen **deterministischen Workflow** aus, der Rechnungen
automatisch verarbeitet und bucht, wenn die Confidence >= 95% ist.

## Workflow-Übersicht

```
PDF/Bild → Markdown → Strukturierte Daten → Compliance → Regeln → [PRÜFUNG] → Confidence → Buchung
                                                           ↓
                                              Keine Regel? → HITL
```

## KRITISCH: Keine Buchungsregel gefunden

**WENN `semantic_rule_engine` KEINE passenden Regeln findet:**

1. `booking_proposals` ist LEER (`[]`)
2. `unmatched_items` enthält die nicht-gematchten Positionen

**→ DU MUSST SOFORT zu `smart-booking-hitl` wechseln!**

**DU DARFST NICHT:**
- Selbst eine Regel erstellen
- Selbst ein Konto wählen
- Ohne User-Bestätigung fortfahren

## Automatische Ausführung

Der Workflow wird vom `activate_skill` Tool **direkt ausgeführt**:
- Keine LLM-Calls zwischen den Schritten
- Deterministische Tool-Sequenz
- Automatischer Skill-Wechsel bei niedrigem Confidence
- **SOFORTIGER Skill-Wechsel wenn keine Regel gefunden**

## Hard Gates (Auslöser für HITL)

| Hard Gate | Bedingung | Grund |
|-----------|-----------|-------|
| `no_rule_match` | **booking_proposals ist leer** | **Keine passende Regel - User muss entscheiden** |
| `new_vendor` | Erster Invoice von diesem Lieferanten | Keine Historie |
| `high_amount` | Bruttobetrag > 5.000 EUR | Wesentlichkeit |
| `critical_account` | Zielkonto 1800, 2100 | Privatentnahmen, Anzahlungen |

## Confidence-Signale

| Signal | Gewicht | Beschreibung |
|--------|---------|--------------|
| Rule Type | 30% | Vendor-Only > Vendor+Item > RAG |
| Similarity Score | 25% | Embedding-Ähnlichkeit |
| Match Uniqueness | 20% | Eindeutigkeit des Matches |
| Historical Hit Rate | 15% | Erfolgsrate der Regel |
| OCR Quality | 10% | Extraktionsqualität |
