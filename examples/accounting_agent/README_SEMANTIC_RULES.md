# Hier ist eine Erklärung der Semantic Rule Engine:

  ## Überblick

  Die SemanticRuleEngineTool ist ein deterministisches Kontierungswerkzeug für Rechnungen. Sie ordnet
  Rechnungspositionen automatisch den richtigen Buchhaltungskonten zu (SKR03/SKR04) — ohne LLM-Entscheidungen.      
  Embeddings werden nur für Ähnlichkeitsvergleiche genutzt.

  Drei Regeltypen (Prioritätsreihenfolge)

  1. Vendor-Only Rules (Priorität 100) — RuleType.VENDOR_ONLY

  Einfachste Stufe: Lieferantenname → Konto. Wenn z.B. "Deutsche Telekom" erkannt wird, geht alles auf Konto 4920   
  (Telekommunikation). Kein Blick auf die Position nötig.

  2. Vendor + Item-Semantics Rules (Priorität 50) — RuleType.VENDOR_ITEM

  Zweistufig: Erst wird der Lieferant geprüft (Regex oder Substring), dann die Positionsbeschreibung gegen
  item_patterns abgeglichen. Der Item-Abgleich funktioniert zweistufig:
  - Exakt/Keyword: Substring-Match (mit Unicode-Quote-Normalisierung). Kurze Patterns (<4 Zeichen) nutzen
  Word-Boundary-Regex um False Positives zu vermeiden (z.B. "DB" soll nicht in "Goldbräu" matchen).
  - Semantisch: Falls kein exakter Match, wird per Embedding-Cosine-Similarity verglichen (Schwelle konfigurierbar, 
  default 0.8).

  3. Vendor-Generalisierung (Priorität 60) — Fallback

  Wenn Phase 1+2 nichts finden, prüft die Engine ob der Lieferant ein dominantes Buchungsmuster hat. Bedingungen:   
  - Mindestens 3 gelernte Regeln für den Vendor (MIN_RULES_FOR_GENERALIZATION)
  - Mindestens 60% der Regeln zeigen auf dasselbe Konto (MIN_DOMINANCE_RATIO)

  Wenn ja, wird eine synthetische Regel erzeugt mit Score = 0.85 * dominance_ratio.

  Regelquellen

  Regeln werden aus drei Quellen geladen:

  ┌────────────────┬──────────────────────────────────────────┬─────────────────────────────────────────────────┐   
  │     Quelle     │                   Pfad                   │                  Beschreibung                   │   
  ├────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────┤   
  │ Statische      │ configs/accounting/rules/*.yaml          │ Manuell gepflegte Kontierungsregeln             │   
  │ Regeln         │                                          │                                                 │   
  ├────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────┤   
  │ Learned Rules  │ .taskforce_accounting/learned_rules.yaml │ Auto-generiert aus bestätigten Buchungen        │   
  │                │                                          │ (HITL/High-Confidence)                          │   
  ├────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────┤   
  │ Legacy-Format  │ expense_categories in YAML               │ Rückwärtskompatibles Keyword-basiertes Format   │   
  │                │                                          │ (Priorität 10)                                  │   
  └────────────────┴──────────────────────────────────────────┴─────────────────────────────────────────────────┘   

  Die Learned Rules werden bei jedem Aufruf auf Änderungen geprüft (via st_mtime), sodass neue Regeln sofort wirksam   werden.

  Matching-Ablauf (execute())

  Invoice rein
      │
      ├─ Supplier-Name extrahieren (aus verschiedenen Feldern)
      ├─ Line Items extrahieren (oder Fallback aus Gesamtbetrag)
      │
      └─ Pro Line Item:
          ├─ Phase 1: Vendor-Only Rules prüfen (score=1.0)
          ├─ Phase 2: Vendor+Item Rules prüfen (exact=1.0 oder semantic≥threshold)
          ├─ Phase 2.5: Vendor-Generalisierung (Fallback)
          │
          ├─ Alle Matches nach (priority DESC, similarity DESC) sortieren
          │
          └─ Ambiguitätsprüfung:
              ├─ Score-Differenz < 0.05 UND
              ├─ unterschiedliche Konten UND
              ├─ Priority-Differenz < 10
              └─ → Dann als "ambiguous" markiert (für HITL-Review)

  Output

  {
      "success": True,
      "rule_matches": [...],         # Welche Regel pro Position gegriffen hat
      "booking_proposals": [...],    # Soll-Buchungen (debit) + Haben (credit auf 1600)
      "unmatched_items": [...],      # Positionen ohne Regelzuordnung
      "ambiguous_items": [...],      # Positionen mit mehrdeutigem Match
  }

  Jede Buchung enthält Soll-Konto, Betrag, VSt-Konto, VSt-Betrag, Rechtsgrundlage und Konfidenz-Score. Am Ende wird 
  automatisch die Gegenbuchung auf Konto 1600 (Verbindlichkeiten a.L.L.) hinzugefügt.

  Zusammenfassung

  Die Engine ist ein Hybrid aus deterministischem Rule-Matching und optionaler Embedding-Similarity — sie trifft    
  alle Entscheidungen ohne LLM, lernt aber aus bestätigten Buchungen (learned rules) und kann über Vendor-Profile   
  generalisieren, wenn neue Positionen eines bekannten Lieferanten auftauchen.