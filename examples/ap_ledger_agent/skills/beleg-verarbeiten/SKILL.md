---
name: beleg-verarbeiten
type: context
description: Beleg (Foto/PDF) verarbeiten und in der EÜR verbuchen
trigger: INVOICE_PROCESSING
---

# Beleg verarbeiten

Du verarbeitest jetzt einen Beleg. Arbeite den kompletten Workflow ab:

1. **Extrahiere** alle Daten aus dem Beleg (Lieferant, Datum, Beträge, Positionen)
2. **Suche den Vendor**: `ap_vendor_resolve(vendor_name="...")`
3. **Ermittle die Periode**: `ap_period_resolve(date="...")`
4. **Validiere**: Pflichtfelder, Betrags-Plausibilität, USt-Satz
5. **Kontierung**: Ordne die richtige Kategorie zu
6. **Bestätigung**: Zeige Zusammenfassung, frage User via `ask_user`
7. **Speichern**: `ap_invoice_persist(...)`
8. **Buchen**: `ap_journal_persist(...)` dann `ap_journal_post(...)`
9. **Audit**: `ap_audit_log(...)`

Überspringe KEINEN Schritt. Bei Confidence < 95% oder Hard Gates MUSS der User bestätigen.
Bei Confidence >= 95% mit bekanntem Vendor und Betrag < 1000€ wird automatisch gebucht.
