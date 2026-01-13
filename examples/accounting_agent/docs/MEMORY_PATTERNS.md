# Accounting Agent Memory Patterns

**Purpose:** Best practices for using long-term memory in accounting workflows

---

## Overview

The Accounting Agent can remember:
- **Supplier information** and typical booking patterns
- **Project-to-cost-center mappings**
- **User preferences** for invoice handling
- **Business rules** and approval workflows
- **Historical decisions** and their rationale

This enables the agent to provide **context-aware suggestions** and **automate repetitive bookings** while learning from corrections.

---

## Entity Types for Accounting

### 1. Supplier (Lieferant)

```json
{
  "name": "Amazon_Web_Services",
  "entityType": "Supplier",
  "observations": [
    "Cloud infrastructure provider",
    "Monthly recurring invoices",
    "Typically booked to account 6805 (IT-Kosten)",
    "VAT: Standard rate 19%",
    "Payment terms: 30 days net",
    "Country: Luxembourg (EU)"
  ]
}
```

**Relations:**
- `typically_booked_to` → Account_6805
- `assigned_to` → CostCenter_8000

### 2. Project (Projekt)

```json
{
  "name": "Project_Phoenix_2024",
  "entityType": "Project",
  "observations": [
    "Internal code: PHX-2024",
    "Cost center: 4200",
    "Budget owner: Alice Schmidt",
    "Budget: 50000 EUR",
    "Active since: 2024-01-01",
    "Expected end: 2024-12-31"
  ]
}
```

**Relations:**
- `assigned_to` → CostCenter_4200
- `managed_by` → User_Alice_Schmidt
- `incurs_costs_from` → Supplier_Freelancer_Mueller

### 3. Account (Buchungskonto)

```json
{
  "name": "Account_6805",
  "entityType": "Account",
  "observations": [
    "DATEV account number: 6805",
    "Description: IT and software costs",
    "Account type: Expense",
    "VAT deductible: Yes",
    "Requires approval: Yes (>1000 EUR)"
  ]
}
```

### 4. BusinessRule (Geschäftsregel)

```json
{
  "name": "Approval_Rule_IT_Expenses",
  "entityType": "BusinessRule",
  "observations": [
    "IT expenses > 1000 EUR require IT manager approval",
    "Approval must be documented in invoice notes",
    "Approver: John Doe (IT Manager)",
    "Timeout: 3 business days",
    "Active since: 2024-01-01"
  ]
}
```

### 5. UserPreference (Benutzer-Präferenzen)

```json
{
  "name": "User_Accountant_Schmidt",
  "entityType": "User",
  "observations": [
    "Prefers invoices >5000 EUR to be split by project",
    "Requires supplier history before first booking",
    "Uses DATEV SKR03 account numbers",
    "Language: German",
    "Working hours: 8-17 CET"
  ]
}
```

### 6. Decision (Entscheidung)

```json
{
  "name": "Decision_Hosting_Cost_Split_Q1_2024",
  "entityType": "Decision",
  "observations": [
    "Decided on: 2024-03-15",
    "Decision: Split hosting costs 70/30 between Project A and B",
    "Rationale: Project A uses more storage and bandwidth",
    "Approved by: CFO Meyer",
    "Valid until: 2024-06-30",
    "Review date: 2024-06-01"
  ]
}
```

---

## Workflow Examples

### Example 1: Learning Supplier Patterns

**First Invoice from New Supplier:**

```
User: "Neue Rechnung von 'DigitalOcean' für Server-Hosting: 450 EUR"

Agent: [No memory found]
Agent: "Dies ist die erste Rechnung von DigitalOcean.
       Auf welches Konto soll ich buchen?"

User: "Konto 6805 (IT-Kosten), Kostenstelle 8000"

Agent: [Stores in memory]
create_entities([{
  "name": "DigitalOcean",
  "entityType": "Supplier",
  "observations": [
    "Cloud hosting provider",
    "First invoice: 2024-01-15",
    "Typical amount: 450 EUR monthly",
    "Booked to account 6805",
    "Assigned to cost center 8000"
  ]
}])

create_relations([
  {"from": "DigitalOcean", "to": "Account_6805", "relationType": "typically_booked_to"},
  {"from": "DigitalOcean", "to": "CostCenter_8000", "relationType": "assigned_to"}
])
```

**Second Invoice (Next Month):**

```
User: "Neue DigitalOcean-Rechnung: 475 EUR"

Agent: [Searches memory]
search_nodes("DigitalOcean")
# Found: typically_booked_to Account_6805, assigned_to CostCenter_8000

Agent: "Ich schlage folgende Buchung vor (basierend auf bisherigen Buchungen):

       Soll:  6805 (IT-Kosten)     475,00 EUR
       Haben: 1200 (Bank)          475,00 EUR

       Kostenstelle: 8000

       Soll ich diese Buchung vorbereiten?"
```

---

### Example 2: Project-Based Cost Allocation

**Setup Phase:**

```python
# Store project information
create_entities([
  {
    "name": "Project_Phoenix",
    "entityType": "Project",
    "observations": [
      "Internal code: PHX-2024",
      "Cost center: 4200",
      "Budget: 50000 EUR",
      "Budget owner: Alice Schmidt"
    ]
  },
  {
    "name": "Freelancer_Mueller",
    "entityType": "Supplier",
    "observations": [
      "Software developer",
      "Hourly rate: 120 EUR",
      "Works exclusively on Project Phoenix"
    ]
  }
])

create_relations([
  {"from": "Freelancer_Mueller", "to": "Project_Phoenix", "relationType": "works_on"},
  {"from": "Project_Phoenix", "to": "CostCenter_4200", "relationType": "assigned_to"}
])
```

**Invoice Processing:**

```
User: "Rechnung von Freelancer Müller: 4800 EUR für 40 Stunden"

Agent: [Searches memory]
search_nodes("Freelancer Mueller")
# Found: works_on Project_Phoenix
open_nodes(["Project_Phoenix"])
# Found: assigned_to CostCenter_4200

Agent: "Ich ordne die Rechnung automatisch zu:

       Projekt: Phoenix (PHX-2024)
       Kostenstelle: 4200
       Budget-Owner: Alice Schmidt (zur Genehmigung)

       Budget-Status: 4.800 EUR von 50.000 EUR verwendet (9,6%)

       Soll ich die Genehmigung an Alice weiterleiten?"
```

---

### Example 3: Learning from Corrections

**Initial Suggestion:**

```
User: "Rechnung von 'Office Depot' für Büromaterial: 250 EUR"

Agent: [Searches memory - nothing found]
Agent: "Auf welches Konto soll ich buchen?"

User: "Das gehört auf 6815 (Büromaterial), nicht 6800"

Agent: [Stores correction]
create_entities([{
  "name": "Office_Depot",
  "entityType": "Supplier",
  "observations": [
    "Office supplies vendor",
    "Booked to account 6815 (Büromaterial)",
    "NOTE: User correction - initially suggested 6800 (wrong)"
  ]
}])
```

**Next Time:**

```
User: "Neue Office Depot Rechnung: 180 EUR"

Agent: [Remembers correction]
Agent: "Buchungsvorschlag:

       Soll:  6815 (Büromaterial)  180,00 EUR
       Haben: 1200 (Bank)          180,00 EUR

       (Frühere Korrekturen berücksichtigt)"
```

---

### Example 4: Complex Cost Splitting

**Decision Documentation:**

```python
create_entities([{
  "name": "Decision_AWS_Cost_Split_2024",
  "entityType": "Decision",
  "observations": [
    "Decided: 2024-02-01",
    "AWS costs split by usage: 60% Project A, 40% Project B",
    "Based on: EC2 instance allocation",
    "Approved by: CTO and CFO",
    "Valid: Q1-Q2 2024",
    "Review: End of Q2"
  ]
}])

create_relations([
  {"from": "Decision_AWS_Cost_Split_2024", "to": "Amazon_Web_Services", "relationType": "applies_to"},
  {"from": "Decision_AWS_Cost_Split_2024", "to": "Project_A", "relationType": "affects"},
  {"from": "Decision_AWS_Cost_Split_2024", "to": "Project_B", "relationType": "affects"}
])
```

**Automated Split:**

```
User: "AWS-Rechnung März: 3000 EUR"

Agent: [Searches memory]
search_nodes("AWS cost split")
# Found: Decision_AWS_Cost_Split_2024

Agent: "Ich wende die genehmigte Aufteilung an (Entscheidung vom 01.02.2024):

       Soll:  6805 (IT-Kosten) KST 4100 (Projekt A)  1.800,00 EUR (60%)
       Soll:  6805 (IT-Kosten) KST 4200 (Projekt B)  1.200,00 EUR (40%)
       Haben: 1200 (Bank)                            3.000,00 EUR

       Hinweis: Review dieser Aufteilung fällig am Ende Q2"
```

---

### Example 5: Compliance & Approval Rules

**Rule Setup:**

```python
create_entities([{
  "name": "Approval_Rule_Capital_Expenses",
  "entityType": "BusinessRule",
  "observations": [
    "All capital expenses (>800 EUR net) require CFO approval",
    "Must check: Is this asset depreciable?",
    "Approval process: Email to cfo@company.de",
    "Required docs: Invoice + asset description",
    "Based on: German tax law (§6 EStG)"
  ]
}])

create_relations([
  {"from": "Approval_Rule_Capital_Expenses", "to": "Account_0420", "relationType": "applies_to"}
])
```

**Automatic Compliance Check:**

```
User: "Rechnung für neue Server-Hardware: 2500 EUR netto"

Agent: [Checks memory for rules]
search_nodes("capital expenses approval")
# Found: Approval_Rule_Capital_Expenses

Agent: "⚠️ GENEHMIGUNG ERFORDERLICH

       Diese Rechnung überschreitet 800 EUR (Anlagevermögen).

       Erforderlich:
       ✓ CFO-Genehmigung (cfo@company.de)
       ✓ Asset-Beschreibung für Anlagenbuchhaltung
       ✓ Prüfung: Abschreibungsfähig? (§6 EStG)

       Vorgeschlagenes Konto: 0420 (Hardware/Anlagevermögen)

       Soll ich die Genehmigungsanfrage vorbereiten?"
```

---

## Memory Maintenance

### Regular Updates

```python
# Update outdated information
delete_observations("Project_Phoenix", ["Budget: 50000 EUR"])
add_observations("Project_Phoenix", ["Budget increased to 75000 EUR as of Q2"])

# Archive completed projects
delete_relations([{
  "from": "Freelancer_Mueller",
  "to": "Project_Phoenix",
  "relationType": "works_on"
}])
add_observations("Project_Phoenix", ["Status: Completed 2024-06-30"])
```

### Periodic Review

Set up quarterly memory reviews:

1. **Check outdated decisions** (valid_until dates)
2. **Update supplier patterns** (changed terms, new accounts)
3. **Archive old projects** (mark as completed)
4. **Consolidate duplicate entities** (e.g., "AWS" vs "Amazon Web Services")

---

## Integration with Kontierung Rules

Memory complements YAML-based rules:

**YAML Rule (Static):**
```yaml
# rules/kontierung_rules.yaml
- pattern: "cloud|hosting|server"
  account: 6805
  description: "IT infrastructure costs"
```

**Memory (Dynamic):**
```python
# Learns supplier-specific exceptions
add_observations("Supplier_SpecialCloudProvider", [
  "Exception: Booked to 6810 instead of 6805",
  "Reason: Part of R&D project (research costs)",
  "Approved by: CFO on 2024-03-20"
])
```

---

## Best Practices

### 1. Start Simple

```python
# First invoice: Just store basic info
create_entities([{
  "name": "New_Supplier",
  "entityType": "Supplier",
  "observations": ["First invoice: 2024-01-15", "Booked to account 6800"]
}])
```

### 2. Add Details Over Time

```python
# After 3 invoices: Pattern emerges
add_observations("New_Supplier", [
  "Typical monthly amount: ~500 EUR",
  "Payment terms: 30 days net",
  "Always includes 19% VAT"
])
```

### 3. Document Exceptions

```python
# When deviation occurs
add_observations("Regular_Supplier", [
  "Exception: Invoice 2024-03-15 booked to 6900 instead of 6800",
  "Reason: Special project expense",
  "One-time deviation"
])
```

### 4. Link Related Information

```python
# Build knowledge graph
create_relations([
  {"from": "Supplier_X", "to": "Project_Y", "relationType": "typically_works_on"},
  {"from": "Project_Y", "to": "CostCenter_Z", "relationType": "assigned_to"},
  {"from": "CostCenter_Z", "to": "User_Manager", "relationType": "approved_by"}
])
```

---

## Privacy & Compliance

**What to Store:**
- ✅ Supplier names (public companies)
- ✅ Account numbers (internal codes)
- ✅ Business rules and decisions
- ✅ Project codes and cost centers
- ✅ User preferences (workflow-related)

**What NOT to Store:**
- ❌ Personal bank account numbers
- ❌ Credit card details
- ❌ Full invoice documents
- ❌ Employee salaries
- ❌ Confidential contract terms

**GoBD Compliance:**
- Memory is for **workflow optimization**, not **audit trail**
- Actual bookings must still go through GoBD-compliant system
- Memory = "Agent's brain", Audit Log = "Legal record"

---

## Troubleshooting

### Memory Not Used

```bash
# Check if memory tools are loaded
Agent: [At conversation start]
read_graph()  # Should retrieve stored entities

# If empty, check config
# Verify: mcp_servers configured in accounting_agent.yaml
```

### Conflicting Information

```python
# Scenario: Two different patterns for same supplier
search_nodes("Supplier_X")
# Found: "Booked to 6800" AND "Booked to 6805"

# Resolution: Ask user or consolidate
delete_observations("Supplier_X", ["Booked to 6800"])
add_observations("Supplier_X", [
  "Booked to 6805 (updated 2024-06-01)",
  "Previously: 6800 (until May 2024)"
])
```

---

## Example Session

**Complete workflow with memory:**

```
Session 1 (Learning):
User: "Rechnung von 'TechSupplier GmbH': 1200 EUR für Software-Lizenzen"
Agent: "Neue Rechnung. Auf welches Konto?"
User: "6825 (Software), Kostenstelle 8000, Projekt 'Digitalisierung'"
Agent: [Stores all information in memory]

Session 2 (Two weeks later):
User: "Neue TechSupplier-Rechnung: 1200 EUR"
Agent: "Ich schlage vor:
       Soll:  6825 (Software)     1.200 EUR
       Haben: 1200 (Bank)         1.200 EUR

       Kostenstelle: 8000
       Projekt: Digitalisierung

       Basierend auf Rechnung vom 15.01.2024"

Session 3 (Exception):
User: "TechSupplier-Rechnung: 3500 EUR (Sonderausgabe)"
Agent: "⚠️ Betrag weicht ab vom üblichen 1200 EUR

       Soll ich trotzdem die gleiche Kontierung verwenden?
       Oder handelt es sich um eine andere Kategorie?"
```

---

**Last Updated:** 2026-01-13
**Author:** Taskforce Team
