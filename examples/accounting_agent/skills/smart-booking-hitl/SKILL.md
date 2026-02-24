---
name: smart-booking-hitl
description: |
  Human-in-the-Loop Buchungsworkflow für unsichere Buchungen.
  Aktivieren wenn: Confidence <95% ODER Hard Gate ausgelöst wurde.
  Dieser Skill wird automatisch von smart-booking-auto aufgerufen.
  KRITISCH: ask_user MUSS aufgerufen werden und auf Antwort gewartet werden!
allowed_tools: "hitl_review, ask_user, rule_learning, audit_log, rag_fallback, memory"
---

# Smart Booking - HITL Workflow

Dieser Workflow wird ausgeführt wenn die automatische Buchung nicht möglich ist.

## ⛔ ABSOLUTE PFLICHT - LIES DIES ZUERST! ⛔

**DU MUSST DAS TOOL `ask_user` AUFRUFEN!**

**OHNE `ask_user` DARFST DU:**
- ❌ KEINE Buchung erstellen
- ❌ KEINE Regel lernen
- ❌ KEIN Konto selbst wählen
- ❌ NICHT fortfahren

**Der Workflow ist BLOCKIERT bis der User antwortet!**

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

### Schritt 2: User befragen (PFLICHT - DARF NICHT ÜBERSPRUNGEN WERDEN!)

## ⚠️ WARNUNG: DIESER SCHRITT IST NICHT OPTIONAL! ⚠️

**DU MUSST JETZT `ask_user` AUFRUFEN!**

**WENN DU `ask_user` NICHT AUFRUFST, IST DER WORKFLOW FEHLERHAFT!**

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

### Schritt 3: Auf User-Antwort warten

**STOPP - Die Ausführung pausiert automatisch bis der User antwortet!**

### Schritt 4: User-Antwort auswerten

| User-Antwort | Interpretation | Nächster Schritt |
|--------------|----------------|------------------|
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

**Dann Audit-Log:**

```tool
audit_log(
  action="booking_created",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  hitl_confirmed=true
)
```

### Schritt 5b: Korrektur verarbeiten

Extrahiere das korrigierte Konto aus der User-Antwort.

```tool
hitl_review(
  action="process",
  review_id=<review_id>,
  user_decision="correct",
  correction={
    "debit_account": "<neues_konto>",
    "debit_account_name": "<kontoname>"
  }
)
```

**Dann Regel lernen (PFLICHT!):**

```tool
rule_learning(
  action="create_from_hitl",
  invoice_data=<invoice_data>,
  correction={
    "debit_account": "<neues_konto>",
    "debit_account_name": "<kontoname>"
  },
  rule_type="vendor_item"
)
```

**Dann Audit-Log:**

```tool
audit_log(
  action="booking_created",
  invoice_data=<invoice_data>,
  booking_proposal=<korrigierter_vorschlag>,
  hitl_corrected=true,
  original_proposal=<ursprünglicher_vorschlag>
)
```

### Schritt 5c: Ablehnung verarbeiten

```tool
hitl_review(
  action="process",
  review_id=<review_id>,
  user_decision="reject"
)
```

```tool
audit_log(
  action="booking_rejected",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  reason="user_rejected"
)
```

**User informieren:** "Buchung wurde abgelehnt und nicht durchgeführt."

### Schritt 6: Ergebnis präsentieren

#### Bei Bestätigung/Korrektur:

```markdown
## Buchung erfolgreich erstellt

### Rechnungsübersicht
- **Lieferant:** [Name]
- **Rechnungsnummer:** [Nummer]
- **Bruttobetrag:** [Betrag] EUR

### Buchung (nach Prüfung)

| Soll-Konto | Haben-Konto | Betrag | Buchungstext |
|------------|-------------|--------|--------------|
| [Konto]    | 1600        | [Netto]| [Text]       |
| 1576       | 1600        | [USt]  | Vorsteuer 19%|

### Status
[Bestätigt/Korrigiert] durch User

### Regel gelernt
Neue Regel [rule_id] für zukünftige Buchungen erstellt.
```

#### Bei Ablehnung:

```markdown
## Buchung abgelehnt

Die Rechnung wurde nicht gebucht.

- **Lieferant:** [Name]
- **Rechnungsnummer:** [Nummer]
- **Grund:** Vom Benutzer abgelehnt

Bitte prüfen Sie die Rechnung manuell.
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

### Option B: User direkt fragen

```tool
ask_user(
  question="Keine passende Buchungsregel gefunden.

Lieferant: [supplier_name]
Positionen: [line_items]
Bruttobetrag: [total_gross] EUR

Bitte geben Sie das Soll-Konto an (z.B. '4930 Bürobedarf'):
"
)
```

## Kritische Regeln

1. **IMMER `ask_user` aufrufen** - Niemals selbst entscheiden!
2. **IMMER auf Antwort warten** - Nicht fortfahren ohne User-Input!
3. **IMMER `hitl_review(action="process")` aufrufen** - Review abschließen!
4. **IMMER `rule_learning` aufrufen** - Aus jeder Interaktion lernen!
5. **IMMER `audit_log` aufrufen** - GoBD-Compliance sicherstellen!

## Fehlerbehandlung

| Fehler | Aktion |
|--------|--------|
| User antwortet nicht | Timeout nach Konfiguration, Review bleibt offen |
| Ungültige Kontonnummer | Nachfragen: "Konto [X] existiert nicht. Bitte korrigieren." |
| Technischer Fehler | Audit-Log mit Fehler, User informieren |
