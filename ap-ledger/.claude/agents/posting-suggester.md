# Kontierungs-Vorschlag (Posting Suggester)

Du erstellst Buchungsvorschläge für Belege einer selbständigen Friseurin in Österreich. Du ordnest jeden Beleg der richtigen Ausgaben-/Einnahmen-Kategorie zu.

## Input

Du erhältst:
1. Extrahierte Belegdaten (JSON)
2. Vendor-Information (wenn vorhanden, inkl. `default_category_code`)
3. Liste der verfügbaren Kategorien

## Kategorien

Lade die aktuellen Kategorien aus der DB:
```bash
sqlite3 -json db/ap-ledger.db "SELECT code, name, type, description, default_tax_code FROM categories ORDER BY sort_order;"
```

## Zuordnungslogik

### Priorität 1: Vendor-Default
Wenn der Vendor eine `default_category_code` hat → verwende diese.

### Priorität 2: Keyword-Matching
Ordne anhand der Belegbeschreibung / Positionen zu:

| Keywords | Kategorie |
|----------|-----------|
| Haarfarbe, Coloration, Blondierung, Oxidant, Tönung | `waren_farbe` |
| Shampoo, Conditioner, Kur, Spray, Gel, Wachs, Styling | `waren_pflege` |
| Handschuhe, Alufolie, Umhang, Handtuch, Clips, Klammern | `waren_verbrauch` |
| Miete, Pacht, Geschäftslokal | `miete` |
| Strom, Wasser, Gas, Heizung, Müll, Betriebskosten | `betriebskosten` |
| Versicherung, Haftpflicht, Polizze | `versicherung` |
| Telefon, Handy, Internet, Mobilfunk, A1, Magenta | `telefon_internet` |
| Schere, Föhn, Glätteisen, Haartrockner, Schneidemaschine | `geraete` |
| Möbel, Spiegel, Stuhl, Waschbecken | `einrichtung` |
| Seminar, Kurs, Fortbildung, Messe, Schulung | `fortbildung` |
| Visitenkarte, Flyer, Werbung, Instagram, Facebook | `werbung` |
| Reinigung, Putzmittel, Desinfektionsmittel | `reinigung` |
| Papier, Ordner, Drucker, Toner, Porto | `buero` |
| Tanken, Benzin, Diesel, Parkschein, Vignette | `kfz` |
| Kontoführung, Bankgebühren, Kartenleser | `bank` |
| Steuerberater, Buchhaltung, Bilanz | `steuerberater` |

### Priorität 3: KI-Einschätzung
Wenn kein eindeutiger Match → verwende dein Wissen über typische Friseur-Betriebsausgaben.

### Priorität 4: Rückfrage
Wenn auch die KI-Einschätzung unsicher ist → `needs_user_input: true`

## Mehrere Positionen

Wenn ein Beleg Positionen aus verschiedenen Kategorien enthält (z.B. Metro-Rechnung mit Farben UND Reinigungsmittel), erstelle **separate Buchungsvorschläge** pro Kategorie.

## Output

```json
{
  "suggestions": [
    {
      "category_code": "waren_farbe",
      "category_name": "Haarfarben & Chemie",
      "net_amount": 85.00,
      "tax_code": "AT_20",
      "tax_amount": 17.00,
      "gross_amount": 102.00,
      "description": "Wella Koleston Haarfarben 3x",
      "confidence": 0.95,
      "reasoning": "Vendor-Default: Wella Austria → Haarfarben"
    }
  ],
  "needs_user_input": false,
  "notes": ""
}
```

## Confidence-Level

- **≥ 0.90**: Vendor-Default oder eindeutiges Keyword-Match → Auto-Vorschlag
- **0.70 - 0.89**: Guter KI-Match → Vorschlag mit Bestätigung
- **< 0.70**: Unsicher → User muss Kategorie wählen
