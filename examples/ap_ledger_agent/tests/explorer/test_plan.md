# AP-Ledger Exploratory Test Plan

**Scope:** MVP-A Phase-A (Happy Path + elementare Korrektur- und Report-Pfade).
**Default-Setup pro Szenario:** frischer Kunde via `provision_customer.py`,
Country AT, `AP_LEDGER_CUSTOMER_NAME="Explorer Testlauf"`, Heute-Datum = 2026-04-17.

Status-Legende: `[ ]` offen · `[x]` durchlaufen (Ergebnis im Report) · `[!]` Blocker (stopt Loop).

---

## 1 Happy Path — Buchen

- [x] **S01 — Tageslosung bar buchen (Text).** Neue Kundin schickt „186 EUR Tageslosung heute". Ausgewählt ist AT (20% USt).
  **Expected:** Genau 1 `invoices`-Row, `type=receipt`, `status=posted`, `total_gross=186.00`, `total_net=155.00`, `total_tax=31.00`. Genau 1 `journal_entries`-Row, `status=posted`. Audit-Log enthält Einträge vom Typ `invoice.posted` und `journal.posted`.

- [x] **S02 — Barumsatz + Karteneinnahme gemischt.** „Heute 300 bar, 150 Karte, Tageslosung".
  **Expected:** 2 `invoices`-Rows (oder 1 mit 2 Lines — beide Varianten zulässig, Dokumentation im Report). `total_gross` summiert 450.00. Journal-Entries balanciert (Soll = Haben).

- [x] **S03 — Ausgabe buchen (Text).** „Wella Haarfarbe 119 EUR, Datum 14.04.2026".
  **Expected:** 1 `invoices`-Row, `type=invoice`, `status=posted`, Vendor `Wella` angelegt oder gematcht, `category_code=waren_farbe` (oder vergleichbare Plausibilität), `total_gross=119.00`, USt gemäß Land.

- [x] **S04 — Drei Buchungen nacheinander (Streaming-Regression).** S01 → S01 (mit anderem Betrag) → S03 hintereinander in derselben Session.
  **Expected:** Alle 3 Buchungen landen, keine verschluckten, kein Duplikat-Fehler, Audit-Log lückenlos.

## 2 Reports

- [x] **S05 — Leerer Monatsreport.** Ohne eine einzige Buchung: „Schick mir Monatsreport April 2026".
  **Expected:** Agent antwortet klar „keine Buchungen" und sendet **kein** PDF. Kein Crash, kein leeres PDF mit Null-Zeilen-Garnitur.

- [ ] **S06 — Jahresreport nach 3 Buchungen.** S01 + S01 (ein anderer Tag) + S03, dann „Jahresreport 2026".
  **Expected:** PDF generiert, Titel enthält Customer-Name aus `AP_LEDGER_CUSTOMER_NAME`, Einnahmensumme / Ausgabensumme / Gewinn / USt-Saldo matchen die Summen der Buchungen bis auf 1 Cent, Anzahl Belege = 3.

## 3 Korrekturen

- [ ] **S07 — Nachträgliche Korrektur eines Betrags.** S01 buchen (186 EUR). Dann „Das war falsch, es waren 168 EUR, bitte korrigieren".
  **Expected:** Ursprünglicher Eintrag bleibt im Audit-Log sichtbar (immutable). Effektive Monatssumme = 168 EUR, nicht 186. Journal-History zeigt Storno + Neubuchung oder direkte Korrektur (beides zulässig, muss im Report dokumentiert werden).

- [ ] **S08 — Consistency-Check nach Korrektur.** Nach S07: `consistency_check.py` manuell ausführen.
  **Expected:** `{"success": true, "clean": true}`. Keine Warnungen, keine unbalancierten Journale.

---

## Runde 2 (werden wir erweitern wenn Runde 1 sauber)

Ideen für Runde 2 — bitte **nicht jetzt** ausführen, erst nach Runde-1-Review:

- Vision-Extraktion mit echten Beleg-Bildern (Clean-JPG + Blurry-JPG + PDF mit OCR)
- Edge amounts: 0.00 / negativ / sehr groß / 3+ Nachkommastellen
- Concurrency: zwei Missions parallel via asyncio
- Telegram File-Größen (ohne Telegram-Layer — simuliert via 50 MB Dummy-PDF)
- Kunde löscht versehentlich Nachricht → DB-Zustand vs. Conversation-History-Desync
- Fresh-Boot nach DB-Crash (WAL rollback)

---

## Konfigurations-Notizen

- Wenn `AZURE_API_KEY` / `AZURE_API_BASE` / `AZURE_API_VERSION` nicht gesetzt sind, bricht das Harness vor dem ersten Call mit klarer Message ab (keine fake LLM-Calls).
- Tests laufen in `%TEMP%\blubot-explorer-<slug>\` — werden nach Erfolg aufgeräumt, bei Fehler behalten damit nachgeforscht werden kann. Report muss den Pfad vermerken.
