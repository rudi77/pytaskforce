"""Tool to persist an invoice with its line items to the AP Ledger database."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ap_ledger_agent.domain.models import Invoice, InvoiceLine, InvoiceStatus, InvoiceType
from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class InvoicePersistTool:
    """Save an invoice and its positions to the database."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_invoice_persist"

    @property
    def description(self) -> str:
        return (
            "Persist a validated invoice with its line items to the AP Ledger database. "
            "Returns the invoice_id for use in subsequent journal creation. "
            "Also checks for duplicate invoices before saving."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "vendor_name_raw": {"type": "string", "description": "Original vendor name from extraction"},
                "vendor_id": {"type": "integer", "description": "Resolved vendor ID (from ap_vendor_resolve)"},
                "invoice_date": {"type": "string", "description": "Invoice date (YYYY-MM-DD)"},
                "total_gross": {"type": "number", "description": "Total gross amount in EUR"},
                "total_net": {"type": "number", "description": "Total net amount in EUR"},
                "total_tax": {"type": "number", "description": "Total tax amount in EUR"},
                "external_ref": {"type": "string", "description": "External invoice/receipt number"},
                "due_date": {"type": "string", "description": "Due date (YYYY-MM-DD)"},
                "type": {"type": "string", "enum": ["invoice", "receipt", "credit_note"], "default": "invoice"},
                "source_file": {"type": "string", "description": "Path to original file"},
                "source_type": {"type": "string", "enum": ["photo", "pdf", "manual"]},
                "extraction_confidence": {"type": "number", "description": "Extraction confidence 0.0-1.0"},
                "fiscal_period_id": {"type": "integer", "description": "Fiscal period ID (from ap_period_resolve)"},
                "notes": {"type": "string"},
                "lines": {
                    "type": "array",
                    "description": "Invoice line items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "integer"},
                            "description": {"type": "string"},
                            "quantity": {"type": "number", "default": 1},
                            "unit_price": {"type": "number"},
                            "net_amount": {"type": "number"},
                            "tax_code": {"type": "string"},
                            "tax_amount": {"type": "number"},
                            "gross_amount": {"type": "number"},
                            "category_code": {"type": "string"},
                        },
                        "required": ["description", "gross_amount"],
                    },
                },
            },
            "required": ["vendor_name_raw", "invoice_date", "total_gross"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> str:
        return "medium"

    @property
    def supports_parallelism(self) -> bool:
        return False

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if not kwargs.get("vendor_name_raw"):
            return False, "vendor_name_raw is required"
        if not kwargs.get("invoice_date"):
            return False, "invoice_date is required"
        if not kwargs.get("total_gross"):
            return False, "total_gross is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()

        try:
            # Duplicate check
            dupes = store.find_duplicate(
                kwargs["vendor_name_raw"],
                kwargs["invoice_date"],
                Decimal(str(kwargs["total_gross"])),
            )
            if dupes:
                return {
                    "success": False,
                    "error": "possible_duplicate",
                    "duplicates": dupes,
                    "message": f"Mögliches Duplikat: {len(dupes)} ähnliche Belege gefunden.",
                }

            lines = []
            for i, line_data in enumerate(kwargs.get("lines", []), start=1):
                lines.append(
                    InvoiceLine(
                        position=line_data.get("position", i),
                        description=line_data.get("description", ""),
                        quantity=Decimal(str(line_data.get("quantity", 1))),
                        unit_price=Decimal(str(line_data["unit_price"])) if line_data.get("unit_price") else None,
                        net_amount=Decimal(str(line_data.get("net_amount", 0))),
                        tax_code=line_data.get("tax_code"),
                        tax_amount=Decimal(str(line_data["tax_amount"])) if line_data.get("tax_amount") else None,
                        gross_amount=Decimal(str(line_data.get("gross_amount", 0))),
                        category_code=line_data.get("category_code"),
                    )
                )

            invoice = Invoice(
                external_ref=kwargs.get("external_ref"),
                vendor_id=kwargs.get("vendor_id"),
                vendor_name_raw=kwargs["vendor_name_raw"],
                invoice_date=kwargs["invoice_date"],
                due_date=kwargs.get("due_date"),
                total_gross=Decimal(str(kwargs["total_gross"])),
                total_net=Decimal(str(kwargs["total_net"])) if kwargs.get("total_net") else None,
                total_tax=Decimal(str(kwargs["total_tax"])) if kwargs.get("total_tax") else None,
                type=InvoiceType(kwargs.get("type", "invoice")),
                status=InvoiceStatus.VALIDATED,
                source_file=kwargs.get("source_file"),
                source_type=kwargs.get("source_type"),
                extraction_confidence=kwargs.get("extraction_confidence"),
                fiscal_period_id=kwargs.get("fiscal_period_id"),
                notes=kwargs.get("notes"),
                lines=lines,
            )

            invoice_id = store.persist_invoice(invoice)
            return {
                "success": True,
                "invoice_id": invoice_id,
                "vendor_name": kwargs["vendor_name_raw"],
                "total_gross": float(kwargs["total_gross"]),
                "line_count": len(lines),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return (
            f"Save invoice: {kwargs.get('vendor_name_raw', '?')} "
            f"({kwargs.get('total_gross', '?')} EUR)"
        )
