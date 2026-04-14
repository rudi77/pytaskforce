---
name: onboarding
type: prompt
description: Ersteinrichtung - Lieferanten und Stammdaten gemeinsam mit dem Kunden anlegen
trigger: ONBOARDING
---

# Onboarding: Lieferanten einrichten

Hilf der Kundin, ihre wichtigsten Lieferanten anzulegen. Gehe die Kategorien
der Reihe nach durch und frage jeweils, welche Lieferanten sie hat.

## Ablauf

Frage die Kundin per ask_user (OHNE channel-Parameter!):

### 1. Haarfarben & Chemie
"Von welchen Lieferanten beziehst du Haarfarben und Chemie?
(z.B. Wella, L'Oreal, Schwarzkopf — oder 'keine' zum Überspringen)"

### 2. Pflegeprodukte
"Welche Lieferanten für Shampoo, Conditioner, Styling?
(z.B. Redken, Goldwell — oder 'gleich wie Farbe')"

### 3. Verbrauchsmaterial
"Woher kommt Verbrauchsmaterial? (Handschuhe, Alufolie, Umhänge)
(z.B. Friseur-Großhandel, Metro)"

### 4. Fixkosten
"Welche Fixkosten-Lieferanten hast du?
- Miete: [Vermieter]
- Strom/Gas: [Energieversorger]
- Telefon/Internet: [Anbieter]
- Versicherung: [Versicherung]"

### 5. Sonstiges
"Gibt es weitere regelmäßige Lieferanten?
(z.B. Steuerberater, Reinigungsfirma, Amazon)"

## Für jeden genannten Lieferanten

Lege ihn sofort an:
```powershell
python examples/ap_ledger_agent/scripts/vendor_resolve.py --action create --vendor-name "[Name]" --category-code "[kategorie]" --tax-code "[DE_19 oder AT_20]"
```

## Abschluss

Zeige eine Übersicht aller angelegten Lieferanten und sage:
"Fertig! Neue Lieferanten werden auch automatisch angelegt wenn du Belege schickst."
