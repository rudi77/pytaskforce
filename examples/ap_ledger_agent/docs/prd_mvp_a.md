# PRD — AP-Ledger MVP-A ("Concierge-Pilot")

**Version:** 0.1 (Draft)
**Datum:** 2026-04-17
**Owner:** Rudi Dittrich
**Status:** Proposal — awaiting approval

---

## 1. Produkt-Pitch (1 Satz)

> „Mach ein Foto vom Beleg in Telegram — am Monatsende bekommst du einen fertigen EÜR-Report und ein ZIP mit allen Belegen. Keine Software, kein Setup, kein Excel."

## 2. Zielkunde (sehr eng)

**Primär:** EPU/Freelancer in AT & DE mit EÜR (Einnahmen-Überschuss-Rechnung) und **< 50 Belegen/Monat**.
Typisch: Designerin, Coach, Friseurin, Entwickler, Fotografin, Beraterin.

**Abgrenzung** — *nicht* Zielkunde:
- Unternehmen mit doppelter Buchführung / Bilanzierung
- Handel mit Wareneingang/Lagerhaltung
- Kunden, die bereits sevDesk/Lexware/FastBill nutzen und zufrieden sind
- Agenturen mit Mitarbeitern / Lohnbuchhaltung

## 3. Problem (was der Kunde heute tut)

- Belege werden in Schuhkarton / Apple Notes / WhatsApp-Chat mit sich selbst gesammelt
- Einmal im Jahr: 2 Tage Excel-Orgie vor Steuerberater-Termin
- Oder: 3 fehlgeschlagene Anläufe mit sevDesk, weil „zu kompliziert für das bisschen"
- Steuerberater schickt immer wieder Rückfragen („Was war diese 47 € vom 12.3.?")

## 4. MVP-Scope

### 4.1 Was der Kunde bekommt — IN-SCOPE

| Feature | Status heute | MVP-A |
|---|---|---|
| Telegram-Bot: Foto → Buchung | vorhanden | übernehmen |
| Vision-Extraktion (Vendor, Betrag, USt) | vorhanden | übernehmen |
| Bestätigungs-Dialog vor Buchung | vorhanden | übernehmen |
| Beleg-Archiv (strukturiert, `belege/YYYY/MM/`) | vorhanden | übernehmen |
| Monatsübersicht als PDF (Einnahmen/Ausgaben/USt-Saldo) | fehlt | **BAUEN** |
| Jahres-EÜR-Report als PDF (verkaufswürdig) | nur CSV | **BAUEN** |
| Belege-ZIP-Export (alle Belege eines Jahres) | fehlt | **BAUEN** |
| Steuerberater-CSV (wie heute) | vorhanden | übernehmen |
| Storno/Korrektur via Telegram | vorhanden | übernehmen |

### 4.2 Was der Kunde NICHT bekommt — OUT-OF-SCOPE

- Web-Dashboard (Telegram ist das einzige Interface)
- Self-Service-Signup (Onboarding macht Rudi manuell)
- DATEV-Export (kommt in MVP-B)
- USt-Voranmeldung (Kleinunternehmer sind häufig UID-befreit)
- Bankabgleich / MT940 / CAMT
- Mehrbenutzer / Team-Features
- Mobile App (Telegram IST die App)

### 4.3 Operations-Scope (Rudi als Concierge)

- **Onboarding:** 30-min Call, Rudi deployed Bot + DB auf Hetzner-Server, sendet Bot-Link
- **Support:** E-Mail/Telegram-DM, max 2 Stunden/Kunde/Monat einkalkuliert
- **Backup:** Tägliches SQLite-Backup + verschlüsseltes Off-Site (Hetzner Storage Box)
- **Monatsreport:** Auto-generiert am 1. des Folgemonats, per E-Mail zugestellt

## 5. Pricing & Packaging

| Plan | Preis | Inkludiert |
|---|---|---|
| **Early Bird (Pilot)** | **€19/Monat** oder **€189/Jahr** | Alles in MVP-A, bis 50 Belege/Monat |
| Lock-in | 12 Monate zum Early-Bird-Preis garantiert | Auch wenn regulärer Preis später €29 wird |

**Zahlung:** Stripe Payment Link (keine Integration nötig), monatliche Rechnung automatisch.

**Refund:** 30-Tage-Geld-zurück ohne Begründung.

## 6. Erfolgskriterien (nach 3 Monaten)

| Metrik | Ziel |
|---|---|
| Zahlende Kunden | ≥ 3 |
| Monatlicher Recurring Revenue | ≥ €60 |
| Churn nach 3 Monaten | ≤ 1 Kunde |
| Belege/Kunde/Monat (Median) | ≥ 15 (= aktive Nutzung) |
| Testimonials / Referenzen | ≥ 2 schriftlich |

**Abbruchkriterium:** Wenn nach 3 Monaten < 2 zahlende Kunden → Produkt-Hypothese falsch, zurück ans Whiteboard.

## 7. 6-Wochen-Plan

| Woche | Tech-Arbeit | Non-Tech-Arbeit |
|---|---|---|
| **1** | Monatsreport-PDF (ReportLab-Template) | Kundenliste: 10 Kandidaten aus Netzwerk anschreiben |
| **2** | Jahres-EÜR-PDF + Belege-ZIP-Export | Landingpage (1 Seite, Framer/Carrd) + Stripe Payment Link |
| **3** | Deploy-Skripte (1 Befehl → neuer Kunde live) | Legal-Templates kaufen (IT-Recht-Kanzlei, ~€100): Impressum, AGB, DSE, AVV |
| **4** | Auto-Backup-Cronjob + E-Mail-Versand Monatsreport | Pilot-Call #1 & #2 (Onboarding) |
| **5** | Bugfixes aus Pilot-Feedback | Pilot-Call #3 + Testimonial-Collection |
| **6** | Puffer + Feintuning | Preisvalidierung: von €19 auf €29 testen beim nächsten Kunden |

## 8. Technische Neubau-Liste (präzise)

1. **`scripts/report_monthly_pdf.py`** — generiert Monatsreport-PDF (Einnahmen, Ausgaben, USt-Saldo, Top-10-Ausgaben-Kategorien)
2. **`scripts/report_annual_eur_pdf.py`** — Jahres-EÜR-Report als PDF (Titelseite, Übersicht, Detailauflistung, Unterschriftsfeld)
3. **`scripts/export_belege_zip.py`** — ZIP aller Belege eines Zeitraums inkl. Index-PDF
4. **`deploy/provision_customer.sh`** — 1-Befehl-Deployment: neuer Kunde = neue DB + neuer Bot-Token + systemd-Unit
5. **`deploy/backup.sh`** — Cronjob: SQLite `.backup` + Belege-Verzeichnis → rclone → Hetzner Storage Box (verschlüsselt)
6. **`scripts/send_monthly_report.py`** — Cronjob am 1. d.M.: für jeden Kunden Monatsreport generieren + per SMTP senden

**Dependencies:** `reportlab` (PDF), `rclone` (Backup), SMTP-Provider (Brevo/Postmark ~€0–10/Monat).

## 9. Non-Tech-Arbeit

- [ ] Domain kaufen (Vorschlag: `belegbot.at` / `belegbot.de` oder `kassenbon.ai`)
- [ ] Landingpage (Carrd, €19/Jahr) — 1 Headline, 3 Screenshots aus Telegram, 1 Preis, 1 CTA
- [ ] Stripe-Account + Payment Link (€19/Monat + €189/Jahr)
- [ ] Legal-Paket: IT-Recht-Kanzlei oder eRecht24 (~€100 einmalig)
- [ ] DSGVO: AVV-Template anpassen (du bist Auftragsverarbeiter für Belegdaten)
- [ ] E-Mail-Adresse (`hallo@...`)
- [ ] Hetzner-Server (CX22 = €4/Monat reicht für 20 Kunden)
- [ ] Bot-Strategie-Entscheidung: 1 Bot für alle vs. 1 Bot pro Kunde (siehe §10)

## 10. Offene Fragen (Entscheidung durch Rudi)

1. **Ein Bot für alle Kunden (Multi-Tenant über Telegram-User-ID) ODER ein dedizierter Bot pro Kunde?**
   - *Geteilt:* Einfacher zu hosten, 1 Codebase. Aber: wenn dein Bot-Token kompromittiert wird → alle Kunden betroffen.
   - *Pro Kunde:* Jeder Kunde hat eigenen Bot-Namen („Anna-Belege-Bot"), isoliert, persönlicher. Aber: mehr Ops-Aufwand.
   - **Empfehlung:** Dedizierter Bot pro Kunde für MVP-A (max 10 Kunden, Aufwand noch klein, Isolation wertvoll für Vertrauen).

2. **Wo läuft das?** Hetzner (Deutschland, DSGVO-einfach) vs. Eigener Server zu Hause.
   - **Empfehlung:** Hetzner CX22 in Falkenstein, €4/Monat.

3. **Monatsreport per E-Mail oder Telegram?**
   - **Empfehlung:** Beides — PDF per E-Mail (offizielle Paper-Trail), Kurzfassung per Telegram-Nachricht.

4. **Zielmarkt zuerst: AT, DE oder beide?**
   - **Empfehlung:** AT zuerst (dein Heimmarkt, Netzwerk vorhanden, EPU-Regelung klar). DE in Phase 2.

5. **Positionierung: „KI-Buchhaltung" vs. „Belegsammler mit Report"?**
   - *KI:* zieht Hype-Kunden, aber hohe Erwartung. Risiko: Kunde denkt es ist Lexware-Ersatz.
   - *Belegsammler:* ehrlicher, unterverkauft das Produkt, aber niedrigere Enttäuschungs-Rate.
   - **Empfehlung:** „Der einfachste Weg, Belege für den Steuerberater zu sammeln" (Problem-first, nicht Tech-first).

## 11. Risiken & Mitigation

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|
| Vision-Extraktion falsch → falsche Buchung | Mittel | Hoch | Immer `ask_user`-Bestätigung vor Buchung; Korrektur-Flow vorhanden |
| Telegram-API-Ausfall | Niedrig | Mittel | SLA-Disclaimer in AGB; E-Mail-Fallback für Monatsreport |
| Steuerberater akzeptiert CSV nicht → DATEV-Forderung | Mittel | Mittel | DATEV-Export als Phase-2-Feature versprechen; Pilot-Kunden vorab fragen |
| DSGVO-Verletzung (Belege = pers.-bezogene Daten) | Niedrig | Hoch | Hetzner + Verschlüsselung + AVV-Template + Löschroutine nach Vertragsende |
| Rudi = Single Point of Failure bei Support | Hoch | Niedrig (bei 5 Kunden) | Bei > 10 Kunden: FAQ-Bot + Notion-Runbook |

---

## 12. Nächste Schritte (Entscheidung durch Rudi)

**Sofort zu entscheiden:**
- [ ] Offene Fragen §10 (Bot-Strategie, Hosting, Zielmarkt, Positionierung)
- [ ] Go / No-Go für den 6-Wochen-Plan

**Nach Go:**
- [ ] Woche 1 starten → Monatsreport-PDF prototypen
- [ ] Parallel: Rudi definiert 10 Pilotkunden-Kandidaten aus Netzwerk

---

*Dieses PRD ist bewusst eng gehalten. Alles was nicht drin steht → Phase 2 (MVP-B).*
