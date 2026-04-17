---
name: belege-export
type: prompt
description: Belege eines Zeitraums als ZIP mit Index-CSV für den Steuerberater exportieren
trigger: REPORT_REQUEST
---

# Belege-ZIP für Steuerberater

Argumente: $ARGUMENTS

Parsing:
- Jahr und optional Monat aus der Anfrage erkennen.
- Ohne Angabe → aktuelles Jahr, alle Monate.
- Text nach "für" = Mandantenname (optional).

## Ablauf

1. **ZIP erzeugen** via powershell:
   ```powershell
   python examples/ap_ledger_agent/scripts/export_belege_zip.py --year <year> [--month <month>] [--customer "<name>"]
   ```
   Response-JSON: `path`, `invoice_count`, `files_included`, `files_missing`.

2. **Kurzmeldung bei Null Belegen:** Wenn `invoice_count == 0`, NICHT senden.
   Antworte: „Für <Zeitraum> sind keine Belege gebucht."

3. **Warnung bei fehlenden Dateien:** Wenn `files_missing > 0`, im Versand-Text
   erwähnen: „(<files_missing> Beleg(e) ohne archivierte Datei — siehe
   belegverzeichnis.csv)".

4. **Per Telegram zustellen:**
   ```
   send_notification(
     message="📎 Belege <Zeitraum> (<files_included>/<invoice_count> Dateien)",
     attachments=["<path aus Schritt 1>"]
   )
   ```

5. **Bestätigung:** „✅ Belege-Paket gesendet."

## Fehler

- Script liefert `success: false` → Fehler zeigen, kein Versand.
- `send_notification` liefert `success: false` → Pfad zur ZIP textlich mitteilen.
