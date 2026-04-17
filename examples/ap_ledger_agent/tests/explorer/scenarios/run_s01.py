"""S01 — Tageslosung bar buchen (Text).

Sendet "186 EUR Tageslosung heute" an einen frischen AT-Kunden und
prüft: 1 Invoice (receipt, posted), 1 Journal (posted), Audit-Log
enthält post-events.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness import db_query, make_fresh_customer, run_scenario, send_message


async def _run() -> dict:
    customer = make_fresh_customer("s01", "Explorer Testlauf", "AT")

    result = await send_message(customer, "186 EUR Tageslosung heute")

    invoices = db_query(
        customer.db_path,
        "SELECT id, type, status, total_gross, total_net, total_tax, "
        "invoice_date, vendor_name_raw FROM invoices ORDER BY id",
    )
    journals = db_query(
        customer.db_path,
        "SELECT id, invoice_id, status, entry_date FROM journal_entries ORDER BY id",
    )
    audit = db_query(
        customer.db_path,
        "SELECT event_type, entity_type, entity_id FROM audit_log ORDER BY id",
    )

    return {
        "agent": {
            "success": result["success"],
            "reply_preview": (result.get("reply") or "")[:400],
            "error": result.get("error"),
        },
        "invoices": invoices,
        "journals": journals,
        "audit": audit,
        "customer_dir": str(customer.customer_dir),
    }


if __name__ == "__main__":
    try:
        out = run_scenario(_run)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"harness_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise
