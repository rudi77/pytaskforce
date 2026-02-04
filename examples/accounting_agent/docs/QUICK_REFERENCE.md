# Accounting Agent - Quick Reference

Schnellreferenz für Entwickler und Operatoren.

---

## Tool-Referenz

| Tool | Zweck | Wichtigste Parameter |
|------|-------|---------------------|
| `docling_extract` | PDF/Image → Markdown | `file_path` |
| `invoice_extract` | Markdown → strukturierte Daten | `markdown_text` |
| `check_compliance` | §14 UStG Validierung | `invoice_data` |
| `semantic_rule_engine` | Kontenzuordnung | `invoice_data` |
| `confidence_evaluator` | Konfidenz + Hard Gates | `booking_proposal`, `invoice_data` |
| `rag_fallback` | LLM-Vorschlag bei keinem Match | `line_item`, `vendor_name` |
| `hitl_review` | Human-in-the-Loop | `action`: create/process |
| `rule_learning` | Automatische Regelerzeugung | `action`: create_from_booking/hitl |
| `calculate_tax` | USt, AfA, GWG | `amount`, `type` |
| `audit_log` | GoBD-Protokollierung | `action`, `details` |

---

## Skills & Intents

| Intent | Skill | Zweck |
|--------|-------|-------|
| `INVOICE_QUESTION` | `invoice-explanation` | Fragen zu konkreten Rechnungen beantworten |
| `ACCOUNTING_QUESTION` | `accounting-expert` | Allgemeine Buchhaltungsfragen, Kontierung, Steuerrecht |
| `INVOICE_PROCESSING` | `smart-booking-auto` | Vollständiger Rechnungs-Workflow |
| `AUTO_SWITCH` | `smart-booking-hitl` | Manuelle Prüfung bei Unsicherheit |

---

## Entscheidungslogik

### Auto-Book vs. HITL

```
IF confidence >= 95%
   AND NOT new_vendor
   AND NOT (amount > 5000€)
   AND NOT (account IN critical_accounts)
THEN
   → AUTO_BOOK
ELSE
   → HITL_REVIEW
```

### Regel-Prioritäten

| Priorität | Quelle | Beschreibung |
|-----------|--------|--------------|
| 100 | Manuell | Vendor-Only Regeln |
| 90 | HITL | Korrektur-Regeln |
| 75 | Auto | High-Confidence Regeln |
| 50 | Manuell | Vendor+Item Regeln |
| 10 | Manuell | Legacy Categories |

---

## Konfidenz-Signale

| Signal | Gewicht | Berechnung |
|--------|---------|------------|
| `rule_type` | 25% | VENDOR_ONLY=1.0, VENDOR_ITEM=0.8, RAG=0.5 |
| `similarity` | 25% | Embedding Cosine Similarity |
| `uniqueness` | 20% | Eindeutig=1.0, Ambiguos=0.7 |
| `historical` | 15% | Regel-Erfolgsrate |
| `extraction` | 15% | OCR/Parsing-Qualität |

---

## Dateipfade

```
.taskforce_accounting/
├── kontierung_rules.yaml      # Manuelle Regeln (read)
├── learned_rules.yaml         # Gelernte Regeln (read/write)
├── booking_history.jsonl      # Buchungshistorie (append)
├── rules_history.jsonl        # Regel-Audit (append)
├── audit_log.jsonl            # Audit-Trail (append)
└── .memory/
    └── knowledge_graph.jsonl  # MCP Long-Term Memory
```

---

## Environment Variables

```bash
# Pflicht
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/

# Optional (Defaults)
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
AZURE_OPENAI_API_VERSION=2024-02-01
```

---

## Kontenrahmen (SKR03 Auszug)

| Konto | Bezeichnung | Kategorie |
|-------|-------------|-----------|
| 1571 | Vorsteuer 7% | USt |
| 1576 | Vorsteuer 19% | USt |
| 1600 | Verbindlichkeiten | Passiv |
| 1800 | Bank | Aktiv |
| 4930 | Bürobedarf | Aufwand |
| 4940 | Zeitschriften | Aufwand |
| 4985 | GWG | Aufwand |
| 6805 | EDV-Kosten | Aufwand |

---

## §14 UStG Pflichtfelder

### Vollständige Rechnung (> 250€)

1. ☐ Vollständiger Name des Leistenden
2. ☐ Vollständige Anschrift des Leistenden
3. ☐ Steuernummer oder USt-IdNr.
4. ☐ Vollständiger Name des Empfängers
5. ☐ Fortlaufende Rechnungsnummer
6. ☐ Rechnungsdatum
7. ☐ Liefer-/Leistungsdatum
8. ☐ Menge und Art der Leistung
9. ☐ Nettobetrag
10. ☐ Steuersatz
11. ☐ Steuerbetrag
12. ☐ Bruttobetrag

### Kleinbetragsrechnung (< 250€, §33 UStDV)

1. ☐ Name und Anschrift Leistender
2. ☐ Rechnungsnummer
3. ☐ Rechnungsdatum
4. ☐ Menge und Art
5. ☐ Bruttobetrag
6. ☐ Steuersatz

---

## CLI-Befehle

```bash
# Agent starten
taskforce run --profile accounting_agent "Verarbeite Rechnung invoice.pdf"

# Chat-Modus
taskforce chat --profile accounting_agent

# API Server
uvicorn taskforce.api.server:app --reload

# Tests ausführen
uv run pytest examples/accounting_agent/tests/
```

---

## Fehlerbehandlung

| Exception | Bedeutung | Aktion |
|-----------|-----------|--------|
| `InvoiceParseError` | Extraktion fehlgeschlagen | Dokumentqualität prüfen |
| `ComplianceValidationError` | Pflichtfelder fehlen | HITL für Datenkorrektur |
| `RuleEngineError` | Keine passende Regel | RAG Fallback |
| `EmbeddingError` | Azure API Fehler | Fallback auf Keywords |
| `ConfidenceError` | Bewertung fehlgeschlagen | Manuelle Prüfung |

---

## Workflow-States

```
INGESTION → VALIDATION_PENDING → RULE_MATCHING
                                      ↓
                               CONFIDENCE_CHECK
                              ↙            ↘
                    FINALIZATION      REVIEW_PENDING
                         ↓                 ↓
                    COMPLETED        RULE_LEARNING
                                          ↓
                                    FINALIZATION
```

---

## Konfiguration (accounting_agent.yaml)

```yaml
# Wichtige Parameter
workflow:
  auto_book_threshold: 0.95        # Schwelle für Auto-Buchung
  hard_gates:
    new_vendor: true               # Gate: Neuer Lieferant
    high_amount_threshold: 5000.0  # Gate: Betrag
    critical_accounts: ["1800"]    # Gate: Kritische Konten
  auto_rule_learning: true         # Automatisches Regellernen
  min_confidence_for_rule_learning: 0.95

embeddings:
  cache_enabled: true
  cache_max_size: 1000

agent:
  max_steps: 50
```

---

## Regel-YAML-Format

### Vendor-Only Regel

```yaml
vendor_rules:
  - rule_id: VR-AWS
    vendor_pattern: "amazon web services"
    target_account: "6805"
    target_account_name: "EDV-Kosten (Cloud)"
    priority: 100
    legal_basis: "§4 Abs. 4 EStG"
```

### Vendor+Item Regel

```yaml
semantic_rules:
  - rule_id: SR-OFFICE
    vendor_pattern: ".*"
    item_patterns:
      - "Bürobedarf"
      - "Schreibwaren"
    target_account: "4930"
    similarity_threshold: 0.8
    priority: 50
```

---

## API Endpoints

| Method | Path | Beschreibung |
|--------|------|--------------|
| POST | `/api/v1/invoice/process` | Rechnung verarbeiten |
| GET | `/api/v1/invoice/{id}` | Status abrufen |
| POST | `/api/v1/review/{id}/decision` | HITL-Entscheidung |
| GET | `/api/v1/rules` | Regeln auflisten |
| POST | `/api/v1/rules` | Regel erstellen |

---

## Monitoring

### Metriken

| Metrik | Beschreibung | Zielwert |
|--------|--------------|----------|
| `auto_book_rate` | Anteil automatischer Buchungen | > 80% |
| `hitl_rate` | Anteil manueller Prüfungen | < 20% |
| `avg_confidence` | Durchschnittliche Konfidenz | > 90% |
| `rule_hit_rate` | Anteil Regel-Treffer | > 85% |
| `processing_time_p95` | 95. Perzentil Verarbeitungszeit | < 30s |

### Logs

```bash
# Application Logs
tail -f .taskforce_accounting/agent.log

# Audit Trail
jq '.' .taskforce_accounting/audit_log.jsonl

# Booking History
jq '.supplier_name, .account' .taskforce_accounting/booking_history.jsonl
```

---

*Quick Reference - Version 1.0*
