---
name: monatsreport
type: prompt
description: Monatsreport als PDF erzeugen und per Telegram zurückschicken
trigger: REPORT_REQUEST
---

# Monatsreport generieren und zustellen

Argumente: $ARGUMENTS

Parsing:
- Monat und Jahr aus der Anfrage erkennen — Reihenfolge egal
  („März 2026", „3/2026", „letzter Monat", „vorigen Monat").
- Ohne Angabe → letzter abgeschlossener Monat.
- Text nach "für" = Mandantenname (optional).

## Ablauf

1. **PDF erzeugen** via powershell:
   ```powershell
   python examples/ap_ledger_agent/deploy/skills/ap-ledger/scripts/report_monthly_pdf.py --year <year> --month <month> [--customer "<name>"]
   ```
   Response-JSON: `path`, `invoice_count`, `has_data`.

2. **Kurzmeldung bei leerem Monat:** Wenn `has_data == false`, NICHT senden.
   Antworte: „Für <Monat> <Jahr> sind keine Buchungen vorhanden."

3. **Per Telegram zustellen:**
   ```
   send_notification(
     message="📎 Monatsreport <Monat> <Jahr>",
     attachments=["<path aus Schritt 1>"]
   )
   ```

4. **Bestätigung:** „✅ Monatsreport gesendet." — nicht die Zahlen wiederholen.

## Fehler

- Script liefert `success: false` → Fehler zeigen, kein Versand.
- `send_notification` liefert `success: false` → Pfad zum PDF textlich mitteilen.
