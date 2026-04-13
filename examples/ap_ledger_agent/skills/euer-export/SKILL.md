---
name: euer-export
type: prompt
description: EÜR-Report oder CSV-Export für den Steuerberater generieren
trigger: REPORT_REQUEST
---

# EÜR-Export generieren

Erstelle einen Report basierend auf der Anfrage: $ARGUMENTS

Verfügbare Reports:
- **Monatsübersicht**: `ap_euer_report(action="monthly")`
- **EÜR-Aufschlüsselung**: `ap_euer_report(action="euer", year=<jahr>)`
- **CSV-Export**: `ap_euer_report(action="csv", year=<jahr>)`
- **Offene Belege**: `ap_euer_report(action="open")`

Formatiere das Ergebnis übersichtlich als Tabelle.
