---
name: euer-export
type: prompt
description: EÜR-Report oder CSV-Export für den Steuerberater generieren
trigger: REPORT_REQUEST
---

# EÜR-Export generieren

Erstelle einen Report basierend auf der Anfrage: $ARGUMENTS

Verfügbare Reports (via powershell-Tool):
- **Monatsübersicht**: `python examples/ap_ledger_agent/scripts/euer_report.py --action monthly`
- **EÜR-Aufschlüsselung**: `python examples/ap_ledger_agent/scripts/euer_report.py --action euer --year <jahr>`
- **CSV-Export**: `python examples/ap_ledger_agent/scripts/euer_report.py --action csv --year <jahr>`
- **Offene Belege**: `python examples/ap_ledger_agent/scripts/euer_report.py --action open`

Formatiere das Ergebnis übersichtlich als Tabelle.
