# Accounts Payable PoC Plugin

This plugin implements the **"vom Beleg zur Vorkontierung"** PoC described in the prompt. It provides
three tools aligned to the PoC roles plus a mock review log generator. The roles are
also available as **agent configurations**, coordinated by an orchestrator.

## Tools

- **ArchitectConfigTool** (`architect_configure_system`)
  - Validates a JSON configuration for chart of accounts, tax rates, vendors, and cost centers.
- **GatekeeperTool** (`gatekeeper_extract_invoice`)
  - Extracts invoice fields from JSON payloads and checks §14 UStG requirements.
- **TaxWizardTool** (`tax_wizard_assign_accounts`)
  - Matches vendors, assigns accounts, and applies VAT logic (domestic vs. reverse charge).
- **ReviewLogTool** (`review_log_generate`)
  - Produces a mock approval entry for the human review step.

## Agent Roles (Configs)

Agent configs live under `configs/agents/`:

- `architect.yaml`
- `gatekeeper.yaml`
- `tax_wizard.yaml`
- `orchestrator.yaml` (coordinates the flow with `call_agent`)

## Sample Data

Sample payloads live under `configs/data/`:

- `system_config_saas_skr03.json` – Architect config for SaaS in SKR03.
- `sample_invoice_cloud.json` – Gatekeeper input invoice.
- `erp_mock.json` – Optional mock ERP vendor data.

## Document Extraction MCP (Optional)

The PoC can reuse the document extraction MCP server for OCR-based invoice parsing. The
plugin config `configs/ap_poc_agent.yaml` already wires the MCP server found under
`servers/document-extraction-mcp`. When available, the Gatekeeper agent may call
`ocr_extract` and `layout_detect` before running the JSON-based extraction. The
Gatekeeper tool can also accept a non-JSON invoice path and will attempt OCR
extraction directly via the MCP tools.

## Example Flow (CLI)

```bash
# Run the orchestrator with the plugin loaded
TASKFORCE_PROFILE=src/taskforce/plugins/ap_poc_agent/configs/ap_poc_agent.yaml \
  taskforce run mission "Run AP PoC" --plugin src/taskforce/plugins/ap_poc_agent
```

Then call the tools or agents in sequence:

1. `architect_configure_system` with `configs/data/system_config_saas_skr03.json`
2. `gatekeeper_extract_invoice` with `configs/data/sample_invoice_cloud.json`
3. `tax_wizard_assign_accounts` with the invoice + config output
4. `review_log_generate` with the booking proposal
