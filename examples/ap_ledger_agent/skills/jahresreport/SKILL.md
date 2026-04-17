---
name: jahresreport
type: prompt
description: Jahres-EÜR-Report als PDF erzeugen und per Telegram zurückschicken
trigger: REPORT_REQUEST
---

# Jahresreport generieren und zustellen

Argumente: $ARGUMENTS

Parsing:
- Erste Zahl = Jahr (z.B. "2026"). Ohne Angabe → aktuelles Jahr.
- Text nach "für" oder "von" = Mandantenname (optional, z.B. "für Anna Schmidt").

## Ablauf

1. **PDF erzeugen** via powershell:
   ```powershell
   python examples/ap_ledger_agent/deploy/skills/ap-ledger/scripts/report_annual_eur_pdf.py --year <year> [--customer "<name>"]
   ```
   Response-JSON enthält `path`, `invoice_count`, `profit`, `tax_liability`.

2. **Kurzmeldung bei leerer Datenbasis:** Wenn `invoice_count == 0`, NICHT
   senden. Antworte stattdessen: „Für <year> sind noch keine Belege gebucht."

3. **Per Telegram zustellen:**
   ```
   send_notification(
     message="📎 Jahresreport <year>\nGewinn: <profit> €, USt-Saldo: <tax_liability> €",
     attachments=["<path aus Schritt 1>"]
   )
   ```
   Beträge mit Decimal-Formatierung aus der JSON-Antwort übernehmen,
   **nicht selbst rechnen**.

4. **Bestätigung:** Nach erfolgreichem Versand kurz „✅ Jahresreport
   gesendet." antworten — nicht den PDF-Inhalt nacherzählen.

## Fehler

- Script liefert `success: false` → Fehlermeldung aus `error` zeigen, keinen Versand versuchen.
- `send_notification` liefert `success: false` → den Pfad zum PDF im Text mitteilen, damit die Userin das File ggf. manuell holen kann.
