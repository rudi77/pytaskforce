Perfekt 👍
Dann mache ich **beides sauber und final**:

* **(1) Überarbeitete, konsistente Markdown-Fassung** deines Dokuments (inhaltlich geschärft, hybrid-konform, audit-sauber)
* **(2) Korrigiertes State-Diagramm** als **offizielle Referenz** (nur minimale, aber entscheidende Änderungen)

Ich halte mich **eng an deinen Text**, ändere **keine fachliche Idee**, sondern **präzisiere Begriffe, Verantwortlichkeiten und Semantik vs. KI**.

---

# ✅ (1) Überarbeitete Markdown-Fassung

**Finale Zielversion – Phase 1 (Sachkonto)**

---

# Technisches Zieldokument

## Autonomer Kontierungs-Workflow (Phase 1 – Sachkonto)

---

## 1. Zielsetzung

Dieses Dokument beschreibt die technische Zielarchitektur eines **autonomen, hybriden Kontierungs-Workflows** zur automatischen Zuordnung von Rechnungspositionen zu **Sachkonten**.

In der ersten Projektphase liegt der Fokus **ausschließlich auf der Sachkontierung**.
Die Erweiterung auf **Kostenstellen** erfolgt in einer späteren Phase, nachdem die Regel- und Lernlogik stabil und validiert ist.

Der Workflow kombiniert bewusst mehrere, klar getrennte Mechanismen:

* **formale, deterministische Datenprüfung**
* **regelbasierte Kontierung mit semantischer Erweiterung** (Vendor / Line-Item)
* **LLM-gestützte Vorschläge ausschließlich als Fallback**
* **Human-in-the-Loop (HITL)** bei Unsicherheit oder Policy-Verletzung
* **automatisches Regel-Lernen** aus bestätigten Entscheidungen

Ziel ist ein **reproduzierbarer, auditierbarer und lernfähiger Prozess**, bei dem **keine Buchungsentscheidung unbegründet oder nicht erklärbar** getroffen wird.

---

## 2. Systemarchitektur

Der Kontierungsprozess wird als **deterministische State Machine** umgesetzt.
Jeder Zustand besitzt eine klar definierte Aufgabe, Ein- und Ausgänge sowie feste Übergangsbedingungen.

Die Architektur folgt dem Prinzip:

> **Rules first – Semantik als Signal – LLM nur als Vorschlag – Mensch als letzte Instanz**

---

### 2.1 Ingestion & Validation

* Extraktion der Rechnungsdaten (OCR, E-Rechnung, API)
* Formale Prüfungen:

  * Pflichtfelder
  * Betragskonsistenz
  * USt-IdNr.
  * Dubletten
* Fehlerhafte oder unvollständige Rechnungen führen in einen **HITL-Korrekturpfad**

➡️ In dieser Phase findet **keine KI-gestützte Entscheidung** statt.

---

### 2.2 Semantic Rules Engine (Priorität 1)

Die **Semantic Rules Engine** ist der primäre Entscheidungsmechanismus.

Sie arbeitet **vollständig deterministisch**, nutzt jedoch **semantische Ähnlichkeitsberechnung (Embeddings)** zur Erhöhung der Treffergenauigkeit.

**Keine LLMs sind Teil dieser Phase.**

#### Regelquellen

* Tabelle `accounting_rules`
* Versionierte, priorisierte Regeln

#### Prüflogiken

**Regeltyp A – Vendor-Only**

* Eindeutige Zuordnung Lieferant → Sachkonto
* Beispiel:
  *„Bürobedarf Müller GmbH“ → Sachkonto 4980 (Bürobedarf)*

**Regeltyp B – Vendor + Item-Semantik**

* Lieferant passt
* Mindestens ein Line Item ist semantisch ähnlich zu einem hinterlegten Item-Muster
* Semantik erfolgt über:

  * Embedding-Vergleich
  * festes Similarity-Threshold
  * versioniertes Modell

➡️ Beispiel:
„Kopierpapier A4“ ≈ „Bürobedarf“

#### Evaluierungsreihenfolge

1. Aktive Regeln nach Priorität sortieren
2. Vendor-Only-Regeln prüfen
3. Vendor + Item-Semantik prüfen
4. Bei mehreren Treffern:

   1. Höchste Spezifität
   2. Höchster Match-Score
   3. Höchste Regelpriorität
5. Ambige Treffer → kein Auto-Booking

➡️ Kein Treffer → **RAG-Fallback**

---

### 2.3 RAG Suggestion (Priorität 2 – Fallback)

Wird nur aktiviert, wenn **keine Regel greift**.

* Suche nach semantisch ähnlichen historischen Buchungen
* Kontext: Lieferant, Line Items, Beträge
* **LLM generiert ausschließlich einen Vorschlag**:

  * Sachkonto
  * Begründung
  * Konfidenzwert

⚠️ Das LLM trifft **keine finale Entscheidung**.

---

### 2.4 Confidence Evaluation

Alle Vorschläge (Regel / Similarity / RAG) werden **deterministisch bewertet**.

Die Konfidenz ergibt sich aus einer gewichteten Bewertung mehrerer Signale:

* Regeltyp (Vendor-Only > Vendor+Item)
* Semantischer Ähnlichkeitswert
* Eindeutigkeit des Treffers
* Historische Trefferquote
* (optional) LLM-Konfidenz als **schwaches Signal**

**Entscheidungslogik**

* **> 95 %:** automatische Buchung + Regel-Lernen
* **≤ 95 %:** HITL-Review

Zusätzliche harte Gates:

* neue Lieferanten
* hohe Beträge
* steuerlich kritische Konten

---

### 2.5 Human-in-the-Loop (HITL) & Lernen

* Benutzer bestätigt oder korrigiert den Vorschlag
* Korrekturen können als neue Regel gespeichert werden
* Regeln sind versioniert und auditierbar
* Neue Regeln überschreiben ältere Versionen

---

### 2.6 Finalization

* Speicherung der Buchung
* Persistierung des Entscheidungspfads
* Optional: Aktivierung neuer Regeln

---

## 3. Zustandsmaschine

*(siehe Referenzdiagramm unten)*

---

## 4. Regelmodell

Jede Regel bildet eine **Wenn–Dann-Beziehung** ab.

### Regeltyp A – Vendor-Only

```text
IF vendor == "Bürobedarf Müller"
THEN account = 4980
```

### Regeltyp B – Vendor + Item-Semantik

```text
IF vendor == "Mustermann GmbH"
AND similarity(line_item, ["papier","toner","stift"]) ≥ 0.8
THEN account = 4980
```

Regeln sind:

* versioniert
* priorisiert
* aktiv/inaktiv
* mit Quelle (manual / auto_high_confidence)

---

## 5. Proof-of-Concept Kriterien

* **Automatisierungsquote**
* **Genauigkeit ≥ 97 %**
* **Lernquote (HITL → Regel)**
* **keine nicht erklärbaren Auto-Buchungen**

---

## 6. Erweiterung (Phase 2)

* Kostenstellen
* Multi-Kriterien-Regeln
* Split-Buchungen

---

## 7. Zusammenfassung

Die Architektur ermöglicht eine **kontrollierte, lernfähige Sachkontierung**, bei der:

> **jede Entscheidung erklärbar, reproduzierbar und auditierbar bleibt**.

---

# ✅ (2) Finales Referenz-State-Diagramm (korrigiert)

### **Offizielle, hybride Version**

```plantuml
@startuml
!theme plain
skinparam state {
    BackgroundColor #F5F5F5
    BorderColor #666666
    FontColor #333333
}
skinparam state<<HITL>> {
    BackgroundColor #FFF4E6
    BorderColor #CC9966
}
title Automatische Kontierung – Hybrid Workflow (deterministisch + semantisch)

[*] --> Ingestion

state Ingestion {
    [*] -> Extracting
    Extracting : 1. Extrahiere Rechnungsdaten
    Extracting -> Validating
    Validating : 2. Formale Validierung
}

Validating --> SemanticRuleCheck : [Daten gültig]
Validating --> PendingValidationHITL : [Daten ungültig]

state PendingValidationHITL <<HITL>> {
    note right : STOP – Benutzer korrigiert Rechnungsdaten
}
PendingValidationHITL --> Validating

state SemanticRuleCheck {
    3a. Prüfe Vendor-Only-Regeln
    3b. Prüfe Line-Item-Semantik\n(Embeddings + Threshold)
    3c. Lieferanten-Fallback
}

note right of SemanticRuleCheck
Deterministische Regelprüfung:
- Keywords / Regex
- Semantische Ähnlichkeit (Embeddings)
- Feste Schwellen & Prioritäten
Keine LLM-Entscheidung
end note

SemanticRuleCheck --> Finalization : [Eindeutiger Regel-Treffer]
SemanticRuleCheck --> RAGSuggestion : [Kein Treffer]

RAGSuggestion : 4. RAG-Fallback (LLM-Vorschlag)
RAGSuggestion --> ConfidenceCheck

ConfidenceCheck : 5. Deterministische\nKonfidenz- & Policy-Prüfung
ConfidenceCheck --> RuleLearning_Auto : [>95 %]
ConfidenceCheck --> PendingReviewHITL : [≤95 %]

state PendingReviewHITL <<HITL>> {
    note right : STOP – Benutzerreview
}
PendingReviewHITL --> Finalization : [Bestätigt]
PendingReviewHITL --> RuleLearning_Manual : [Korrigiert]

RuleLearning_Manual : 6a. Regel speichern (manuell)
RuleLearning_Manual --> Finalization

RuleLearning_Auto : 6b. Auto-Regel (High Confidence)
RuleLearning_Auto --> Finalization

Finalization : 7. Buchung speichern\n+ Audit Trail
Finalization --> [*]

@enduml
```
