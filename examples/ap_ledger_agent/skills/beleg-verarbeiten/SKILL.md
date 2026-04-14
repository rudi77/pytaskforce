---
name: beleg-verarbeiten
type: context
description: Beleg (Foto/PDF) verarbeiten und in der EÜR verbuchen
trigger: INVOICE_PROCESSING
---

# Beleg verarbeiten

Du verarbeitest jetzt einen Beleg. Arbeite den kompletten Workflow ab:

1. **Extrahiere** alle Daten aus dem Beleg (Lieferant, Datum, Beträge, Positionen)
2. **Suche den Vendor**:
   ```powershell
   python examples/ap_ledger_agent/scripts/vendor_resolve.py --vendor-name "..."
   ```
3. **Ermittle die Periode**:
   ```powershell
   python examples/ap_ledger_agent/scripts/period_resolve.py --date "..."
   ```
4. **Validiere**: Pflichtfelder, Betrags-Plausibilität, USt-Satz
5. **Kontierung**: Ordne die richtige Kategorie zu
6. **Bestätigung**: Zeige Zusammenfassung, frage User via `ask_user`
7. **Speichern**:
   ```powershell
   python examples/ap_ledger_agent/scripts/invoice_persist.py --vendor-name-raw "..." --invoice-date "..." --total-gross ... --lines-json "[...]"
   ```
8. **Buchen**:
   ```powershell
   python examples/ap_ledger_agent/scripts/journal_persist.py --invoice-id ... --entry-date "..." --description "..." --lines-json "[...]"
   python examples/ap_ledger_agent/scripts/journal_post.py --journal-id ...
   ```
9. **Audit**:
   ```powershell
   python examples/ap_ledger_agent/scripts/audit_log.py --event-type invoice_posted --entity-type invoice --entity-id ...
   ```

Überspringe KEINEN Schritt. Bei Confidence < 95% oder Hard Gates MUSS der User bestätigen.
Bei Confidence >= 95% mit bekanntem Vendor und Betrag < 1000€ wird automatisch gebucht.
