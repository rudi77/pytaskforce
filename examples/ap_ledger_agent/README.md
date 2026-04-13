# AP Ledger Agent — Taskforce Plugin

Beleg-zu-Buchung Workflow für österreichische Einzelunternehmer (EÜR). Taskforce ist der Orchestrator — der Agent verarbeitet Belege (Fotos, PDFs, Kassenbons) und erstellt Buchungssätze in SQLite.

## Architektur

```
Telegram / CLI
      ↓
Taskforce Agent (ap_ledger_agent Profile)
      ↓
Plugin Tools (9 spezialisierte Tools)
      ↓
SQLite DB (Belege, Buchungen, Audit)
      ↓
HITL via ask_user / Communication Gateway
```

**Taskforce orchestriert den gesamten Workflow.** Der System-Prompt im Profil-YAML definiert den 10-Schritt-Prozess, die Plugin-Tools erledigen alle DB-Operationen, und HITL läuft über das native `ask_user` Tool mit Channel-Routing (CLI oder Telegram).

## Projektstruktur

```
ap_ledger_agent/
├── ap_ledger_agent/               # Python-Paket (Plugin)
│   ├── __init__.py
│   ├── domain/
│   │   ├── models.py              # Invoice, JournalEntry, Vendor, etc.
│   │   └── errors.py              # Custom exceptions
│   ├── tools/
│   │   ├── __init__.py            # Exportiert alle Tools (__all__)
│   │   ├── vendor_resolve_tool.py # Lieferant suchen/anlegen
│   │   ├── period_resolve_tool.py # Geschäftsperiode ermitteln
│   │   ├── tax_resolve_tool.py    # Steuersatz auflösen
│   │   ├── invoice_persist_tool.py# Beleg + Positionen speichern
│   │   ├── journal_persist_tool.py# Buchungssatz erstellen
│   │   ├── journal_post_tool.py   # Buchung finalisieren
│   │   ├── audit_log_tool.py      # Audit-Log schreiben
│   │   └── euer_report_tool.py    # Reports und CSV-Export
│   └── infrastructure/
│       └── sqlite_store.py        # SQLite-Persistenz
├── configs/
│   ├── ap_ledger_agent.yaml       # Profil (System-Prompt + Tool-Wiring)
│   └── accounting/rules/
│       └── compliance_rules_at.yaml # § 11 UStG Compliance-Regeln
├── db/
│   ├── schema.sql                 # Datenbank-Schema
│   └── seed-data.sql              # Kategorien, Steuersätze, Lieferanten
├── skills/
│   ├── beleg-verarbeiten/SKILL.md # Skill: Belegverarbeitung
│   └── euer-export/SKILL.md       # Skill: EÜR-Report
└── README.md
```

## Verwendung

### Als Taskforce Plugin

```bash
# Agent mit dem AP Ledger Profil starten
taskforce run mission "Verarbeite den Beleg invoices/rechnung.pdf" \
    --profile examples/ap_ledger_agent/configs/ap_ledger_agent.yaml

# Oder im Chat-Modus
taskforce chat --profile examples/ap_ledger_agent/configs/ap_ledger_agent.yaml
```

### Via Telegram (Communication Gateway)

Wenn der Taskforce API-Server mit Communication Gateway läuft:
1. Foto vom Beleg an den Telegram-Bot schicken
2. Agent extrahiert, validiert und schlägt Buchung vor
3. Bestätigen via Telegram-Buttons
4. Beleg ist verbucht

### Programmatisch

```python
from taskforce.application.factory import AgentFactory
from taskforce.application.plugin_loader import PluginLoader

# Plugin laden
loader = PluginLoader()
manifest = loader.discover_plugin("examples/ap_ledger_agent")
tools = loader.load_tools(manifest)

# Agent erstellen
factory = AgentFactory()
agent = await factory.create_agent(
    config="examples/ap_ledger_agent/configs/ap_ledger_agent.yaml"
)

# Mission ausführen
result = await agent.execute("Verarbeite den Beleg invoices/kassenbon.jpg")
```

## Plugin-Tools

| Tool | Beschreibung |
|------|-------------|
| `ap_vendor_resolve` | Lieferant suchen (exact → LIKE → keyword) oder anlegen |
| `ap_period_resolve` | Geschäftsperiode für ein Datum finden/erstellen |
| `ap_tax_resolve` | Österreichischen Steuersatz auflösen |
| `ap_invoice_persist` | Beleg mit Positionen speichern (+ Duplikat-Check) |
| `ap_journal_persist` | Buchungssatz erstellen (Soll=Haben-Prüfung) |
| `ap_journal_post` | Buchung finalisieren (draft → posted) |
| `ap_audit_log` | Unveränderlicher Audit-Log Eintrag |
| `ap_euer_report` | Reports: Monatsübersicht, EÜR, CSV-Export, offene Belege |

Alle Tools implementieren das Taskforce `ToolProtocol` und werden vom Plugin-Loader automatisch entdeckt.

## Datenbank

SQLite mit 8 Tabellen und 2 Views:

- **categories** — 22 Kategorien (Friseur-spezifisch)
- **tax_codes** — 5 österreichische Steuersätze
- **vendors** — 16 voreingestellte Lieferanten
- **fiscal_periods** — Monatsperioden (auto-erstellt)
- **invoices** + **invoice_lines** — Belege mit Positionen
- **journal_entries** + **journal_lines** — Buchungssätze
- **audit_log** — Unveränderlicher Audit-Trail
- **v_euer_summary** — EÜR nach Kategorien
- **v_monthly_totals** — Monatliche Einnahmen/Ausgaben/Gewinn

Die DB wird automatisch beim ersten Tool-Aufruf initialisiert.

## Workflow

```
Beleg empfangen
     ↓
1. Extraktion (Agent liest Bild/PDF)
     ↓
2. ap_vendor_resolve → Vendor matchen
     ↓
3. ap_period_resolve → Periode ermitteln
     ↓
4. Validierung (Agent prüft Pflichtfelder, Beträge)
     ↓
5. Kontierung (Agent ordnet Kategorie zu)
     ↓
6. ask_user → HITL Bestätigung
     ↓
7. ap_invoice_persist → Beleg speichern
     ↓
8. ap_journal_persist → Buchungssatz erstellen
     ↓
9. ap_journal_post → Buchung finalisieren
     ↓
10. ap_audit_log → Audit-Eintrag
```

## Österreich-spezifisch

- **USt-Sätze:** 20% (Normal), 10% (ermäßigt), 13% (speziell), 0% (befreit)
- **Kleinbetragsrechnung:** ≤ 400€ (§ 11 Abs. 6 UStG) — vereinfachte Anforderungen
- **EÜR:** Einnahmen-Überschuss-Rechnung nach dem Zufluss-/Abfluss-Prinzip
- **Compliance:** § 11 UStG 1994 — Pflichtangaben auf Rechnungen
