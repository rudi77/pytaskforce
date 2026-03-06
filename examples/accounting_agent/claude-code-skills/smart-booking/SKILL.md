---
name: smart-booking
description: >
  Rechnungen intelligent buchen mit automatischer SKR03/SKR04 Kontierung,
  §14 UStG Compliance-Pruefung, und GoBD-konformem Audit Trail.
  Verwende diesen Skill immer wenn der User eine Rechnung buchen, kontieren
  oder verarbeiten moechte. Auch bei "buche das", "kontiere die Rechnung",
  "Rechnung verarbeiten", "was soll ich mit dieser Rechnung machen",
  oder wenn ein PDF/Bild einer Rechnung bereitgestellt wird.
  Erkennt Lieferanten, ordnet Konten zu, lernt aus Korrekturen,
  und fuehrt einen revisionssicheren Audit Trail.
---

# Smart Booking — Rechnungen intelligent buchen

Dieser Skill fuehrt dich durch den vollstaendigen Buchungsworkflow fuer
Eingangsrechnungen nach deutschem Steuerrecht (SKR03/SKR04).

## Workspace

Alle Daten werden in `.bookkeeping/` im aktuellen Verzeichnis gespeichert:
```
.bookkeeping/
├── rules/learned_rules.yaml    # Gelernte Buchungsregeln
├── bookings/bookings.jsonl     # Buchungshistorie (append-only)
└── audit/audit_trail.jsonl     # GoBD-konformer Audit Trail
```

Das Verzeichnis wird automatisch beim ersten Lauf erstellt.

## Workflow — Schritt fuer Schritt

Fuehre die folgenden Phasen **in dieser Reihenfolge** aus. Ueberspringe keine Phase.

### Phase 1: Rechnungsdaten extrahieren

Lies die Rechnungsdatei (PDF, Bild, oder Text) und extrahiere diese Felder
in ein strukturiertes JSON-Objekt:

```json
{
  "supplier_name": "Firmenname des Lieferanten",
  "supplier_address": "Strasse, PLZ, Ort",
  "supplier_vat_id": "DE123456789 oder Steuernummer",
  "invoice_number": "RE-2024-001",
  "invoice_date": "2024-01-15",
  "delivery_date": "2024-01-10",
  "total_net": 1000.00,
  "total_vat": 190.00,
  "total_gross": 1190.00,
  "line_items": [
    {
      "description": "Positionsbeschreibung",
      "quantity": 1,
      "unit_price": 1000.00,
      "net_amount": 1000.00,
      "vat_rate": 0.19,
      "vat_amount": 190.00
    }
  ],
  "vat_breakdown": [
    {"rate": 0.19, "net_amount": 1000.00, "vat_amount": 190.00}
  ]
}
```

**Wichtig bei der Extraktion:**
- Betraege immer als Dezimalzahlen (Punkt als Trennzeichen)
- Datumsformate: ISO 8601 (YYYY-MM-DD)
- USt-Saetze als Dezimal (0.19 fuer 19%, 0.07 fuer 7%)
- DACH-Formate beachten (DE/AT/CH haben verschiedene USt-ID Formate)
- Bei Reverse Charge: im JSON notieren ("reverse_charge": true)

Speichere das JSON in eine temporaere Datei: `.bookkeeping/current_invoice.json`

### Phase 2: Compliance-Pruefung (§14 UStG)

Fuehre das Compliance-Script aus:

```bash
python <SKILL_DIR>/scripts/compliance.py \
  --input .bookkeeping/current_invoice.json \
  --rules <SKILL_DIR>/resources/compliance_rules.yaml
```

**Ergebnis auswerten:**

- `is_compliant: true` → Weiter zu Phase 3
- `is_compliant: false` → Dem User die fehlenden Pflichtangaben zeigen:
  - Zeige jedes fehlende Feld mit der gesetzlichen Grundlage
  - Frage den User ob er die fehlenden Daten ergaenzen kann
  - Nach Ergaenzung: Compliance-Check erneut ausfuehren
  - **Buchung NICHT fortsetzen solange errors existieren**
- `warnings` → Hinweise anzeigen, blockieren aber nicht

**Sonderfall Kleinbetragsrechnung:** Bei Bruttobetrag <= 250 EUR gelten
reduzierte Anforderungen (§33 UStDV). Das Script erkennt dies automatisch.

### Phase 3: Kontierung (Kontozuordnung)

Fuehre das Kontierung-Script aus:

```bash
python <SKILL_DIR>/scripts/kontierung.py \
  --input .bookkeeping/current_invoice.json \
  --rules <SKILL_DIR>/resources/kontierung_rules.yaml \
  --workspace .bookkeeping
```

Das Script durchlaeuft drei Matching-Stufen:
1. **Gelernte Regeln** (aus frueheren Buchungen/Korrekturen) — hoechste Prioritaet
2. **Vendor-Regeln** (direkter Lieferant → Konto Mapping)
3. **Semantische Regeln** (Positionsbeschreibung ~ Muster Matching)

**Ergebnis auswerten:**

Das Ergebnis enthaelt `confidence.recommendation`:

- **`auto_book`** → Confidence >= 95%, keine Hard Gates → Weiter zu Phase 4A
- **`hitl_review`** → Confidence < 95% ODER Hard Gate → Weiter zu Phase 4B

### Phase 4A: Automatische Buchung (bei auto_book)

Wenn `recommendation == "auto_book"`:

1. **Buchungsvorschlag dem User kurz zeigen** (Zusammenfassung):

```
Automatische Buchung (bekannter Lieferant, Confidence: 97%):

Lieferant: [Name]
Rechnungsnr.: [Nummer]
Brutto: [Betrag] EUR

Positionen:
1. [Beschreibung] → Konto [XXXX] ([Kontoname])  |  [Netto] EUR
   Vorsteuer: [VSt-Konto] | [VSt-Betrag] EUR
```

2. **Buchung speichern:**

```bash
echo '<booking_json>' | python <SKILL_DIR>/scripts/booking.py save --workspace .bookkeeping
```

Das booking_json muss enthalten: supplier_name, invoice_number, invoice_date,
total_gross, total_net, total_vat, booking_proposals (aus Phase 3), decision ("auto_book"),
confidence.

3. **Regel lernen:**

```bash
echo '<rule_json>' | python <SKILL_DIR>/scripts/booking.py learn --workspace .bookkeeping
```

Das rule_json: action="create_from_booking", supplier_name, confidence,
position_bookings (je Position: item_description, debit_account, debit_account_name).

4. **Audit Log:**

```bash
echo '<audit_json>' | python <SKILL_DIR>/scripts/booking.py audit --workspace .bookkeeping
```

### Phase 4B: Manuelle Pruefung (bei hitl_review)

Wenn `recommendation == "hitl_review"`:

1. **Detaillierten Buchungsvorschlag zeigen:**

```
BUCHUNGSVORSCHLAG ZUR PRUEFUNG

Lieferant: [Name] [ggf. NEU oder Hard-Gate Grund]
Rechnungsnr.: [Nummer]
Brutto: [Betrag] EUR
Confidence: [XX]%

[Wenn Hard Gates getriggert, diese auflisten mit Grund]

POSITIONEN & KONTIERUNGSVORSCHLAEGE:

1. [Beschreibung] — [Netto] EUR
   → Konto [XXXX] ([Kontoname])
   Confidence: [XX]%, Grund: [Regel-Info]

2. [Beschreibung] — [Netto] EUR
   → Konto [XXXX] ([Kontoname])
   Confidence: [XX]%, Grund: [Regel-Info]

[Falls unmatched_items vorhanden:]
NICHT ZUGEORDNETE POSITIONEN:
- [Beschreibung] — Bitte Konto angeben

---
Optionen:
1. BESTAETIGEN — Vorschlag uebernehmen
2. KORRIGIEREN — z.B. "Position 1 auf Konto 4930" oder "alles auf 6805"
3. ABLEHNEN — Nicht buchen
```

2. **User-Entscheidung verarbeiten:**

**Bei Bestaetigung (1):**
- Buchung speichern (decision: "user_confirmed")
- Regel lernen (action: "create_from_hitl_confirmation")
- Audit Log schreiben

**Bei Korrektur (2):**
- Korrigierte Konten in die Buchungsvorschlaege einarbeiten
- Buchung speichern (decision: "user_corrected", user_corrections: {...})
- Regel lernen (action: "create_from_hitl", mit korrigierten Konten)
- Audit Log schreiben
- HITL-Korrekturen bekommen Prioritaet 90 (hoeher als automatische Regeln)

**Bei Ablehnung (3):**
- Nur Audit Log schreiben (operation: "booking_rejected")
- Keine Regel lernen
- Keine Buchung speichern

### Phase 5: Zusammenfassung

Am Ende **immer** eine Zusammenfassung ausgeben:

```
BUCHUNG ABGESCHLOSSEN

Lieferant: [Name]
Rechnungsnr.: [Nummer]
Brutto: [Betrag] EUR

Buchungen:
- [Beschreibung] → [Konto] ([Kontoname]) | [Netto] EUR
  Vorsteuer: [VSt-Konto] | [VSt-Betrag] EUR

Status: [Automatisch gebucht / Manuell bestaetigt / Korrigiert / Abgelehnt]
Audit-ID: [Log-ID]
Neue Regeln: [Anzahl] gelernt
```

## Ausgabeformat

Alle Betraege in **deutschem Format** anzeigen (1.234,56 EUR).
Kontonummern immer 4-stellig. Bei SKR04-Bedarf das Mapping aus
`resources/kontierung_rules.yaml` verwenden (Abschnitt `skr04_mapping`).

## Haeufige Szenarien

### Reverse Charge (§13b UStG)
Erkennbar an: auslaendischer Lieferant, "Reverse Charge" Vermerk, §13b Hinweis.
Vorsteuer auf Konto 1577 (statt 1576). Das Kontierung-Script erkennt dies mit
dem `--reverse-charge` Flag.

### Kleinbetragsrechnung (§33 UStDV)
Bruttobetrag <= 250 EUR. Reduzierte Pflichtangaben. Wird automatisch erkannt.

### Mehrere MwSt-Saetze
Rechnung mit gemischten Saetzen (z.B. 19% und 7%). Jede Position wird separat
mit dem passenden Vorsteuer-Konto gebucht (1576 fuer 19%, 1571 fuer 7%).

### GWG-Pruefung
IT-Equipment unter 800 EUR netto → Konto 4985 (GWG, §6 Abs. 2 EStG).
Ueber 800 EUR → Anlagevermoegen (0420), Abschreibung ueber Nutzungsdauer.

## Bisherige Buchungen anzeigen

```bash
python <SKILL_DIR>/scripts/booking.py list --workspace .bookkeeping [--limit 20] [--supplier "Name"]
```

## Scripts-Referenz

| Script | Zweck |
|--------|-------|
| `scripts/compliance.py` | §14 UStG Pflichtfeld-Pruefung |
| `scripts/kontierung.py` | Regelbasierte Kontozuordnung + Confidence |
| `scripts/booking.py` | Buchung speichern, Regeln lernen, Audit Log |

Alle Scripts lesen JSON von `--input` oder stdin und geben JSON auf stdout aus.
