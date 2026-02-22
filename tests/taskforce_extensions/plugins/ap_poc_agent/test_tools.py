import asyncio
import json
import sys
from pathlib import Path

sys.path.append("src/taskforce_extensions/plugins/ap_poc_agent")

from ap_poc_agent.tools import (  # noqa: E402
    ArchitectConfigTool,
    GatekeeperTool,
    ReviewLogTool,
    TaxWizardTool,
)

BASE_DIR = Path("src/taskforce_extensions/plugins/ap_poc_agent/configs/data")


def test_architect_config_validates_sample_config() -> None:
    tool = ArchitectConfigTool()
    config_path = BASE_DIR / "system_config_saas_skr03.json"

    result = asyncio.run(tool.execute(config_path=str(config_path)))

    assert result["success"] is True
    assert result["summary"]["chart_of_accounts"] == "SKR03"


def test_gatekeeper_extracts_invoice_fields() -> None:
    tool = GatekeeperTool()
    invoice_path = BASE_DIR / "sample_invoice_cloud.json"

    result = asyncio.run(tool.execute(invoice_path=str(invoice_path)))

    assert result["success"] is True
    assert result["invoice_data"]["supplier_name"] == "Cloud Provider GmbH"
    assert result["compliant"] is True


def test_gatekeeper_uses_ocr_text() -> None:
    tool = GatekeeperTool()
    ocr_text = (
        "Rechnungsnummer INV-2025-777 Rechnungsdatum 15.01.2025 "
        "Netto 1000,00 MwSt 19% 190,00 Brutto 1190,00 EUR"
    )

    result = asyncio.run(tool.execute(ocr_text=ocr_text))

    assert result["success"] is True
    assert result["invoice_data"]["invoice_id"] == "INV-2025-777"
    assert result["invoice_data"]["total_amount"] == 1190.0


def test_tax_wizard_assigns_accounts() -> None:
    architect_tool = ArchitectConfigTool()
    gatekeeper_tool = GatekeeperTool()
    tax_tool = TaxWizardTool()

    config_payload = json.loads((BASE_DIR / "system_config_saas_skr03.json").read_text())
    invoice_payload = json.loads((BASE_DIR / "sample_invoice_cloud.json").read_text())

    config_result = asyncio.run(architect_tool.execute(config_payload=config_payload))
    invoice_result = asyncio.run(gatekeeper_tool.execute(invoice_payload=invoice_payload))

    result = asyncio.run(
        tax_tool.execute(
            invoice_data=invoice_result["invoice_data"],
            system_config=config_result["system_config"],
        )
    )

    assert result["success"] is True
    assert result["booking_proposal"]["debit_account"] == "4920"


def test_review_log_generates_prompt() -> None:
    tool = ReviewLogTool()
    proposal = {
        "invoice_id": "INV-2025-001",
        "vendor": "Cloud Provider GmbH",
        "debit_account": "4920",
        "credit_account": "1600",
        "total_amount": 1190.0,
        "currency": "EUR",
    }

    result = asyncio.run(tool.execute(booking_proposal=proposal, payment_terms_days=10))

    assert result["success"] is True
    assert "Bestätigen" in result["approval_prompt"]
