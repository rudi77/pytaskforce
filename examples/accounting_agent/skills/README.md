# Accounting Agent Skills

Dieses Verzeichnis enthält die Skills für den Accounting Agent. Skills ermöglichen eine modulare, Token-effiziente Workflow-Steuerung.

## Übersicht

```
skills/
├── invoice-explanation/     # Fragen zu Rechnungen beantworten
├── smart-booking-auto/      # Automatischer Buchungsworkflow
└── smart-booking-hitl/      # Human-in-the-Loop Workflow
```

## Skills im Detail

### 1. invoice-explanation

**Trigger:** `INVOICE_QUESTION` Intent

Beantwortet Fragen zu Rechnungen ohne Tool-Aufrufe. Minimaler Token-Verbrauch.

**Beispiel-Anfragen:**
- "Wie hoch ist die MwSt?"
- "Wer ist der Lieferant?"
- "Warum gibt es zwei Steuersätze?"

**Ressourcen:**
- `german_tax_glossary.yaml` - Deutsches Steuer-Glossar

### 2. smart-booking-auto

**Trigger:** `INVOICE_PROCESSING` Intent

Führt den automatischen Buchungsworkflow aus:

```
1. docling_extract → invoice_extract
2. check_compliance
3. semantic_rule_engine
4. confidence_evaluator
5. Bei Confidence ≥95%: Auto-Book
6. Sonst: → smart-booking-hitl
```

**Ressourcen:**
- `kontierung_rules.yaml` - SKR03 Buchungsregeln
- `compliance_rules.yaml` - §14 UStG Compliance

### 3. smart-booking-hitl

**Trigger:** Automatisch von `smart-booking-auto` bei:
- Confidence < 95%
- Hard Gate ausgelöst (new_vendor, high_amount, critical_account)

Führt den HITL-Workflow aus:

```
1. hitl_review(create)
2. ask_user → User-Entscheidung
3. hitl_review(process)
4. rule_learning
5. audit_log
```

**Ressourcen:**
- `user_prompts.yaml` - User-Prompt-Templates

## Token-Einsparung

| Szenario | Alte Methode | Skills | Einsparung |
|----------|--------------|--------|------------|
| Frage beantworten | ~1500 tok | ~300 tok | **80%** |
| Auto-Booking | ~1500 tok | ~800 tok | **47%** |
| HITL-Booking | ~1500 tok | ~1200 tok | **20%** |

## Verwendung

### Programmatisch

```python
from accounting_agent.application import (
    create_accounting_skill_activator,
    SkillIntegration,
    AccountingIntent,
)

# Skill-Aktivator erstellen
activator = create_accounting_skill_activator()

# Skill nach Intent aktivieren
skill = activator.activate_by_intent(AccountingIntent.INVOICE_PROCESSING)

# Integration für automatisches Switching
integration = SkillIntegration(activator)
enhanced_prompt = integration.enhance_prompt(base_prompt, intent)

# Nach Tool-Aufruf prüfen
switch_result = integration.on_tool_result("confidence_evaluator", output)
```

### Über Agent-Konfiguration

In `accounting_agent.yaml`:

```yaml
skills:
  directories:
    - "${PLUGIN_PATH}/skills"
  activation:
    mode: "intent_based"
    auto_switch: true
```

## Skill-Entwicklung

### SKILL.md Format

```markdown
---
name: skill-name
description: |
  Was der Skill macht und wann er aktiviert wird.
allowed_tools: tool1 tool2 tool3
---

# Skill-Instruktionen

Markdown-Body mit Workflow-Anweisungen.
```

### Ressourcen hinzufügen

Dateien im `resources/`-Verzeichnis werden automatisch als Skill-Ressourcen verfügbar:

```
skill-name/
├── SKILL.md
└── resources/
    ├── config.yaml
    └── templates/
        └── prompt.md
```

Zugriff:
```python
content = skill.read_resource("resources/config.yaml")
```

## Architektur

```
┌─────────────────────────────────────────────┐
│           ACCOUNTING AGENT                   │
│  ┌───────────────────────────────────────┐  │
│  │     Basis-System-Prompt (minimal)     │  │
│  │     - Intent-Erkennung                │  │
│  │     - Skill-Aktivierungslogik         │  │
│  └───────────────────────────────────────┘  │
│                     │                        │
│         Intent → SkillActivator              │
│                     │                        │
│  ┌──────────┬───────┴───────┬──────────┐   │
│  │          │               │          │   │
│  ▼          ▼               ▼          │   │
│ invoice-  smart-          smart-       │   │
│ explana-  booking-        booking-     │   │
│ tion      auto            hitl         │   │
│  │          │               │          │   │
│  │          └───────────────┘          │   │
│  │          Automatischer Wechsel      │   │
│  │          bei Confidence <95%        │   │
│  │          oder Hard Gate             │   │
└──┴──────────────────────────────────────┘
```
