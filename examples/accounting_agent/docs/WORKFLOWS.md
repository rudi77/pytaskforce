# Accounting Agent - Workflow-Dokumentation

Diese Dokumentation beschreibt die Abläufe und Interaktionen zwischen den Komponenten des Accounting Agents im Detail. Sie ergänzt die Hauptdokumentation (`ARCHITECTURE.md`) mit fokussierten Sequenz- und Timing-Diagrammen.

---

## Inhaltsverzeichnis

1. [End-to-End Rechnungsverarbeitung](#1-end-to-end-rechnungsverarbeitung)
2. [Semantic Rule Matching](#2-semantic-rule-matching)
3. [Confidence-Bewertung](#3-confidence-bewertung)
4. [HITL-Workflow](#4-hitl-workflow)
5. [Regel-Lernen](#5-regel-lernen)
6. [RAG Fallback](#6-rag-fallback)
7. [Compliance-Prüfung](#7-compliance-prüfung)
8. [Audit & Persistenz](#8-audit--persistenz)

---

## 1. End-to-End Rechnungsverarbeitung

### 1.1 Überblick

Die Rechnungsverarbeitung ist ein mehrstufiger Prozess, der von der Dokumentenerfassung bis zur finalen Buchung reicht. Der gesamte Ablauf wird vom Taskforce-Framework orchestriert, wobei der Agent im ReAct-Modus (Reason + Act) arbeitet.

Der Prozess gliedert sich in sechs Hauptphasen:

| Phase | Beschreibung | Tools | Typische Dauer |
|-------|--------------|-------|----------------|
| **1. Extraktion** | PDF/Bild → strukturierte Daten | docling_extract, invoice_extract | 3-7 Sekunden |
| **2. Validierung** | §14 UStG Compliance-Prüfung | check_compliance | < 1 Sekunde |
| **3. Klassifikation** | Kontenzuordnung | semantic_rule_engine, rag_fallback | 2-5 Sekunden |
| **4. Bewertung** | Konfidenz und Hard Gates | confidence_evaluator | < 1 Sekunde |
| **5. Entscheidung** | Auto-Book oder HITL | hitl_review, ask_user | 0 - mehrere Minuten |
| **6. Finalisierung** | Speicherung und Audit | rule_learning, audit_log | < 1 Sekunde |

### 1.2 Vollständiges Sequenzdiagramm

Das folgende Diagramm zeigt alle Interaktionen zwischen Agent, Tools und Benutzer:

```mermaid
sequenceDiagram
    autonumber
    participant U as Benutzer
    participant A as Agent
    participant D as docling_extract
    participant I as invoice_extract
    participant C as check_compliance
    participant S as semantic_rule_engine
    participant CF as confidence_evaluator
    participant H as hitl_review
    participant R as rag_fallback
    participant L as rule_learning
    participant AU as audit_log
    participant BH as BookingHistory

    U->>A: "Verarbeite Rechnung invoice.pdf"

    rect rgb(240, 248, 255)
        Note over A,D: Phase 1: Extraktion
        A->>D: extract(invoice.pdf)
        D-->>A: Markdown-Text
        A->>I: extract_structure(markdown)
        I-->>A: Invoice Object
    end

    rect rgb(255, 248, 240)
        Note over A,C: Phase 2: Validierung
        A->>C: validate(invoice)
        alt Nicht konform
            C-->>A: errors, missing_fields
            A->>H: create(type="data_correction")
            H-->>A: user_prompt
            A->>U: "Bitte ergänzen Sie..."
            U-->>A: Korrektur
            A->>I: extract_structure(korrigiert)
        else Konform
            C-->>A: is_compliant=true
        end
    end

    rect rgb(240, 255, 240)
        Note over A,S: Phase 3: Klassifikation
        A->>S: match_rules(invoice)
        alt Match gefunden
            S-->>A: rule_matches, booking_proposals
        else Kein Match
            S-->>A: unmatched_items
            A->>R: suggest(unmatched_items)
            R->>BH: search_similar()
            BH-->>R: similar_bookings
            R-->>A: rag_suggestion
        end
    end

    rect rgb(255, 255, 240)
        Note over A,CF: Phase 4: Bewertung
        A->>CF: evaluate(proposal)
        CF-->>A: confidence, hard_gates
    end

    rect rgb(255, 240, 255)
        Note over A,H: Phase 5: Entscheidung
        alt Confidence >= 95% & keine Gates
            Note over A: AUTO_BOOK
            A->>L: create_from_booking()
            L-->>A: rule_created
        else Confidence < 95% oder Gates
            Note over A: HITL_REVIEW
            A->>H: create(proposal, confidence)
            H-->>A: review_id, user_prompt
            A->>U: Buchungsvorschlag
            U-->>A: Entscheidung
            A->>H: process(decision)
            alt Korrigiert
                H->>L: create_from_hitl()
                L-->>A: rule_created
            end
        end
    end

    rect rgb(240, 240, 255)
        Note over A,AU: Phase 6: Finalisierung
        A->>BH: save_booking()
        A->>AU: log(action, details)
        AU-->>A: audit_id
    end

    A-->>U: Buchung abgeschlossen
```

### 1.3 Phasen-Details

#### Phase 1: Extraktion

Die Extraktion wandelt ein Dokument (PDF, Bild, Scan) in strukturierte Daten um. Dieser Prozess besteht aus zwei Schritten:

**Schritt 1.1: Docling-Extraktion**

Das `docling_extract` Tool nutzt die Docling-Bibliothek, um das Dokument in Markdown zu konvertieren:

- **OCR**: Für gescannte Dokumente wird Optical Character Recognition angewendet
- **Layout-Analyse**: Tabellen, Überschriften und Absätze werden erkannt
- **Text-Extraktion**: Der gesamte Text wird in lesbarer Reihenfolge extrahiert

**Schritt 1.2: LLM-Strukturierung**

Das `invoice_extract` Tool nutzt ein LLM, um den Markdown-Text in ein strukturiertes `Invoice`-Objekt zu verwandeln:

- **Feld-Identifikation**: Lieferant, Datum, Beträge werden erkannt
- **Positions-Extraktion**: Einzelne Rechnungspositionen werden separiert
- **Normalisierung**: Beträge werden in einheitliches Format gebracht
- **Konsistenzprüfung**: Summen werden validiert

#### Phase 2: Validierung

Die Compliance-Prüfung stellt sicher, dass die Rechnung alle gesetzlichen Anforderungen erfüllt:

**Prüfschritte:**

1. **Betragsprüfung**: Ist es eine Kleinbetragsrechnung (< 250€)?
2. **Pflichtfelder**: Sind alle nach §14 UStG erforderlichen Felder vorhanden?
3. **USt-Konsistenz**: Stimmt die Summe der Einzelposten mit der Gesamtsumme überein?
4. **Datumslogik**: Ist das Lieferdatum plausibel (nicht in der Zukunft)?

**Bei Fehlern:**

Wenn kritische Felder fehlen, wird der Benutzer via HITL zur Ergänzung aufgefordert. Nach der Korrektur wird Phase 1.2 wiederholt.

#### Phase 3: Klassifikation

Die Klassifikation ordnet jede Rechnungsposition einem Sachkonto zu:

**Strategie-Reihenfolge:**

1. **Vendor-Only Regeln (Priority 100)**: Direktes Mapping Lieferant → Konto
2. **Vendor+Item Regeln (Priority 50-90)**: Kombination aus Lieferant und Positionsbeschreibung
3. **Legacy-Kategorien (Priority 10)**: Keyword-basierte Zuordnung
4. **RAG Fallback**: LLM-Vorschlag basierend auf historischen Buchungen

**Bei Erfolg:** `booking_proposals` werden erstellt
**Bei Misserfolg:** RAG Fallback wird aktiviert

#### Phase 4: Bewertung

Die Confidence-Bewertung berechnet einen Vertrauenswert und prüft Ausschlusskriterien:

**Berechnung:**
- 5 gewichtete Signale ergeben `overall_confidence`
- 3 Hard Gates werden geprüft (new_vendor, high_amount, critical_account)

**Entscheidung:**
- `confidence >= 0.95` UND keine Hard Gates → AUTO_BOOK
- Sonst → HITL_REVIEW

#### Phase 5: Entscheidung

Je nach Bewertungsergebnis:

**AUTO_BOOK Pfad:**
- Buchung wird sofort durchgeführt
- Automatische Regel wird gelernt (Priority 75)
- Keine Benutzerinteraktion erforderlich

**HITL_REVIEW Pfad:**
- Review-Dokument wird erstellt
- Benutzer erhält alle relevanten Informationen
- Benutzer wählt: Bestätigen / Korrigieren / Ablehnen
- Bei Korrektur: HITL-Regel wird gelernt (Priority 90)

#### Phase 6: Finalisierung

Die Finalisierung speichert alle Daten revisionssicher:

1. **Booking History**: Buchungsdatensatz mit Embedding für zukünftige Suchen
2. **Audit Log**: GoBD-konformer Eintrag mit Checksum
3. **Rule History**: Falls eine Regel gelernt wurde

### 1.4 Timing-Diagramm

Das folgende Diagramm zeigt die zeitliche Abfolge der Operationen bei einer typischen Rechnungsverarbeitung:

```mermaid
gantt
    title Rechnungsverarbeitung Timeline
    dateFormat ss
    axisFormat %S s

    section Extraktion
    Docling PDF Parse     :a1, 00, 3s
    LLM Strukturierung    :a2, after a1, 2s

    section Validierung
    Compliance Check      :b1, after a2, 1s

    section Klassifikation
    Rule Loading          :c1, after b1, 1s
    Embedding Compute     :c2, after c1, 2s
    Similarity Match      :c3, after c2, 1s

    section Bewertung
    Confidence Calc       :d1, after c3, 1s
    Hard Gate Check       :d2, after d1, 1s

    section Finalisierung
    Booking Save          :e1, after d2, 1s
    Audit Log             :e2, after e1, 1s
```

**Typische Gesamtdauer:** 12-15 Sekunden (ohne HITL)

---

## 2. Semantic Rule Matching

### 2.1 Algorithmus-Überblick

Das Semantic Rule Matching ist der Kern der automatischen Kontierung. Es kombiniert drei Matching-Strategien in einer priorisierten Reihenfolge.

**Grundprinzip:**

Das System versucht, für jede Rechnungsposition eine passende Regel zu finden. Dabei werden zuerst die zuverlässigsten Regeln (Vendor-Only) geprüft, bevor auf weniger spezifische Regeln zurückgegriffen wird.

### 2.2 Matching-Algorithmus Flowchart

```mermaid
flowchart TB
    START([Invoice mit LineItems]) --> LOAD[Regeln laden]

    LOAD --> LOOP{Für jedes<br/>LineItem}

    LOOP --> VENDOR_ONLY[Phase 1:<br/>Vendor-Only Regeln]

    VENDOR_ONLY --> VO_CHECK{Vendor<br/>Pattern Match?}
    VO_CHECK -->|Ja| VO_MATCH[Match Type: VENDOR_ONLY<br/>Similarity: 1.0]
    VO_CHECK -->|Nein| VENDOR_ITEM[Phase 2:<br/>Vendor+Item Regeln]

    VENDOR_ITEM --> VI_VENDOR{Vendor<br/>Pattern Match?}
    VI_VENDOR -->|Nein| LEGACY
    VI_VENDOR -->|Ja| VI_ITEM[Item Patterns prüfen]

    VI_ITEM --> EXACT{Exakter<br/>Keyword?}
    EXACT -->|Ja| EXACT_MATCH[Match Type: EXACT<br/>Similarity: 1.0]
    EXACT -->|Nein| EMBED[Embedding berechnen]

    EMBED --> SIM{Cosine Similarity<br/>> Threshold?}
    SIM -->|Ja| SEM_MATCH[Match Type: SEMANTIC<br/>Similarity: X.XX]
    SIM -->|Nein| LEGACY

    LEGACY[Phase 3:<br/>Legacy Categories] --> LEG_CHECK{Keyword<br/>Match?}
    LEG_CHECK -->|Ja| LEG_MATCH[Match Type: LEGACY<br/>Priority: 10]
    LEG_CHECK -->|Nein| NO_MATCH[Kein Match]

    VO_MATCH --> COLLECT
    EXACT_MATCH --> COLLECT
    SEM_MATCH --> COLLECT
    LEG_MATCH --> COLLECT
    NO_MATCH --> UNMATCHED[Zur unmatched_items]

    COLLECT[Matches sammeln] --> SORT[Nach Priority sortieren]
    SORT --> AMBIG{Top 2 Matches<br/>Diff < 0.05?}
    AMBIG -->|Ja| FLAG_AMBIG[is_ambiguous = true]
    AMBIG -->|Nein| BEST[Best Match auswählen]

    FLAG_AMBIG --> BEST
    BEST --> NEXT{Weitere<br/>LineItems?}
    UNMATCHED --> NEXT

    NEXT -->|Ja| LOOP
    NEXT -->|Nein| PROPOSAL[BookingProposals erstellen]

    PROPOSAL --> END([Return Results])

    style VO_MATCH fill:#4caf50
    style EXACT_MATCH fill:#81c784
    style SEM_MATCH fill:#64b5f6
    style LEG_MATCH fill:#ffb74d
    style NO_MATCH fill:#ef5350
```

### 2.3 Phasen-Beschreibung

#### Phase 1: Vendor-Only Matching (Grün)

**Funktionsweise:**

1. Der Lieferantenname wird normalisiert (Kleinbuchstaben, Whitespace trimmen)
2. Für jede Vendor-Only Regel wird geprüft, ob das `vendor_pattern` enthalten ist
3. Bei Match: Sofortiger Abbruch, Konto wird zurückgegeben

**Beispiel:**

```yaml
vendor_rules:
  - rule_id: VR-AWS
    vendor_pattern: "amazon web services"
    target_account: "6805"
```

Rechnung von "Amazon Web Services EMEA SARL" → Pattern "amazon web services" ist enthalten → Match!

**Vorteile:**
- Schnellste Matching-Methode
- Höchste Zuverlässigkeit (Priority 100)
- Keine Embedding-Berechnung nötig

#### Phase 2: Vendor+Item Matching (Blau)

**Funktionsweise:**

1. Vendor-Pattern wird als Regex oder Substring geprüft
2. Bei Vendor-Match: Item-Patterns werden geprüft
3. Zuerst exakter Keyword-Match (schnell)
4. Falls nicht: Semantischer Match via Embeddings

**Exakter Match:**

```python
for pattern in rule.item_patterns:
    if pattern.lower() in item.description.lower():
        return RuleMatch(match_type="exact", similarity=1.0)
```

**Semantischer Match:**

```python
item_embedding = embed(item.description)
for pattern in rule.item_patterns:
    pattern_embedding = embed(pattern)  # Cached
    similarity = cosine_similarity(item_embedding, pattern_embedding)
    if similarity >= rule.similarity_threshold:
        return RuleMatch(match_type="semantic", similarity=similarity)
```

**Beispiel:**

```yaml
semantic_rules:
  - rule_id: SR-IT-EQUIPMENT
    vendor_pattern: ".*"  # Beliebiger Lieferant
    item_patterns:
      - "Laptop"
      - "Notebook"
      - "Computer"
      - "Monitor"
    target_account: "4985"
    similarity_threshold: 0.8
```

Positionsbeschreibung "MacBook Pro 16 Zoll M3":
- Exakter Match auf "Laptop"? Nein
- Embedding-Similarity zu "Laptop": 0.87 > 0.8 → Match!

#### Phase 3: Legacy Categories (Orange)

**Funktionsweise:**

Keyword-basierte Zuordnung mit optionaler bedingter Logik (z.B. Betragsschwellen).

```yaml
expense_categories:
  - category: it_equipment
    keywords: ["laptop", "pc", "server", "hardware"]
    conditions:
      - if: amount < 800
        account: "4985"  # GWG
      - else:
        account: "0420"  # Anlagevermögen
```

#### Ambiguitätsprüfung

Nach dem Sammeln aller Matches wird geprüft, ob mehrere Regeln ähnlich gut passen:

```python
if len(matches) >= 2:
    best = matches[0]
    second = matches[1]
    if abs(best.similarity - second.similarity) < 0.05:
        best.is_ambiguous = True
        best.alternative_matches = [second]
```

**Auswirkung:** Ambige Matches führen zu niedrigerer Uniqueness-Score in der Confidence-Bewertung.

### 2.4 Embedding-Vergleich

Das folgende Diagramm zeigt den Ablauf der Embedding-basierten Ähnlichkeitssuche:

```mermaid
flowchart LR
    subgraph "Input"
        ITEM[LineItem Description<br/>"Cloud Hosting Services"]
    end

    subgraph "Embedding Service"
        EMB1[Azure OpenAI<br/>Embedding API]
        CACHE{Cache<br/>Hit?}
    end

    subgraph "Rule Patterns"
        P1["Cloud Computing" → [0.12, -0.34, ...]]
        P2["Hosting" → [0.15, -0.28, ...]]
        P3["Server" → [0.08, -0.41, ...]]
    end

    subgraph "Similarity"
        COS[Cosine Similarity]
        RANK[Ranking]
    end

    ITEM --> CACHE
    CACHE -->|Ja| VEC[Cached Vector]
    CACHE -->|Nein| EMB1
    EMB1 --> VEC

    VEC --> COS
    P1 --> COS
    P2 --> COS
    P3 --> COS

    COS --> RANK
    RANK --> RESULT["Cloud Computing": 0.92<br/>"Hosting": 0.88<br/>"Server": 0.71]
```

**Erläuterung:**

1. Die Positionsbeschreibung wird in einen 1536-dimensionalen Vektor umgewandelt
2. Dieser Vektor wird mit den vorberechneten Pattern-Vektoren verglichen
3. Die Cosine Similarity (0.0-1.0) misst die semantische Ähnlichkeit
4. Das Pattern mit höchster Similarity über dem Threshold gewinnt

**Performance-Optimierungen:**
- Pattern-Embeddings werden beim Tool-Start vorberechnet
- LRU-Cache für Item-Embeddings (max. 1000 Einträge)
- Batch-Embedding für mehrere Positionen gleichzeitig

---

## 3. Confidence-Bewertung

### 3.1 Signal-Architektur

Die Confidence-Bewertung ist ein gewichtetes Scoring-System, das die Zuverlässigkeit einer Buchungsentscheidung quantifiziert.

**Designprinzipien:**

1. **Multi-Signal-Ansatz**: Kein einzelnes Signal dominiert
2. **Kalibrierte Gewichte**: Basierend auf empirischen Daten
3. **Hard Gates als Override**: Bestimmte Situationen erzwingen immer HITL

### 3.2 Signal-Berechnung

```mermaid
flowchart TB
    subgraph "Input Daten"
        RULE[Rule Match]
        INVOICE[Invoice Data]
        HISTORY[Booking History]
    end

    subgraph "Signal Berechnung"
        S1[Rule Type Signal]
        S2[Similarity Signal]
        S3[Uniqueness Signal]
        S4[Historical Signal]
        S5[Extraction Signal]
    end

    subgraph "Rule Type Logic"
        RT_VO[VENDOR_ONLY → 1.0]
        RT_VI[VENDOR_ITEM → 0.8]
        RT_RAG[RAG → 0.5]
        RT_NONE[NONE → 0.0]
    end

    subgraph "Uniqueness Logic"
        UQ_UNIQUE[Eindeutig → 1.0]
        UQ_AMBIG[Ambiguos → 0.7]
    end

    subgraph "Weighted Sum"
        W1["× 0.25"]
        W2["× 0.25"]
        W3["× 0.20"]
        W4["× 0.15"]
        W5["× 0.15"]
        SUM[Σ = Overall Confidence]
    end

    RULE --> S1
    RULE --> S2
    RULE --> S3
    HISTORY --> S4
    INVOICE --> S5

    S1 --> RT_VO
    S1 --> RT_VI
    S1 --> RT_RAG
    S1 --> RT_NONE

    S3 --> UQ_UNIQUE
    S3 --> UQ_AMBIG

    S1 --> W1 --> SUM
    S2 --> W2 --> SUM
    S3 --> W3 --> SUM
    S4 --> W4 --> SUM
    S5 --> W5 --> SUM
```

### 3.3 Signal-Definitionen

#### Signal 1: Rule Type (25%)

Bewertet die Art der angewendeten Regel:

| Regeltyp | Score | Begründung |
|----------|-------|------------|
| VENDOR_ONLY | 1.0 | Höchste Zuverlässigkeit - bewährte Zuordnung |
| VENDOR_ITEM (HITL) | 0.9 | Vom Benutzer bestätigte Zuordnung |
| VENDOR_ITEM (Exact) | 0.85 | Exakter Keyword-Match |
| VENDOR_ITEM (Semantic) | 0.8 | Semantischer Match, leicht unsicherer |
| RAG Fallback | 0.5 | LLM-Schätzung ohne Regel |
| Kein Match | 0.0 | Keine Grundlage |

#### Signal 2: Similarity (25%)

Die Cosine Similarity aus dem Matching:

- Bei VENDOR_ONLY oder EXACT: 1.0
- Bei SEMANTIC: Der berechnete Similarity-Wert (0.8-1.0)
- Bei RAG: Die vom LLM angegebene Konfidenz

#### Signal 3: Uniqueness (20%)

Misst, wie eindeutig die Zuordnung war:

| Situation | Score | Beschreibung |
|-----------|-------|--------------|
| Eindeutig | 1.0 | Nur eine Regel passt oder klarer Abstand |
| Leicht ambiguos | 0.8 | Zwei Matches, aber klarer Gewinner |
| Stark ambiguos | 0.7 | Mehrere sehr ähnliche Matches |
| Sehr unsicher | 0.5 | Viele gleichwertige Kandidaten |

#### Signal 4: Historical (15%)

Basiert auf der Erfolgshistorie der Regel:

```python
historical_score = successful_uses / total_uses
# successful_uses = Buchungen ohne nachträgliche Korrektur
# total_uses = Gesamtanwendungen der Regel
```

- Neue Regeln starten mit 0.5 (neutral)
- Minimum: 0.3 (Regel wurde oft korrigiert)
- Maximum: 1.0 (Regel wurde nie korrigiert)

#### Signal 5: Extraction (15%)

Die Qualität der Dokumentenextraktion:

| Qualität | Score | Indikatoren |
|----------|-------|-------------|
| Excellent | 0.95-1.0 | Digitale PDF, alle Felder erkannt |
| Good | 0.85-0.95 | Gute OCR, wenige Unsicherheiten |
| Medium | 0.70-0.85 | Scan mit Artefakten, einige Felder unsicher |
| Poor | 0.50-0.70 | Schlechte Qualität, viele Rekonstruktionen |

### 3.4 Hard Gate Prüfung

Nach der Confidence-Berechnung werden die Hard Gates geprüft:

```mermaid
flowchart TB
    CONF[Overall Confidence] --> THRESHOLD{≥ 95%?}

    THRESHOLD -->|Nein| HITL_LOW[→ HITL<br/>Grund: Low Confidence]
    THRESHOLD -->|Ja| GATES[Hard Gates prüfen]

    GATES --> G1{new_vendor?}
    G1 -->|Ja| HITL_NEW[→ HITL<br/>Grund: Neuer Lieferant]
    G1 -->|Nein| G2{high_amount?}

    G2 -->|Ja| HITL_AMT[→ HITL<br/>Grund: Betrag > 5000€]
    G2 -->|Nein| G3{critical_account?}

    G3 -->|Ja| HITL_CRIT[→ HITL<br/>Grund: Kritisches Konto]
    G3 -->|Nein| AUTO[→ AUTO_BOOK]

    style AUTO fill:#4caf50
    style HITL_LOW fill:#ff9800
    style HITL_NEW fill:#ff9800
    style HITL_AMT fill:#ff9800
    style HITL_CRIT fill:#ff9800
```

**Gate-Definitionen:**

| Gate | Prüfung | Default-Konfiguration |
|------|---------|----------------------|
| new_vendor | `booking_history.is_new_vendor(supplier)` | Aktiviert |
| high_amount | `invoice.total_gross > threshold` | 5.000 EUR |
| critical_account | `target_account in critical_list` | ["1800", "2100"] |

**Rationale für Hard Gates:**

- **new_vendor**: Erste Rechnungen von einem Lieferanten können leicht falsch klassifiziert werden
- **high_amount**: Bei hohen Beträgen hat ein Fehler größere finanzielle Auswirkungen
- **critical_account**: Bestimmte Konten (Bank, Eigenkapital) erfordern besondere Sorgfalt

---

## 4. HITL-Workflow

### 4.1 Zweck und Trigger

Der Human-in-the-Loop (HITL) Workflow ist der Qualitätssicherungsmechanismus des Systems. Er stellt sicher, dass unsichere Buchungen von einem Menschen geprüft werden.

**HITL wird ausgelöst bei:**

1. Confidence unter 95%
2. Ausgelöstem Hard Gate
3. Ambiguität im Rule Matching
4. Fehlenden Compliance-Feldern

### 4.2 Review-Erstellung

```mermaid
sequenceDiagram
    participant A as Agent
    participant H as HITLReviewTool
    participant S as Storage
    participant U as User

    A->>H: create(invoice, proposal, confidence, gates)

    H->>H: review_id = uuid4()

    H->>H: Generiere user_prompt

    Note over H: user_prompt enthält:<br/>- Rechnungsdaten<br/>- Vorgeschlagene Buchung<br/>- Konfidenz<br/>- Prüfungsgründe<br/>- Optionen

    H->>S: Store pending_review

    H-->>A: {review_id, user_prompt, options}

    A->>U: Zeige user_prompt

    Note over U: ## Buchungsvorschlag<br/>**Lieferant:** AWS<br/>**Betrag:** 750€<br/>**Konto:** 6805<br/>**Konfidenz:** 87%<br/><br/>**Grund:** Neuer Lieferant<br/><br/>1) Bestätigen<br/>2) Korrigieren<br/>3) Ablehnen
```

**Struktur des user_prompt:**

Der generierte Prompt enthält alle für die Entscheidung relevanten Informationen:

```markdown
## Buchungsvorschlag zur Prüfung

**Review-ID:** a1b2c3d4-5678-90ab-cdef

---

### Rechnungsdaten
| Feld | Wert |
|------|------|
| Lieferant | TechSupply GmbH |
| Rechnungsnummer | RE-2026-0042 |
| Rechnungsdatum | 25.01.2026 |
| Bruttobetrag | 595,00 EUR |
| Nettobetrag | 500,00 EUR |
| USt 19% | 95,00 EUR |

### Positionen
1. **Büromaterial Sortiment** - 500,00 EUR netto

---

### Vorgeschlagene Buchung
- **Sollkonto:** 4930 (Bürobedarf)
- **Habenkonto:** 1600 (Verbindlichkeiten)
- **Vorsteuerkonto:** 1576 (Vorsteuer 19%)
- **Buchungstext:** Büromaterial Sortiment - TechSupply GmbH

### Konfidenz-Details
- **Gesamtkonfidenz:** 87%
- **Regel:** SR-OFFICE (Semantic Match)
- **Ähnlichkeit:** 0.84

---

### Prüfungsgründe
- ⚠️ Konfidenz unter 95% (87%)
- ⚠️ Neuer Lieferant (erste Rechnung)

---

### Ihre Optionen
1. **Bestätigen** - Vorschlag wie dargestellt übernehmen
2. **Korrigieren** - Anderes Konto angeben (z.B. "4985 GWG")
3. **Ablehnen** - Buchung abbrechen und manuell bearbeiten
```

### 4.3 Review-Verarbeitung

```mermaid
flowchart TB
    INPUT([User Entscheidung]) --> DECISION{Entscheidung?}

    DECISION -->|1: Bestätigen| CONFIRM[Originalvorschlag<br/>übernehmen]
    DECISION -->|2: Korrigieren| CORRECT[Korrektur anwenden]
    DECISION -->|3: Ablehnen| REJECT[Buchung abbrechen]

    CONFIRM --> FINAL[final_booking =<br/>original_proposal]

    CORRECT --> APPLY[Neues Konto<br/>anwenden]
    APPLY --> LEARN{create_rule?}
    LEARN -->|Ja| RULE[rule_learning<br/>create_from_hitl]
    LEARN -->|Nein| SKIP[Keine Regel]
    RULE --> FINAL_CORR[final_booking =<br/>corrected_proposal]
    SKIP --> FINAL_CORR

    REJECT --> CANCEL[is_rejected = true]

    FINAL --> SAVE[Buchung speichern]
    FINAL_CORR --> SAVE
    CANCEL --> END([Workflow beendet])

    SAVE --> AUDIT[Audit Log]
    AUDIT --> END

    style CONFIRM fill:#4caf50
    style CORRECT fill:#ff9800
    style REJECT fill:#f44336
```

**Verarbeitung im Detail:**

**Option 1: Bestätigen**

Der Benutzer akzeptiert den Vorschlag ohne Änderung:

```python
result = hitl_review.process(
    review_id="a1b2c3d4",
    user_decision="confirm"
)
# result.final_booking = original_proposal
# result.is_hitl_correction = False
```

**Option 2: Korrigieren**

Der Benutzer gibt ein anderes Konto an:

```python
result = hitl_review.process(
    review_id="a1b2c3d4",
    user_decision="correct",
    correction={
        "target_account": "4985",
        "target_account_name": "GWG",
        "create_rule": True  # Optional: Regel lernen
    }
)
# result.final_booking hat aktualisiertes Konto
# result.is_hitl_correction = True
# result.rule_created = True (falls create_rule=True)
```

**Option 3: Ablehnen**

Der Benutzer bricht die automatische Buchung ab:

```python
result = hitl_review.process(
    review_id="a1b2c3d4",
    user_decision="reject",
    rejection_reason="Rechnung ist Dublettte"  # Optional
)
# result.is_rejected = True
# Kein final_booking
```

---

## 5. Regel-Lernen

### 5.1 Übersicht

Das Regellernen ermöglicht dem System, aus Erfahrung besser zu werden. Es gibt zwei Lernquellen:

| Quelle | Trigger | Resultierende Priority | Zuverlässigkeit |
|--------|---------|------------------------|-----------------|
| Auto-Learning | Confidence ≥ 95%, Auto-Book | 75 | Hoch |
| HITL-Learning | Benutzerkorrektur | 90 | Sehr hoch |

### 5.2 Auto-Learning Pipeline

```mermaid
flowchart TB
    subgraph "Trigger"
        BOOK[AUTO_BOOK<br/>Confidence ≥ 95%]
    end

    subgraph "Analyse"
        VENDOR[Vendor Name<br/>normalisieren]
        ITEMS[Line Items<br/>analysieren]
        ACCOUNT[Zielkonto<br/>ermitteln]
    end

    subgraph "Regeltyp-Entscheidung"
        CHECK{Nur Vendor<br/>relevant?}
        VO_TYPE[RuleType:<br/>VENDOR_ONLY]
        VI_TYPE[RuleType:<br/>VENDOR_ITEM]
    end

    subgraph "Regel-Erstellung"
        CREATE[AccountingRule<br/>erstellen]
        ID[rule_id:<br/>AUTO-{timestamp}]
        PRIO[priority: 75]
        SRC[source:<br/>AUTO_HIGH_CONFIDENCE]
    end

    subgraph "Persistenz"
        CONFLICT[Konfliktprüfung]
        SAVE[learned_rules.yaml<br/>speichern]
        HISTORY[rules_history.jsonl<br/>Eintrag]
    end

    BOOK --> VENDOR
    VENDOR --> ITEMS
    ITEMS --> ACCOUNT
    ACCOUNT --> CHECK

    CHECK -->|Ja| VO_TYPE
    CHECK -->|Nein| VI_TYPE

    VO_TYPE --> CREATE
    VI_TYPE --> CREATE

    CREATE --> ID
    ID --> PRIO
    PRIO --> SRC
    SRC --> CONFLICT

    CONFLICT --> SAVE
    SAVE --> HISTORY
```

**Wann wird VENDOR_ONLY vs. VENDOR_ITEM gewählt?**

```python
def determine_rule_type(invoice, booking_history):
    # Prüfe historische Buchungen für diesen Lieferanten
    history = booking_history.get_vendor_history(invoice.supplier_name)

    if len(history) >= 3:
        accounts = set(b.debit_account for b in history)
        if len(accounts) == 1:
            # Lieferant wird immer gleich gebucht
            return RuleType.VENDOR_ONLY

    # Verschiedene Konten je nach Position
    return RuleType.VENDOR_ITEM
```

### 5.3 HITL-Learning Pipeline

```mermaid
flowchart TB
    subgraph "Trigger"
        HITL[HITL Korrektur<br/>empfangen]
    end

    subgraph "Korrektur-Analyse"
        ORIG[Original:<br/>Konto 4930]
        CORR[Korrektur:<br/>Konto 4940]
        DIFF[Delta ermitteln]
    end

    subgraph "Regel-Erstellung"
        CREATE[AccountingRule<br/>erstellen]
        ID[rule_id:<br/>HITL-{timestamp}]
        PRIO[priority: 90<br/>↑ höher als Auto]
        SRC[source:<br/>HITL_CORRECTION]
    end

    subgraph "Konflikt-Behandlung"
        FIND[Konflikt-Regeln<br/>finden]
        DEACT[Alte Regeln<br/>deaktivieren]
    end

    subgraph "Persistenz"
        SAVE[learned_rules.yaml<br/>speichern]
        HISTORY[rules_history.jsonl<br/>Eintrag]
    end

    HITL --> ORIG
    ORIG --> CORR
    CORR --> DIFF

    DIFF --> CREATE
    CREATE --> ID
    ID --> PRIO
    PRIO --> SRC

    SRC --> FIND
    FIND --> DEACT
    DEACT --> SAVE
    SAVE --> HISTORY
```

**Besonderheit bei HITL-Learning:**

HITL-Regeln haben eine höhere Priorität (90) als Auto-Regeln (75). Wenn eine HITL-Korrektur erfolgt, bedeutet das, dass eine vorherige Zuordnung falsch war. Die neue Regel soll Vorrang haben.

**Konfliktauflösung:**

Wenn die neue Regel mit einer bestehenden Regel konfligiert (gleicher Vendor, überlappende Items, anderes Konto), wird die alte Regel deaktiviert:

```python
conflicting_rules = rule_repository.find_conflicting_rules(new_rule)
for conflict in conflicting_rules:
    rule_repository.deactivate_rule(
        conflict.rule_id,
        reason=f"Superseded by {new_rule.rule_id}"
    )
```

---

## 6. RAG Fallback

### 6.1 Aktivierungsbedingungen

Der RAG (Retrieval-Augmented Generation) Fallback wird aktiviert, wenn:

1. Keine Vendor-Only Regel passt
2. Keine Vendor+Item Regel über dem Similarity-Threshold liegt
3. Keine Legacy-Kategorie matcht

### 6.2 Kontext-Aufbau

```mermaid
flowchart TB
    subgraph "Input"
        ITEM[Unmatched LineItem<br/>"Spezial-Widget XY"]
        VENDOR[Vendor Name<br/>"TechCorp GmbH"]
    end

    subgraph "Semantic Search"
        EMBED[Item Description<br/>→ Embedding]
        SEARCH[BookingHistory<br/>search_similar()]
        FILTER[Vendor Filter<br/>optional]
    end

    subgraph "Kontext"
        TOP5[Top 5<br/>Similar Bookings]
        FORMAT[Als Kontext<br/>formatieren]
    end

    subgraph "LLM Prompt"
        SYSTEM[System Prompt:<br/>Buchhaltungs-Experte]
        USER[User Prompt:<br/>Item + Kontext]
        CALL[LLM Call]
    end

    ITEM --> EMBED
    VENDOR --> FILTER
    EMBED --> SEARCH
    FILTER --> SEARCH
    SEARCH --> TOP5
    TOP5 --> FORMAT

    FORMAT --> USER
    SYSTEM --> CALL
    USER --> CALL

    CALL --> RESULT[JSON Response:<br/>account, confidence,<br/>reasoning]
```

**Semantic Search:**

Die Suche in der Booking History verwendet Embeddings:

```python
async def search_similar(query: str, vendor_name: str = None, limit: int = 5):
    query_embedding = await embed(query)

    results = []
    for booking in booking_history:
        if vendor_name and vendor_name not in booking.supplier_name:
            continue
        similarity = cosine_similarity(query_embedding, booking.embedding)
        results.append((similarity, booking))

    results.sort(reverse=True)
    return results[:limit]
```

### 6.3 LLM Prompt und Response

**System Prompt:**

```
Du bist ein erfahrener Buchhalter mit Expertise im deutschen Steuerrecht.
Deine Aufgabe ist es, Rechnungspositionen dem korrekten Sachkonto (SKR03) zuzuordnen.

Regeln:
1. Sei konservativ bei der Konfidenz-Angabe
2. Wenn du unsicher bist, gib mehrere Alternativen an
3. Begründe deine Entscheidung kurz
4. Antworte immer im JSON-Format
```

**User Prompt (Beispiel):**

```
Ordne die folgende Rechnungsposition einem Sachkonto zu.

Rechnung:
- Lieferant: TechCorp GmbH
- Position: "Spezial-Widget XY für Produktionsanlage"
- Betrag: 1.200,00 EUR netto
- USt: 19%

Ähnliche historische Buchungen:
1. MaschinenbauCo: "Ersatzteil für Produktionsmaschine" → Konto 4970 (Reparaturen)
2. TechParts AG: "Komponente für Fertigung" → Konto 4970 (Reparaturen)
3. IndustrieBedarf: "Werkzeug für Produktion" → Konto 4985 (GWG)

Antworte im JSON-Format mit:
- suggested_account: Kontonummer
- account_name: Kontobezeichnung
- confidence: Deine Konfidenz (0.0-1.0)
- reasoning: Kurze Begründung
- legal_basis: Rechtsgrundlage
- alternative_accounts: Liste von Alternativen
```

**LLM Response:**

```json
{
    "suggested_account": "4970",
    "account_name": "Reparaturen und Instandhaltung",
    "confidence": 0.70,
    "reasoning": "Basierend auf zwei ähnlichen Buchungen scheint es sich um ein Ersatzteil für die Produktion zu handeln. Da es als 'Spezial-Widget' bezeichnet wird, könnte es auch ein GWG sein.",
    "legal_basis": "§4 Abs. 4 EStG",
    "alternative_accounts": [
        {
            "account": "4985",
            "name": "GWG",
            "reason": "Falls Anschaffungskosten < 800€ und eigenständig nutzbar"
        },
        {
            "account": "4830",
            "name": "Betriebsbedarf",
            "reason": "Falls Verbrauchsmaterial"
        }
    ]
}
```

### 6.4 Response-Verarbeitung

```mermaid
flowchart TB
    LLM[LLM Response] --> PARSE{JSON<br/>parsebar?}

    PARSE -->|Nein| FALLBACK[Fallback:<br/>Konto 4900<br/>Conf: 0.3]

    PARSE -->|Ja| VALIDATE{Konto<br/>gültig?}
    VALIDATE -->|Nein| FALLBACK
    VALIDATE -->|Ja| EXTRACT[Account,<br/>Confidence,<br/>Reasoning]

    EXTRACT --> CONF{Confidence<br/>plausibel?}
    CONF -->|Nein| CAP[Cap: 0.7]
    CONF -->|Ja| PASS[Wert übernehmen]

    CAP --> PROPOSAL
    PASS --> PROPOSAL

    PROPOSAL[RAG BookingProposal] --> FLAG[is_rag_suggestion = true]
    FALLBACK --> FLAG

    FLAG --> EVAL[→ confidence_evaluator]
```

**Sicherheitsmaßnahmen:**

1. **Konto-Validierung**: Prüfung ob Konto existiert
2. **Confidence-Cap**: LLM-Konfidenz wird auf max. 0.7 begrenzt
3. **RAG-Flag**: Vorschläge werden als RAG markiert (niedrigerer rule_type_score)

---

## 7. Compliance-Prüfung

### 7.1 Prüfungslogik

Die Compliance-Prüfung validiert Rechnungen gegen die Anforderungen des §14 UStG:

```mermaid
flowchart TB
    INVOICE([Invoice Object]) --> AMOUNT{Betrag<br/>< 250€?}

    AMOUNT -->|Ja| SMALL[Kleinbetrags-<br/>rechnung<br/>§33 UStDV]
    AMOUNT -->|Nein| FULL[Vollständige<br/>Rechnung<br/>§14 UStG]

    SMALL --> CHECK_S[Pflichtfelder prüfen:<br/>6 Felder]
    FULL --> CHECK_F[Pflichtfelder prüfen:<br/>12 Felder]

    CHECK_S --> MISSING_S{Fehlende<br/>Felder?}
    CHECK_F --> MISSING_F{Fehlende<br/>Felder?}

    MISSING_S -->|Ja| WARN_S[Warnings<br/>generieren]
    MISSING_S -->|Nein| OK_S[is_compliant = true]

    MISSING_F -->|Ja| ERROR_F{Kritische<br/>Felder?}
    MISSING_F -->|Nein| VAT_CHECK

    ERROR_F -->|Ja| FAIL[is_compliant = false<br/>Errors generieren]
    ERROR_F -->|Nein| WARN_F[Warnings<br/>generieren]

    WARN_S --> VAT_CHECK
    OK_S --> VAT_CHECK
    WARN_F --> VAT_CHECK

    VAT_CHECK[USt-Konsistenz<br/>prüfen] --> VAT_OK{USt = Netto<br/>× Satz?}
    VAT_OK -->|Ja| DONE[Prüfung<br/>abgeschlossen]
    VAT_OK -->|Nein| VAT_WARN[Warning:<br/>USt-Abweichung]
    VAT_WARN --> DONE

    FAIL --> END([ComplianceResult])
    DONE --> END

    style OK_S fill:#4caf50
    style FAIL fill:#f44336
```

### 7.2 Feldkategorien

**Kritische Felder (führen zu is_compliant=false):**

- Lieferantenname
- Lieferantenanschrift
- Rechnungsnummer
- Rechnungsdatum
- Steuernummer/USt-IdNr. (außer Kleinbetrag)

**Nicht-kritische Felder (führen zu Warnings):**

- Lieferdatum (§14 erlaubt "im Monat der Lieferung")
- Empfängername (bei B2B oft implizit)

---

## 8. Audit & Persistenz

### 8.1 Datenfluss-Übersicht

```mermaid
flowchart LR
    subgraph "Transiente Daten"
        INVOICE[Invoice<br/>Object]
        PROPOSAL[Booking<br/>Proposal]
        MATCH[Rule<br/>Match]
    end

    subgraph "Persistenz Layer"
        YAML[(kontierung_rules.yaml<br/>learned_rules.yaml)]
        HISTORY[(booking_history.jsonl)]
        AUDIT[(audit_log.jsonl)]
        RULES_HIST[(rules_history.jsonl)]
    end

    subgraph "Operationen"
        SAVE_RULE[Rule speichern]
        SAVE_BOOKING[Booking speichern]
        LOG_AUDIT[Audit loggen]
    end

    MATCH --> SAVE_RULE
    SAVE_RULE --> YAML
    SAVE_RULE --> RULES_HIST

    INVOICE --> SAVE_BOOKING
    PROPOSAL --> SAVE_BOOKING
    SAVE_BOOKING --> HISTORY

    SAVE_BOOKING --> LOG_AUDIT
    SAVE_RULE --> LOG_AUDIT
    LOG_AUDIT --> AUDIT
```

### 8.2 Append-Only Garantie

Alle historischen Daten werden nur angehängt, nie überschrieben oder gelöscht:

```mermaid
sequenceDiagram
    participant App as Application
    participant BH as BookingHistory
    participant FS as FileSystem

    App->>BH: save_booking(record)

    BH->>BH: timestamp = now()
    BH->>BH: booking_id = uuid()
    BH->>BH: compute_embedding()

    Note over BH: Append-Only Write

    BH->>FS: open(file, mode='a')
    BH->>FS: write(json_line + '\n')
    BH->>FS: flush()
    BH->>FS: close()

    Note over FS: Datei wird nur erweitert,<br/>nie überschrieben

    BH-->>App: booking_id
```

**GoBD-Compliance:**

- Keine DELETE-Operationen
- Keine UPDATE-Operationen (nur APPEND)
- Jeder Eintrag hat Timestamp und Checksum
- 10-Jahre-Aufbewahrung unterstützt

---

*Workflow-Dokumentation - Version 1.0*
*Letzte Aktualisierung: 2026-01-27*
