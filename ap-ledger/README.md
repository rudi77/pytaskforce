# AP-Ledger: Beleg-zu-Buchung mit Claude Code CLI

Einfache Buchhaltung für Einzelunternehmer in Österreich. Foto vom Beleg schicken, bestätigen, fertig.

## Architektur

```
Telegram (Handy)
      ↓
telegram_bot.py  →  speichert Foto/PDF
      ↓
claude_runner.py →  ruft `claude` CLI als Subprocess
      ↓
CLAUDE.md        →  orchestriert Subagents
      ↓
SQLite           →  Belege, Buchungen, Audit
      ↓
telegram_bot.py  →  schickt Zusammenfassung zurück
```

**Kernidee:** Claude Code CLI **ist** die Workflow-Engine. Der `CLAUDE.md` Prompt definiert den Prozess, Subagents führen KI-Schritte aus, Shell-Scripts erledigen deterministische DB-Operationen.

## Für wen?

Eine selbständige Friseurin in Österreich. Typische Belege:
- Kassenbons vom Friseur-Großhändler (Farben, Shampoo)
- Rechnungen (Miete, Strom, Versicherung)
- Kleinmaterial (Amazon, DM)

Der Steuerberater bekommt am Jahresende einen CSV-Export.

## Projektstruktur

```
ap-ledger/
├── CLAUDE.md                     # Orchestrator-Prompt (= die Workflow-Engine)
├── .claude/agents/
│   ├── extractor.md              # Beleg → strukturierte Daten
│   ├── validator.md              # Fachliche Validierung
│   ├── posting-suggester.md      # Kontierungsvorschlag
│   ├── ledger-builder.md         # Journal-Eintrag aufbauen
│   └── reviewer.md               # Prüfung & Korrektur
├── scripts/
│   ├── init-db.sh                # DB initialisieren
│   ├── resolve-vendor.sh         # Lieferant suchen
│   ├── resolve-period.sh         # Geschäftsperiode finden
│   ├── resolve-tax.sh            # Steuersatz auflösen
│   ├── create-vendor.sh          # Neuen Lieferant anlegen
│   ├── persist-invoice.sh        # Beleg speichern
│   ├── persist-journal.sh        # Buchungssatz speichern
│   ├── post-journal.sh           # Buchung finalisieren
│   └── write-audit.sh            # Audit-Log schreiben
├── db/
│   ├── schema.sql                # Datenbank-Schema
│   ├── seed-data.sql             # Kategorien, Steuersätze, Lieferanten
│   └── ap-ledger.db              # (wird beim Start erzeugt)
├── telegram_bot.py               # Telegram Bot
├── claude_runner.py              # Claude CLI Subprocess-Wrapper
├── requirements.txt              # Python Dependencies
├── .env.example                  # Umgebungsvariablen-Template
└── invoices/                     # Eingehende Belege (Fotos/PDFs)
```

## Setup

### Voraussetzungen

- Python 3.11+
- SQLite 3
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installiert und konfiguriert
- Telegram Account

### 1. Dependencies installieren

```bash
cd ap-ledger
pip install -r requirements.txt
```

### 2. Telegram Bot erstellen

1. Öffne Telegram und suche `@BotFather`
2. Sende `/newbot` und folge den Anweisungen
3. Kopiere das Bot-Token

### 3. Konfiguration

```bash
cp .env.example .env
# .env editieren und Tokens eintragen
```

### 4. Datenbank initialisieren

```bash
bash scripts/init-db.sh
```

### 5. Bot starten

```bash
source .env
python telegram_bot.py
```

## Benutzung

### Beleg verbuchen

1. Foto vom Beleg machen (oder PDF schicken)
2. An den Bot senden
3. Bot zeigt Zusammenfassung:
   ```
   📋 Beleg erkannt

   🏪 Wella Austria
   📅 2025-03-15
   💰 102,00 € brutto
      (85,00 € netto + 17,00 € USt)
   📁 Kategorie: Haarfarben & Chemie
   🟢 Sicherheit: 92%

   ✅ Passt  |  ✏️ Korrigieren  |  ❌ Ablehnen
   ```
4. Tap auf ✅ → Beleg ist verbucht

### Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `/start` | Begrüßung |
| `/status` | Offene Belege anzeigen |
| `/monat` | Monatsübersicht |
| `/export` | CSV-Export für Steuerberater |
| `/kategorien` | Alle Kategorien anzeigen |
| `/help` | Hilfe |

### Korrekturen

Wenn der Bot falsch liegt:
- Tap auf ✏️ Korrigieren
- Schreib z.B. "Kategorie: Reinigung" oder "Betrag: 45,90"
- Bot zeigt die korrigierte Version

## Workflow-Details

### Deterministische Steps (Shell-Scripts)

- **resolve-vendor.sh**: Sucht Lieferant in DB (exact match → LIKE → keyword)
- **resolve-period.sh**: Findet/erstellt Geschäftsperiode für ein Datum
- **resolve-tax.sh**: Löst österreichischen Steuercode auf
- **persist-invoice.sh**: Beleg + Positionen in DB schreiben
- **persist-journal.sh**: Buchungssatz mit Soll/Haben-Prüfung
- **post-journal.sh**: Buchung finalisieren (draft → posted)
- **write-audit.sh**: Unveränderlicher Audit-Log Eintrag

### KI-basierte Steps (Subagents)

- **extractor.md**: Liest Beleg-Bild/PDF, extrahiert strukturierte Daten
- **validator.md**: Prüft Pflichtfelder, Betrags-Plausibilität, Duplikate
- **posting-suggester.md**: Ordnet die richtige Kategorie zu
- **ledger-builder.md**: Erstellt den Buchungssatz (Soll/Haben)
- **reviewer.md**: Finale Qualitätsprüfung

### HITL (Human-in-the-Loop)

Claude fragt über Telegram direkt nach:
- Neuer Lieferant → "Welche Kategorie?"
- Unsichere Kategorie → Auswahloptionen
- Jeder Beleg → Bestätigung vor Buchung

## Österreich-spezifisch

### Steuersätze

| Code | Satz | Beschreibung |
|------|------|--------------|
| AT_20 | 20% | Normalsteuersatz |
| AT_10 | 10% | Ermäßigt (Lebensmittel, Bücher) |
| AT_13 | 13% | Speziell (Blumen, Kunst) |
| AT_0 | 0% | Befreit (Versicherung) |
| EU_RC | 0% | Reverse Charge (EU) |

### Kleinbetragsrechnung

Belege ≤ 400 € haben vereinfachte Anforderungen (§ 11 Abs. 6 UStG):
- Kein Empfänger-Name nötig
- Bruttobetrag genügt

### EÜR (Einnahmen-Überschuss-Rechnung)

Buchung nach dem Zufluss-/Abfluss-Prinzip.

## Standalone-Nutzung (ohne Telegram)

Claude Code CLI kann auch direkt verwendet werden:

```bash
cd ap-ledger
claude  # Startet den interaktiven Modus, CLAUDE.md wird geladen
```

Dann im Chat:
```
Verarbeite den Beleg invoices/rechnung_001.pdf
```

Oder direkt:
```bash
python claude_runner.py invoices/kassenbon.jpg
```
