"""S04 — Drei Buchungen nacheinander (Streaming-Regression).

Sendet 3 Nachrichten an denselben Kunden (selbe session_id) sequenziell
und prüft, dass alle 3 Buchungen landen, keine Duplikat-Fehler, und
Audit-Log vollständig ist.

Sequenz:
  1) 186 EUR Tageslosung heute
  2) 240 EUR Tageslosung heute
  3) Wella Haarfarbe 119 EUR, Datum 14.04.2026
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness import db_query, make_fresh_customer, run_scenario, send_message


async def _run() -> dict:
    customer = make_fresh_customer("s04", "Explorer Testlauf", "AT")
    session_id = "s04-shared-session"

    messages = [
        "186 EUR Tageslosung heute",
        "240 EUR Tageslosung heute",
        "Wella Haarfarbe 119 EUR, Datum 14.04.2026",
    ]
    step_results = []
    for idx, msg in enumerate(messages, start=1):
        r = await send_message(customer, msg, session_id=session_id)
        step_results.append({
            "step": idx,
            "message": msg,
            "success": r["success"],
            "tool_calls_count": len(r.get("tool_calls", [])),
            "reply_preview": (r.get("reply") or "")[:120],
            "error": r.get("error"),
        })

    invoices = db_query(
        customer.db_path,
        "SELECT id, type, status, total_gross, total_net, total_tax, "
        "invoice_date, vendor_name_raw FROM invoices ORDER BY id",
    )
    journals = db_query(
        customer.db_path,
        "SELECT id, invoice_id, status FROM journal_entries ORDER BY id",
    )
    audit = db_query(
        customer.db_path,
        "SELECT event_type, entity_type, entity_id FROM audit_log "
        "WHERE event_type != 'system_init' ORDER BY id",
    )

    return {
        "steps": step_results,
        "invoice_count": len(invoices),
        "invoices": invoices,
        "journal_count": len(journals),
        "journals": journals,
        "audit_post_init": audit,
        "customer_dir": str(customer.customer_dir),
    }


if __name__ == "__main__":
    try:
        out = run_scenario(_run)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"harness_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise
