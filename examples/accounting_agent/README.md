# Accounting Agent Example

A specialized accounting agent for German invoice processing and bookkeeping (Buchhaltung). This example demonstrates how to build domain-specific agents using the Taskforce framework.

## Overview

The Accounting Agent processes German invoices by:

1. **Extracting** invoice data from PDFs/images using Docling
2. **Validating** compliance with §14 UStG (German tax law)
3. **Applying** deterministic accounting rules for account assignment (Kontierung)
4. **Calculating** VAT, depreciation (AfA), and GWG treatment
5. **Logging** all operations in a GoBD-compliant audit trail

This agent can work autonomously or interactively with human oversight.

## Features

### Accounting Q&A (Expert Mode)
- Answers general bookkeeping questions (Kontierung, UStG/EStG/HGB, GoBD)
- Provides short legal references and practical SKR03/SKR04 examples
- Triggered via `ACCOUNTING_QUESTION` intent (`accounting-expert` skill)

### Document Extraction
- **Tool**: `docling_extract`
- Converts PDF and image invoices to structured Markdown
- Supports scanned documents and digital invoices
- Extracts tables, amounts, and metadata

### Compliance Checking
- **Tool**: `check_compliance`
- Validates against §14 UStG mandatory fields (Pflichtangaben)
- Handles Kleinbetragsrechnung (§33 UStDV) special rules
- Returns detailed legal references for missing fields

### Rule-Based Account Assignment
- **Tool**: `apply_kontierung_rules`
- YAML-based deterministic rules (no LLM guessing)
- Supports SKR03 and SKR04 chart of accounts
- Keyword matching with amount thresholds (GWG vs. Anlagevermögen)
- Handles 15+ expense categories automatically

### Tax Calculations
- **Tool**: `calculate_tax`
- VAT calculation (19%, 7%, reverse charge)
- Input tax (Vorsteuer) deduction
- Depreciation schedules (AfA) per asset type
- GWG threshold check (€800)

### Audit Logging
- **Tool**: `audit_log`
- GoBD-compliant immutable logs
- SHA-256 integrity hashes
- ISO 8601 timestamps (UTC)
- Retention-ready for 10-year archiving

## Installation

### Option 1: Standalone Usage

```bash
cd examples/accounting_agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install docling CLI (required for PDF extraction)
pip install docling
```

### Option 2: Integration with Taskforce

```bash
# Install taskforce (from project root)
cd /home/user/pytaskforce
uv sync

# Install accounting agent dependencies
cd examples/accounting_agent
pip install -r requirements.txt
```

## Usage

### Standalone Tool Usage

You can use the accounting tools directly without the Taskforce framework:

```python
from accounting_agent.tools import DoclingTool, ComplianceCheckerTool

# Extract invoice from PDF
docling = DoclingTool()
result = await docling.execute(file_path="invoice.pdf")
print(result["markdown"])

# Check compliance
checker = ComplianceCheckerTool()
invoice_data = {
    "supplier_name": "ACME GmbH",
    "invoice_number": "INV-2024-001",
    "net_amount": 1000.00,
    "vat_rate": 0.19,
    # ... more fields
}
compliance = await checker.execute(invoice_data=invoice_data)
print(compliance["is_compliant"])
```

### Integration with Taskforce

The accounting agent can be used as a Taskforce agent profile:

```bash
# Run accounting agent via Taskforce CLI
taskforce run mission "Prüfe die Rechnung invoice.pdf und erstelle einen Buchungsvorschlag" \
    --profile accounting_agent
```

Or programmatically:

```python
from taskforce.application.factory import AgentFactory

factory = AgentFactory()
agent = await factory.create_agent(profile="accounting_agent")

result = await agent.execute_mission(
    "Analysiere die Rechnung und prüfe die Compliance",
    session_id="invoice-2024-001"
)
```

## Configuration

### Accounting Rules

Rules are defined in `configs/accounting/rules/kontierung_rules.yaml`:

```yaml
expense_categories:
  office_supplies:
    keywords:
      - "Bürobedarf"
      - "Schreibwaren"
    debit_account: "4930"
    legal_basis: "§4 Abs. 4 EStG"

  it_equipment:
    keywords:
      - "Computer"
      - "Laptop"
    conditions:
      - if_amount_below: 800
        debit_account: "4985"  # GWG
      - if_amount_above: 800
        debit_account: "0420"  # Anlagevermögen
        afa_years: 3
```

### Compliance Rules

Compliance requirements are configured in `configs/accounting/rules/compliance_rules.yaml`:

```yaml
mandatory_fields:
  supplier_name:
    legal_ref: "§14 Abs. 4 Nr. 1 UStG"
    severity: "error"

  invoice_date:
    legal_ref: "§14 Abs. 4 Nr. 3 UStG"
    severity: "error"
```

### Agent Profile

The agent behavior is configured in `configs/accounting_agent.yaml`:

```yaml
profile: accounting_agent
specialist: accounting

agent:
  max_steps: 50
  planning_strategy: plan_and_execute

tools:
  - docling_extract
  - apply_kontierung_rules
  - check_compliance
  - calculate_tax
  - audit_log
  - ask_user
```

Skills and intents are defined in the same config:

```yaml
skills:
  available:
    - name: accounting-expert
      trigger: "ACCOUNTING_QUESTION"
```

## Domain Models

The agent uses typed domain models defined in `accounting_agent/domain/`:

```python
from accounting_agent.domain import Invoice, LineItem, BookingProposal

# Create an invoice
invoice = Invoice(
    invoice_id="INV-001",
    supplier_name="ACME GmbH",
    invoice_number="2024-001",
    invoice_date=date(2024, 1, 15),
    total_gross=Decimal("1190.00"),
    total_net=Decimal("1000.00"),
    total_vat=Decimal("190.00"),
    line_items=[
        LineItem(
            description="Laptop Dell XPS 13",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            net_amount=Decimal("1000.00"),
            vat_rate=Decimal("0.19"),
            vat_amount=Decimal("190.00")
        )
    ]
)
```

## Examples

### Example 1: Process Invoice PDF

```python
from accounting_agent.tools import (
    DoclingTool,
    ComplianceCheckerTool,
    RuleEngineTool,
    AuditLogTool
)

async def process_invoice(pdf_path: str):
    # Step 1: Extract document
    docling = DoclingTool()
    extraction = await docling.execute(file_path=pdf_path)

    if not extraction["success"]:
        return {"error": extraction["error"]}

    markdown = extraction["markdown"]

    # Step 2: Parse invoice data (simplified - in reality use LLM)
    invoice_data = parse_markdown_to_invoice(markdown)

    # Step 3: Check compliance
    checker = ComplianceCheckerTool()
    compliance = await checker.execute(invoice_data=invoice_data)

    if not compliance["is_compliant"]:
        print("⚠️  Compliance issues found:")
        for error in compliance["errors"]:
            print(f"  - {error['message']} ({error['legal_reference']})")

    # Step 4: Apply accounting rules
    rule_engine = RuleEngineTool(rules_path="configs/accounting/rules/")
    booking = await rule_engine.execute(
        invoice_data=invoice_data,
        chart_of_accounts="SKR03"
    )

    print(f"✅ Applied {booking['rules_applied']} rules")
    print(f"📋 Generated {len(booking['booking_proposals'])} booking entries")

    # Step 5: Create audit log
    audit = AuditLogTool()
    await audit.execute(
        operation="invoice_processed",
        document_id=invoice_data.get("invoice_number"),
        details={
            "source_file": pdf_path,
            "compliance_status": compliance["is_compliant"],
            "booking_entries": len(booking["booking_proposals"])
        },
        decision="Invoice processed and booked",
        legal_basis="§14 UStG, §238 HGB"
    )

    return {
        "success": True,
        "compliance": compliance,
        "bookings": booking["booking_proposals"]
    }
```

### Example 2: VAT Calculation

```python
from accounting_agent.tools import TaxCalculatorTool

async def calculate_invoice_tax():
    calc = TaxCalculatorTool()

    # Calculate VAT from net amount
    vat_result = await calc.execute(
        calculation_type="vat",
        amount=1000.00,
        vat_rate=0.19
    )

    print(f"Net: {vat_result['net_amount']} EUR")
    print(f"VAT: {vat_result['vat_amount']} EUR")
    print(f"Gross: {vat_result['gross_amount']} EUR")

    # Check if asset qualifies as GWG
    gwg_result = await calc.execute(
        calculation_type="gwg_check",
        amount=750.00
    )

    print(f"Treatment: {gwg_result['treatment']}")
    print(f"Legal basis: {gwg_result['legal_basis']}")
```

## Telegram Integration

The accounting agent can be accessed via Telegram, allowing conversational invoice processing with interactive clarification questions.

### Prerequisites

1. **Create a Telegram Bot** via [@BotFather](https://t.me/BotFather) and save the token
2. **Set the environment variable**:
   ```bash
   export TELEGRAM_BOT_TOKEN="your-bot-token-here"
   ```

### Start the API Server

```bash
# From the project root
uvicorn taskforce.api.server:app --host 0.0.0.0 --port 8000
```

### Register the Telegram Webhook

Register your webhook URL with the `profile` and `plugin_path` query parameters so that Telegram messages are routed to the accounting agent:

```bash
# Set your public URL (e.g., via ngrok for development)
WEBHOOK_URL="https://your-domain.com/api/v1/gateway/telegram/webhook?profile=accounting_agent&plugin_path=examples/accounting_agent"

# Register webhook with Telegram
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${WEBHOOK_URL}\"}"
```

### How It Works

The Telegram integration leverages the existing Communication Gateway:

```
User sends message on Telegram
    → Telegram webhook delivers to /api/v1/gateway/telegram/webhook
    → TelegramInboundAdapter normalizes the payload
    → CommunicationGateway executes accounting agent
    → Agent processes invoice / asks clarification questions
    → Response sent back via Telegram
```

**Clarification Flow (ask_user):**

When the agent encounters ambiguities (e.g., missing invoice fields, unclear account assignment), it uses the `ask_user` tool. This:

1. **Pauses** agent execution and saves state
2. **Sends** the question to the user via Telegram
3. **Waits** for the user's reply (next Telegram message)
4. **Resumes** execution with the user's answer
5. If the answer is unclear, **asks again** with a more specific question

**Proactive Notifications (send_notification):**

The agent can proactively notify the user via `send_notification` (e.g., booking completed, errors detected). The user is auto-registered as a notification recipient on first message.

### Example Conversation

```
User:  Buche diese Rechnung: [PDF anhängen oder Text]
Agent: 📋 RECHNUNGSDETAILS:
       • Lieferant: Büromarkt AG
       • Rechnungsnummer: 12345
       • Bruttobetrag: 238,00 EUR

       📦 POSITIONEN:
       1. Druckerpapier A4 - 10 x 5,00 EUR (19%)
          → Vorschlag: Konto 4930 (Büromaterial)
       2. Unbekannter Artikel - 1 x 40,00 EUR (19%)
          → ❓ Kein passendes Konto gefunden

       Auf welches Konto soll "Unbekannter Artikel" gebucht werden?

User:  Auf 4930 Büromaterial
Agent: ✅ Buchung durchgeführt und Regel gespeichert:
       - Druckerpapier A4 → Konto 4930 (Büromaterial)
       - Unbekannter Artikel → Konto 4930 (Büromaterial)
```

## Architecture

```
examples/accounting_agent/
├── accounting_agent/
│   ├── __init__.py
│   ├── domain/              # Domain models (pure Python)
│   │   ├── __init__.py
│   │   ├── models.py        # Invoice, BookingProposal, etc.
│   │   └── errors.py        # Domain exceptions
│   └── tools/               # Specialized tools
│       ├── __init__.py
│       ├── tool_base.py     # Base classes
│       ├── docling_tool.py
│       ├── rule_engine_tool.py
│       ├── compliance_checker_tool.py
│       ├── tax_calculator_tool.py
│       └── audit_log_tool.py
├── configs/
│   ├── accounting_agent.yaml
│   └── rules/
│       ├── kontierung_rules.yaml
│       └── compliance_rules.yaml
├── tests/
│   └── test_*.py
├── requirements.txt
└── README.md (this file)
```

## Legal Compliance

This example implements German accounting standards:

- **§14 UStG**: Invoice mandatory fields (Pflichtangaben)
- **§33 UStDV**: Small invoice exemptions (Kleinbetragsrechnung)
- **§6 Abs. 2 EStG**: Low-value assets (GWG)
- **§7 EStG**: Depreciation (AfA)
- **§15 UStG**: Input tax deduction (Vorsteuerabzug)
- **§13b UStG**: Reverse charge
- **GoBD**: Proper bookkeeping principles

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=accounting_agent tests/
```

## Extending the Agent

### Adding New Rules

Edit `configs/accounting/rules/kontierung_rules.yaml`:

```yaml
expense_categories:
  my_new_category:
    keywords:
      - "custom keyword"
    debit_account: "4XXX"
    legal_basis: "§X EStG"
```

### Adding New Tools

Create a new tool in `accounting_agent/tools/`:

```python
from accounting_agent.tools.tool_base import ApprovalRiskLevel

class MyCustomTool:
    @property
    def name(self) -> str:
        return "my_custom_tool"

    @property
    def description(self) -> str:
        return "Description of what the tool does"

    async def execute(self, **params) -> dict:
        # Tool implementation
        return {"success": True, "result": "..."}
```

Then register it in `accounting_agent/tools/__init__.py`.

## Limitations

- **Language**: German only (can be adapted for other locales)
- **Chart of Accounts**: SKR03 and SKR04 only
- **Docling**: Requires external CLI installation
- **OCR Quality**: Depends on invoice scan quality
- **Rule Coverage**: Limited to predefined categories

## Contributing

This is an example/template. Adapt it to your needs:

1. Fork or copy the `examples/accounting_agent` directory
2. Modify domain models for your use case
3. Customize rules in `configs/accounting/rules/`
4. Add your own tools as needed
5. Adjust compliance checks for your jurisdiction

## License

Same as Taskforce framework (see main project LICENSE file).

## Support

For questions about:
- **Taskforce framework**: See main project documentation
- **German accounting**: Consult with a Steuerberater
- **Docling**: https://github.com/DS4SD/docling

## Related Examples

- See `examples/` directory for more agent examples
- Check Taskforce documentation for agent development guides

---

**Disclaimer**: This is a demonstration/example only. Always consult with a qualified Steuerberater (tax advisor) for production accounting systems. No warranty is provided regarding legal compliance or correctness of calculations.
