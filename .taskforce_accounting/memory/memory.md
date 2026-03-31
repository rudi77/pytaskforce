id: a1b2c3d4e5f647a8b9c0d1e2f3a4b5c6
scope: profile
kind: preference
content: |
  # Kunden-Konfiguration: Tina (Friseursalon)

  ## Allgemein
  - Kundenname: Tina
  - Branche: Friseursalon (Kleingewerbe)
  - Standort: Teisendorf, Bayern
  - Steuerregelung: Kleinunternehmer (keine USt-Ausweisung, keine Vorsteuer)
  - Kontenrahmen: Nicht relevant (einfache Einnahmen-Ueberschuss-Rechnung, kein SKR03/SKR04)
  - Buchhaltungsart: Einfache EUeR mit Excel-Kassenbuch

  ## Kategorien
  - Einnahmen
  - Wareneinsatz
  - Friseurmaterial
  - Miete
  - Strom
  - Werbung
  - Sonstiges

  ## Ordnerstruktur (absolute Pfade, verbindlich)
  - Basispfad: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\
  - Eingang PDF: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\01_Eingaenge\Rechnungen_PDF\
  - Eingang Bilder: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\01_Eingaenge\Rechnungen_Bilder\
  - Eingang Einnahmen Screenshots: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\01_Eingaenge\Einnahmen_Screenshots\
  - Eingang Einnahmen Text: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\01_Eingaenge\Einnahmen_Text\
  - Verarbeitet Ausgaben: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\02_Verarbeitet\Ausgaben\
  - Verarbeitet Einnahmen: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\02_Verarbeitet\Einnahmen\
  - Excel: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\03_Excel\Buchhaltung_Tina.xlsx
  - Export Steuerberater: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\04_Export_Steuerberater\
  - Auswertungen: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\05_Auswertungen\
  - Unklar: C:\Users\rudi\Documents\Private\Tina\Buchhaltung\99_Unklar\

  ## Excel-Spalten (Buchhaltung_Tina.xlsx)
  Datum | Typ | Kategorie | Beschreibung | Betrag brutto | Betrag netto | Umsatzsteuer | Steuersatz | Zahlungsart | Belegnummer | Lieferant/Kunde | Datei-/Belegname | Ordnerpfad | Bemerkung | Status

  ## Ablageregeln
  - Ausgaben-Belege NUR nach 02_Verarbeitet\Ausgaben\ (niemals direkt in 02_Verarbeitet\)
  - Einnahmen-Belege NUR nach 02_Verarbeitet\Einnahmen\ (niemals direkt in 02_Verarbeitet\)
  - Dateiname-Muster: YYYY-MM-DD_Lieferant_Beschreibung.ext
  - In Excel-Spalte Ordnerpfad immer den vollstaendigen absoluten Pfad eintragen

  ## OCR-Strategie
  - Text-PDFs: pypdf direkt
  - Gescannte PDFs/Bilder: docling via extract_text_with_ocr.py
  - Falls OCR scheitert: Beleg nach 99_Unklar verschieben

  ## Fehlerbehandlung
  - Unlesbare Dateien: nach 99_Unklar verschieben
  - Fehlende Felder: Benutzer fragen, nicht raten
  - Mehrdeutige Belege: als "Unklar" markieren
tags:
  - accounting_config
  - onboarding
  - tina
  - friseursalon
  - kleinunternehmer
metadata:
  source: migrated_from_skill
  customer: tina
  migrated_from: .taskforce/skills/tina-buchhaltung/SKILL.md
  migration_date: '2026-03-30'
created_at: '2026-03-30T12:00:00+00:00'
updated_at: '2026-03-30T12:00:00+00:00'
strength: 1.0
access_count: 0
emotional_valence: neutral
importance: 1.0
associations: []
decay_rate: 0.0
