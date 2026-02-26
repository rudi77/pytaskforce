---
name: smart-booking-hitl
description: |
  Human-in-the-Loop Buchungsworkflow für unsichere Buchungen.
  Aktivieren wenn: Confidence <95% ODER Hard Gate ausgelöst wurde.
  Dieser Skill wird automatisch von smart-booking-auto aufgerufen.
  WEITERLEITUNG: Review wird erstellt und an den Buchhalter (CLI) delegiert.
  Der Telegram-User wird per send_notification informiert.
allowed_tools: "hitl_review, send_notification, rule_learning, audit_log, rag_fallback, memory, ask_user"
---

# Smart Booking - HITL Workflow (Weiterleitung an Buchhalter)

Dieser Workflow wird ausgeführt wenn die automatische Buchung nicht möglich ist.
**Buchungsentscheidungen werden an den Buchhalter (CLI) delegiert, NICHT über Telegram gelöst.**

## Zwei-Rollen-Modell

| Rolle | Kanal | Aufgabe |
|-------|-------|---------|
| Telegram-User | Telegram | Reicht Rechnungen ein, beantwortet Fragen zu fehlenden Pflichtangaben |
| Buchhalter | CLI | Trifft Buchungsentscheidungen (Konto bestätigen/korrigieren/ablehnen) |

## Voraussetzungen

Du erhältst aus dem vorherigen Skill:
- `invoice_data`: Strukturierte Rechnungsdaten
- `rule_match`: Ergebnis des Regel-Matchings (kann leer sein)
- `confidence_result`: Bewertungsergebnis mit Hard Gates

## Workflow-Schritte

### Schritt 1: HITL-Review erstellen

```tool
hitl_review(
  action="create",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal_aus_rule_match>,
  confidence_result=<confidence_result>
)
```

**Ausgabe speichern als:** `review_result` (enthält `review_id`)

### Schritt 2: Telegram-User per Notification informieren

**WICHTIG: Verwende `send_notification`, NICHT `ask_user`!**

Buchungsentscheidungen trifft der Buchhalter, nicht der Telegram-User.

```tool
send_notification(
  channel="telegram",
  recipient_id="<sender_id>",
  message="📨 Ihre Rechnung wird zur Prüfung weitergeleitet.

📋 Rechnung: [invoice_number] von [supplier_name]
💰 Betrag: [total_gross] EUR
🔍 Grund: [triggered_hard_gates oder 'Confidence unter 95%']
📝 Review-ID: [review_id]

Der Buchhalter wird die Kontierung prüfen und freigeben."
)
```

### Schritt 3: Audit-Log für offenen Review

```tool
audit_log(
  action="review_created",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  review_id=<review_id>,
  reason=<triggered_hard_gates>
)
```

### Schritt 4: Antwort an den Aufrufer

Antworte mit einer Zusammenfassung:

```
📨 Rechnung zur Prüfung weitergeleitet.

• Lieferant: [Name]
• Rechnungsnummer: [Nummer]
• Bruttobetrag: [Betrag] EUR
• Grund: [Hard Gate / niedrige Confidence]
• Review-ID: [review_id]

Der Buchhalter wird die Buchung über die CLI bearbeiten.
```

→ Der Workflow endet hier. Der Buchhalter übernimmt über die CLI.

---

## Buchhalter-Workflow (über CLI)

Wenn der Buchhalter über die CLI einen offenen Review bearbeitet:

### Bei Bestätigung:

```tool
hitl_review(
  action="process",
  review_id=<review_id>,
  user_decision="confirm"
)
```

Dann Regel lernen und Audit-Log:

```tool
rule_learning(
  action="create_from_hitl_confirmation",
  invoice_data=<invoice_data>,
  position_bookings=[
    {"item_description": "...", "debit_account": "...", "debit_account_name": "..."}
  ]
)
```

```tool
audit_log(action="booking_created", invoice_data=<invoice_data>, hitl_confirmed=true)
```

Telegram-User benachrichtigen:

```tool
send_notification(
  channel="telegram",
  recipient_id="<sender_id>",
  message="✅ Buchung freigegeben (Review [review_id]):
• Rechnung [invoice_number] von [supplier_name]
• Konto: [debit_account] ([debit_account_name])
• Betrag: [total_gross] EUR"
)
```

### Bei Korrektur:

```tool
hitl_review(
  action="process",
  review_id=<review_id>,
  user_decision="correct",
  correction={"debit_account": "<neues_konto>", "debit_account_name": "<kontoname>"}
)
```

```tool
rule_learning(
  action="create_from_hitl",
  invoice_data=<invoice_data>,
  correction={"debit_account": "<neues_konto>", "debit_account_name": "<kontoname>"}
)
```

```tool
audit_log(action="booking_created", hitl_corrected=true)
```

```tool
send_notification(channel="telegram", recipient_id="<sender_id>",
  message="✅ Buchung korrigiert und freigegeben (Review [review_id])")
```

### Bei Ablehnung:

```tool
hitl_review(action="process", review_id=<review_id>, user_decision="reject")
```

```tool
audit_log(action="booking_rejected", reason="accountant_rejected")
```

```tool
send_notification(channel="telegram", recipient_id="<sender_id>",
  message="❌ Buchung abgelehnt (Review [review_id]): [Grund]")
```

## Ausnahme: Fehlende Rechnungsdaten (Telegram-Rückfrage)

**NUR wenn Pflichtangaben fehlen** (Rechnungsdatum, Steuernummer, Lieferantenname etc.)
darf `ask_user` aufgerufen werden, da nur der Telegram-User diese Angaben ergänzen kann.

```tool
ask_user(
  question="⚠️ Fehlende Angaben auf der Rechnung:
- [Feld]: [Beschreibung]

Bitte ergänzen Sie die fehlenden Informationen."
)
```

## Fallback: Kein Regelvorschlag

Wenn `rule_match` leer ist (keine passende Regel gefunden):

### Option A: RAG Fallback verwenden

```tool
rag_fallback(
  invoice_data=<invoice_data>,
  top_k=3
)
```

Liefert LLM-basierte Vorschläge aus ähnlichen historischen Buchungen.
Erstelle Review mit RAG-Vorschlag und leite an Buchhalter weiter.

## Kritische Regeln

1. **`ask_user` NUR für fehlende Pflichtangaben** - Buchungsentscheidungen gehen an den Buchhalter!
2. **IMMER `send_notification` nutzen** um den Telegram-User über den Status zu informieren
3. **IMMER `hitl_review(action="create")` aufrufen** - Review dokumentieren!
4. **IMMER `audit_log` aufrufen** - GoBD-Compliance sicherstellen!
5. **Workflow endet nach Notification** - Buchhalter übernimmt über CLI!
