---
name: smart-booking-auto
description: |
  Automatischer Buchungsworkflow für Rechnungen mit hoher Confidence (>=95%).
  Aktivieren wenn: INVOICE_PROCESSING Intent erkannt wurde.
  Dieser Skill führt den deterministischen Workflow aus und wechselt automatisch
  zu smart-booking-hitl wenn Confidence <95% oder Hard Gates ausgelöst werden.
allowed_tools:
  - docling_extract
  - invoice_extract
  - check_compliance
  - semantic_rule_engine
  - confidence_evaluator
  - rule_learning
  - audit_log
---

# Smart Booking - Automatischer Workflow

Führe diesen deterministischen Workflow **exakt in dieser Reihenfolge** aus.

## Workflow-Schritte

### Schritt 1: Extraktion

```tool
docling_extract(file_path="<pfad_zur_rechnung>")
```

Konvertiert PDF/Bild zu Markdown.

Falls bereits Markdown vorhanden, überspringe diesen Schritt.

### Schritt 2: Strukturierung

```tool
invoice_extract(markdown_content="<markdown_aus_schritt_1>")
```

Extrahiert strukturierte Rechnungsdaten (Invoice-Objekt).

**Ausgabe speichern als:** `invoice_data`

### Schritt 3: Kontext-Analyse

Bestimme den Steuer-Kontext anhand der extrahierten Daten:

| Kontext | Erkennung | Behandlung |
|---------|-----------|------------|
| Inlandsrechnung (DE→DE) | USt-IdNr. beginnt mit "DE" | Strenge §14 UStG Prüfung |
| EU-Rechnung (EU→DE) | USt-IdNr. beginnt mit AT/FR/NL/etc. | Reverse Charge prüfen |
| Drittland-Rechnung | Keine EU-USt-IdNr. | Einfuhr-USt prüfen |

### Schritt 4: Compliance-Prüfung

```tool
check_compliance(invoice_data=<invoice_data>)
```

Validiert Pflichtangaben nach §14 UStG.

**Bei kritischen Fehlern:** STOPP - User informieren, kein Buchungsvorschlag.

**Bei Warnungen:** Fortfahren mit Hinweis.

### Schritt 5: Regel-Matching

```tool
semantic_rule_engine(
  invoice_data=<invoice_data>,
  match_mode="vendor_then_item"
)
```

Findet passende Buchungsregel:
1. **Vendor-Only Rules** (Priorität 100) - Exakte Lieferanten-Zuordnung
2. **Vendor+Item Rules** (Priorität 90) - Semantisches Item-Matching
3. **Learned Rules** - Aus vorherigen Buchungen/Korrekturen

**Ausgabe speichern als:** `rule_match`

### Schritt 6: Confidence-Bewertung

```tool
confidence_evaluator(
  invoice_data=<invoice_data>,
  rule_match=<rule_match>,
  booking_proposal=<booking_proposal_aus_rule_match>
)
```

Berechnet gewichtete Confidence und prüft Hard Gates.

**Ausgabe enthält:**
- `overall_confidence`: Float (0.0-1.0)
- `recommendation`: "auto_book" oder "hitl_review"
- `triggered_hard_gates`: Liste der ausgelösten Gates
- `signals`: Detaillierte Bewertung

### Schritt 7: Entscheidung

**WENN** `confidence >= 0.95` **UND** `triggered_hard_gates == []`:

→ Weiter zu **Schritt 8** (Auto-Booking)

**SONST:**

→ **SKILL WECHSELN** zu `smart-booking-hitl`

   Übergib: `invoice_data`, `rule_match`, `confidence_result`

### Schritt 8: Auto-Booking abschließen

#### 8a: Regel lernen

```tool
rule_learning(
  action="create_from_booking",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  confidence=<overall_confidence>,
  rule_type="vendor_only"  # oder "vendor_item"
)
```

#### 8b: Audit-Log

```tool
audit_log(
  action="booking_created",
  invoice_data=<invoice_data>,
  booking_proposal=<booking_proposal>,
  confidence=<overall_confidence>,
  auto_booked=true
)
```

### Schritt 9: Output

Präsentiere dem User das Ergebnis:

```markdown
## Buchung erfolgreich erstellt

### Rechnungsübersicht
- **Lieferant:** [Name]
- **Rechnungsnummer:** [Nummer]
- **Bruttobetrag:** [Betrag] EUR

### Buchungsvorschlag (automatisch gebucht)

| Soll-Konto | Haben-Konto | Betrag | Buchungstext |
|------------|-------------|--------|--------------|
| [Konto]    | 1600        | [Netto]| [Text]       |
| 1576       | 1600        | [USt]  | Vorsteuer 19%|

### Confidence
[X]% - Automatische Buchung

### Rechtsgrundlage
[Basis aus Regel]
```

## Hard Gates (Auslöser für HITL)

Diese Bedingungen lösen **immer** einen HITL-Review aus:

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
