"""S05 — Leerer Monatsreport.

Frischer Kunde ohne Buchungen, Anfrage "Schick mir Monatsreport April
2026". Erwartet: Agent antwortet "keine Buchungen" und sendet KEIN PDF.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness import make_fresh_customer, run_scenario, send_message


async def _run() -> dict:
    customer = make_fresh_customer("s05", "Explorer Testlauf", "AT")

    result = await send_message(
        customer,
        "Schick mir den Monatsreport April 2026",
    )

    # Inspect reports/ directory — expect NO PDF was generated/sent
    reports_dir = customer.reports_dir
    pdfs = (
        sorted(p.name for p in reports_dir.rglob("*.pdf"))
        if reports_dir.exists()
        else []
    )

    tool_calls = result.get("tool_calls", [])
    called_send_notification = any(
        "send_notification" in (tc or "") for tc in tool_calls
    )

    reply_lower = (result.get("reply") or "").lower()
    keine_buchungen_mentioned = any(
        phrase in reply_lower
        for phrase in ("keine buchung", "keine beleg", "nichts gebucht", "no data")
    )

    return {
        "agent": {
            "success": result["success"],
            "reply": result.get("reply"),
            "error": result.get("error"),
            "tool_calls": tool_calls,
        },
        "pdfs_in_reports_dir": pdfs,
        "called_send_notification": called_send_notification,
        "keine_buchungen_mentioned": keine_buchungen_mentioned,
        "customer_dir": str(customer.customer_dir),
    }


if __name__ == "__main__":
    try:
        out = run_scenario(_run)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"harness_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise
