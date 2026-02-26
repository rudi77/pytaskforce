---
name: smart-booking-hitl
description: |
  Human-in-the-Loop Buchungsworkflow für unsichere Buchungen.
  Aktivieren wenn: Confidence <95% ODER Hard Gate ausgelöst wurde.
  Dieser Skill wird automatisch von smart-booking-auto aufgerufen.
  Buchungsentscheidungen werden über den Standard-ask_user an den Buchhalter (CLI) gestellt.
  Fehlende Pflichtangaben werden per ask_user(channel="telegram") beim Einreicher erfragt.
allowed_tools: "hitl_review, ask_user, send_notification, rule_learning, audit_log, rag_fallback, memory"
---

# Smart Booking - HITL Workflow

Dieser Workflow wird ausgeführt wenn die automatische Buchung nicht möglich ist.

## Zwei-Rollen-Modell mit `ask_user`

| Wer | Wie | Wann |
|-----|-----|------|
| **Buchhalter (CLI)** | `ask_user(question="...")` | Buchungsentscheidungen (Konto bestätigen/korrigieren/ablehnen) |
| **Telegram-User** | `ask_user(question="...", channel="telegram", recipient_id="...")` | Fehlende Pflichtangaben ergänzen |

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

### Schritt 2: Buchhalter befragen (Standard ask_user → CLI)

**PFLICHT: `ask_user` MUSS aufgerufen werden (ohne channel → geht an CLI-Buchhalter)!**

```tool
ask_user(
  question="Buchungsvorschlag zur Prüfung:

Lieferant: [supplier_name]
Rechnungsnummer: [invoice_number]
Bruttobetrag: [total_gross] EUR
Nettobetrag: [total_net] EUR
MwSt: [total_vat] EUR ([vat_rate]%)

Vorgeschlagenes Soll-Konto: [debit_account] - [debit_account_name]
Haben-Konto: 1600 - Verbindlichkeiten

Confidence: [overall_confidence]%
Grund für Prüfung: [triggered_hard_gates oder 'Confidence unter 95%']

Bitte wählen Sie:
1. Bestätigen - Vorschlag übernehmen
2. Korrigieren - Anderes Konto angeben (z.B. 'Konto 4930')
3. Ablehnen - Nicht buchen"
)
```

### Schritt 3: Auf Buchhalter-Antwort warten

**STOPP - Die Ausführung pausiert automatisch bis der Buchhalter in der CLI antwortet!**

### Schritt 4: Buchhalter-Antwort auswerten

| Antwort | Interpretation | Nächster Schritt |
|---------|----------------|------------------|
| "1", "Bestätigen", "Ja", "OK" | `confirm` | Schritt 5a |
| "2", "Korrigieren", "Konto XXXX" | `correct` | Schritt 5b |
| "3", "Ablehnen", "Nein" | `reject` | Schritt 5c |

### Schritt 5a: Bestätigung verarbeiten

```tool
hitl_review(
  action="process",
  review_id=<review_id>,
  user_decision="confirm"
)
```

**Dann Regel lernen (PFLICHT!):**

```tool
rule_learning(
  action="create_from_hitl_confirmation",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  rule_type="vendor_item"
)
```

**Dann Audit-Log und Telegram-User benachrichtigen:**

```tool
audit_log(
  action="booking_created",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  hitl_confirmed=true
)
```

```tool
send_notification(
  channel="telegram",
  recipient_id="<sender_id>",
  message="✅ Buchung freigegeben: [Rechnungsnr.] von [Lieferant] → Konto [XXXX]"
)
```

### Schritt 5b: Korrektur verarbeiten

```tool
hitl_review(
  action="process",
  review_id=<review_id>,
  user_decision="correct",
  correction={"debit_account": "<neues_konto>", "debit_account_name": "<kontoname>"}
)
```

**Dann Regel lernen + Audit-Log + Telegram-Benachrichtigung** (wie 5a).

### Schritt 5c: Ablehnung verarbeiten

```tool
hitl_review(action="process", review_id=<review_id>, user_decision="reject")
```

```tool
audit_log(action="booking_rejected", reason="accountant_rejected")
```

```tool
send_notification(
  channel="telegram",
  recipient_id="<sender_id>",
  message="❌ Buchung abgelehnt: [Rechnungsnr.] von [Lieferant]"
)
```

## Ausnahme: Fehlende Rechnungsdaten (Telegram-Rückfrage)

**NUR wenn Pflichtangaben fehlen** darf der Telegram-User direkt gefragt werden:

```tool
ask_user(
  question="⚠️ Fehlende Angaben auf der Rechnung:
- [Feld]: [Beschreibung]

Bitte ergänzen Sie die fehlenden Informationen.",
  channel="telegram",
  recipient_id="<sender_id>"
)
```

## Fallback: Kein Regelvorschlag

Wenn `rule_match` leer ist (keine passende Regel gefunden):

```tool
rag_fallback(invoice_data=<invoice_data>, top_k=3)
```

Erstelle Buchungsvorschlag aus RAG-Ergebnissen und frage den Buchhalter wie in Schritt 2.

## Kritische Regeln

1. **Standard `ask_user`** für Buchungsentscheidungen → Buchhalter (CLI)
2. **`ask_user(channel="telegram")`** NUR für fehlende Pflichtangaben → Telegram-User
3. **`send_notification`** für Ergebnis-Benachrichtigungen → Telegram-User
4. **IMMER `hitl_review(action="process")` aufrufen** - Review abschließen!
5. **IMMER `rule_learning` aufrufen** - Aus jeder Interaktion lernen!
6. **IMMER `audit_log` aufrufen** - GoBD-Compliance sicherstellen!
