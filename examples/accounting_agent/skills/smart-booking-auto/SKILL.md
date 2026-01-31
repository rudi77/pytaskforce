---
name: smart-booking-auto
description: |
  Automatischer Buchungsworkflow für Rechnungen mit hoher Confidence (>=95%).
  Aktivieren wenn: INVOICE_PROCESSING Intent erkannt wurde.
  Dieser Skill führt den deterministischen Workflow aus und wechselt automatisch
  zu smart-booking-hitl wenn Confidence <95% oder Hard Gates ausgelöst werden.
allowed_tools: docling_extract invoice_extract check_compliance semantic_rule_engine confidence_evaluator rule_learning audit_log

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
      output: rule_match

    # Step 5: Confidence bewerten
    - tool: confidence_evaluator
      params:
        invoice_data: "${invoice_data}"
        rule_match: "${rule_match}"
        booking_proposal: "${rule_match.booking_proposal}"
      output: confidence_result

    # Step 6: Entscheidung - Auto oder HITL?
    - switch:
        "on": confidence_result.recommendation
        cases:
          hitl_review:
            skill: smart-booking-hitl
          auto_book:
            continue: true

    # Step 7: Bei Auto-Booking - Regel lernen
    - tool: rule_learning
      params:
        action: "create_from_booking"
        invoice_data: "${invoice_data}"
        booking_proposal: "${rule_match.booking_proposal}"
        confidence: "${confidence_result.overall_confidence}"
      output: learned_rule
      optional: true

    # Step 8: Audit-Log erstellen
    - tool: audit_log
      params:
        action: "booking_created"
        invoice_data: "${invoice_data}"
        booking_proposal: "${rule_match.booking_proposal}"
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
PDF/Bild → Markdown → Strukturierte Daten → Compliance → Regeln → Confidence → Buchung
```

## Automatische Ausführung

Der Workflow wird vom `activate_skill` Tool **direkt ausgeführt**:
- Keine LLM-Calls zwischen den Schritten
- Deterministische Tool-Sequenz
- Automatischer Skill-Wechsel bei niedrigem Confidence

## Hard Gates (Auslöser für HITL)

| Hard Gate | Bedingung | Grund |
|-----------|-----------|-------|
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
