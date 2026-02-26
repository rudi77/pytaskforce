---
name: smart-booking-auto
description: |
  Automatischer Buchungsworkflow für Rechnungen mit hoher Confidence (>=95%).
  Aktivieren wenn: INVOICE_PROCESSING Intent erkannt wurde.
  Dieser Skill führt den deterministischen Workflow aus und wechselt automatisch
  zu smart-booking-hitl wenn Confidence <95% oder Hard Gates ausgelöst werden.
  Bei fehlenden Pflichtangaben (§14 UStG) wird der Telegram-User per ask_user befragt.
  Bei Buchungsentscheidungen wird an den Buchhalter (CLI) weitergeleitet.
allowed_tools: docling_extract invoice_extract check_compliance semantic_rule_engine confidence_evaluator rule_learning audit_log hitl_review ask_user send_notification memory

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
      # Bei Compliance-Fehlern: ask_user um fehlende Pflichtangaben zu erfragen
      # (siehe "Compliance-Validierung" Abschnitt unten)
      on_error: ask_user_for_missing_fields

    # Step 4: Kontierungsregeln anwenden
    - tool: semantic_rule_engine
      params:
        invoice_data: "${invoice_data}"
        chart_of_accounts: "SKR03"
      output: rule_result

    # Step 4b: KRITISCH - Prüfe ob Buchungsvorschläge vorhanden sind
    # WENN rules_applied = 0 → SOFORT zu HITL (Buchhalter) wechseln!
    - switch:
        "on": rule_result.rules_applied
        cases:
          "0":
            skill: smart-booking-hitl
            reason: "Keine passende Buchungsregel gefunden - Buchhalter muss entscheiden"

    # Step 5: Confidence bewerten (NUR wenn booking_proposals vorhanden!)
    - tool: confidence_evaluator
      params:
        invoice_data: "${invoice_data}"
        rule_match: "${rule_result.rule_matches[0]}"
        booking_proposal: "${rule_result.booking_proposals[0]}"
      output: confidence_result

    # Step 6: Entscheidung - Auto oder HITL?
    # Bei hitl_review → Weiterleitung an Buchhalter (CLI), NICHT ask_user!
    - switch:
        "on": confidence_result.recommendation
        cases:
          hitl_review:
            # Weiterleitung an Buchhalter:
            # 1. hitl_review(action="create") aufrufen
            # 2. send_notification an Telegram-User (informieren, nicht fragen!)
            # 3. Buchhalter bearbeitet über CLI
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

## Zwei-Rollen-Modell

| Rolle | Kanal | Verantwortung |
|-------|-------|---------------|
| **Telegram-User** | Telegram | Reicht Rechnungen ein, ergänzt fehlende Pflichtangaben |
| **Buchhalter** | CLI | Trifft Buchungsentscheidungen bei HITL-Reviews |

## Workflow-Übersicht

```
PDF/Bild → Markdown → Strukturierte Daten → Compliance-Prüfung → Regeln → Confidence → Buchung
                                                    ↓                          ↓
                                          Fehler? → ask_user         HITL? → Buchhalter (CLI)
                                          (Telegram-User)           (send_notification)
```

## Compliance-Validierung (§14 UStG)

**WENN `check_compliance` Fehler mit `severity: error` zurückgibt:**

Diese Fehler bedeuten, dass **Pflichtangaben fehlen**. Der Telegram-User kann diese
ergänzen, da er die Rechnung physisch vorliegen hat.

**→ `ask_user` aufrufen um fehlende Angaben zu erfragen:**

```tool
ask_user(
  question="⚠️ Die Rechnung ist unvollständig.

Folgende Pflichtangaben nach §14 UStG fehlen:
- [Feldname]: [Beschreibung] ([Rechtsgrundlage])
- [Feldname]: [Beschreibung] ([Rechtsgrundlage])

Bitte ergänzen Sie die fehlenden Angaben oder senden Sie ein besseres Bild der Rechnung.",
  channel="telegram",
  recipient_id="<sender_id_aus_metadata>"
)
```

→ Wartet auf Antwort vom Telegram-User, ergänzt die Daten, prüft erneut.

**HINWEIS:** Warnungen (`severity: warning`) wie fehlendes Lieferdatum sind KEINE
Abbruchgründe. Nur Fehler (`severity: error`) blockieren den Workflow.

## HITL: Buchhalter über Standard-ask_user fragen

**WENN `smart-booking-hitl` aktiviert wird:**

Der Buchhalter wird über den Standard-`ask_user` (ohne channel) gefragt.
Er antwortet direkt in der CLI. Der Telegram-User wird per `send_notification`
über das Ergebnis informiert.

## KRITISCH: Keine Buchungsregel gefunden

**WENN `semantic_rule_engine` KEINE passenden Regeln findet:**

1. `booking_proposals` ist LEER (`[]`)
2. `unmatched_items` enthält die nicht-gematchten Positionen

**→ Wechsle zu `smart-booking-hitl`!** (Weiterleitung an Buchhalter)

**DU DARFST NICHT:**
- Selbst eine Regel erstellen
- Selbst ein Konto wählen
- Den Telegram-User nach dem Konto fragen

## Automatische Ausführung

Der Workflow wird vom `activate_skill` Tool **direkt ausgeführt**:
- Keine LLM-Calls zwischen den Schritten
- Deterministische Tool-Sequenz
- Automatischer Skill-Wechsel bei niedrigem Confidence
- **SOFORTIGER Skill-Wechsel wenn keine Regel gefunden**

## Hard Gates (Auslöser für Buchhalter-HITL)

| Hard Gate | Bedingung | Aktion |
|-----------|-----------|--------|
| `no_rule_match` | **booking_proposals ist leer** | → Buchhalter (CLI) |
| `new_vendor` | Erster Invoice von diesem Lieferanten | → Buchhalter (CLI) |
| `high_amount` | Bruttobetrag > 5.000 EUR | → Buchhalter (CLI) |
| `critical_account` | Zielkonto 1800, 2100 | → Buchhalter (CLI) |

## Confidence-Signale

| Signal | Gewicht | Beschreibung |
|--------|---------|--------------|
| Rule Type | 30% | Vendor-Only > Vendor+Item > RAG |
| Similarity Score | 25% | Embedding-Ähnlichkeit |
| Match Uniqueness | 20% | Eindeutigkeit des Matches |
| Historical Hit Rate | 15% | Erfolgsrate der Regel |
| OCR Quality | 10% | Extraktionsqualität |
