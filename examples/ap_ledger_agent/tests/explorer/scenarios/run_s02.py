"""S02 — Barumsatz + Karteneinnahme gemischt.

Sendet "Heute 300 bar, 150 Karte, Tageslosung" an einen frischen
AT-Kunden und prüft: Summe total_gross = 450, Journal-Entries
balanciert (Soll = Haben pro Entry).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness import db_query, make_fresh_customer, run_scenario, send_message


async def _run() -> dict:
    customer = make_fresh_customer("s02", "Explorer Testlauf", "AT")

    result = await send_message(customer, "Heute 300 bar, 150 Karte, Tageslosung")

    invoices = db_query(
        customer.db_path,
        "SELECT id, type, status, total_gross, total_net, total_tax, "
        "invoice_date, vendor_name_raw FROM invoices ORDER BY id",
    )
    invoice_lines = db_query(
        customer.db_path,
        "SELECT invoice_id, position, description, gross_amount, net_amount, tax_amount "
        "FROM invoice_lines ORDER BY invoice_id, position",
    )
    journals = db_query(
        customer.db_path,
        "SELECT id, invoice_id, status, entry_date FROM journal_entries ORDER BY id",
    )
    journal_lines = db_query(
        customer.db_path,
        "SELECT journal_entry_id, line_number, account_code, account_name, "
        "debit_amount, credit_amount FROM journal_lines ORDER BY journal_entry_id, line_number",
    )

    # Balance check per journal entry
    by_entry: dict[int, dict[str, float]] = {}
    for jl in journal_lines:
        eid = jl["journal_entry_id"]
        b = by_entry.setdefault(eid, {"debit": 0.0, "credit": 0.0})
        b["debit"] += jl["debit_amount"] or 0.0
        b["credit"] += jl["credit_amount"] or 0.0
    balance_by_entry = {
        eid: {
            "debit": round(b["debit"], 2),
            "credit": round(b["credit"], 2),
            "balanced": round(b["debit"], 2) == round(b["credit"], 2),
        }
        for eid, b in by_entry.items()
    }

    total_gross_sum = round(sum((r["total_gross"] or 0) for r in invoices), 2)

    return {
        "agent": {
            "success": result["success"],
            "reply_preview": (result.get("reply") or "")[:400],
            "error": result.get("error"),
            "tool_calls": result.get("tool_calls", [])[:10],
        },
        "invoices": invoices,
        "invoice_lines": invoice_lines,
        "journals": journals,
        "journal_lines": journal_lines,
        "total_gross_sum": total_gross_sum,
        "balance_by_entry": balance_by_entry,
        "customer_dir": str(customer.customer_dir),
    }


if __name__ == "__main__":
    try:
        out = run_scenario(_run)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"harness_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise
