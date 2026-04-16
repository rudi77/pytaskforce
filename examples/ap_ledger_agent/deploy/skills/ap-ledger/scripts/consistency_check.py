"""Check AP Ledger database for inconsistencies.

Usage:
  python consistency_check.py
  python consistency_check.py --fix-hint
"""

import argparse
from _db import get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Check DB consistency")
    parser.add_argument("--fix-hint", action="store_true", help="Include fix suggestions")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)
    conn = store.get_connection()

    issues = []

    # 1. Orphaned invoices
    rows = conn.execute(
        "SELECT i.id, i.vendor_name_raw, i.invoice_date, i.total_gross, i.status "
        "FROM invoices i "
        "WHERE i.status IN ('validated', 'posted') "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM journal_entries je WHERE je.invoice_id = i.id"
        ")"
    ).fetchall()
    for r in rows:
        issue = {
            "type": "orphaned_invoice",
            "severity": "warning",
            "invoice_id": r["id"],
            "vendor": r["vendor_name_raw"],
            "date": r["invoice_date"],
            "amount": r["total_gross"],
            "status": r["status"],
            "message": f"Invoice #{r['id']} ({r['vendor_name_raw']}, {r['total_gross']}EUR) "
                       f"hat Status '{r['status']}' aber keinen Buchungssatz.",
        }
        if args.fix_hint:
            issue["fix"] = (
                f"journal_persist.py --invoice-id {r['id']} --entry-date {r['invoice_date']} "
                f"--description 'Nachbuchung' --lines-json '[...]'"
            )
        issues.append(issue)

    # 2. Unposted journals linked to posted invoices
    rows = conn.execute(
        "SELECT je.id as journal_id, je.invoice_id, je.status as journal_status, "
        "i.status as invoice_status, i.vendor_name_raw, i.total_gross "
        "FROM journal_entries je "
        "JOIN invoices i ON i.id = je.invoice_id "
        "WHERE je.status = 'draft' AND i.status = 'posted'"
    ).fetchall()
    for r in rows:
        issue = {
            "type": "unposted_journal",
            "severity": "warning",
            "journal_id": r["journal_id"],
            "invoice_id": r["invoice_id"],
            "vendor": r["vendor_name_raw"],
            "message": f"Journal #{r['journal_id']} ist 'draft' aber Invoice #{r['invoice_id']} "
                       f"ist 'posted' ({r['vendor_name_raw']}, {r['total_gross']}EUR).",
        }
        if args.fix_hint:
            issue["fix"] = f"journal_post.py --journal-id {r['journal_id']}"
        issues.append(issue)

    # 3. Unbalanced posted journals
    rows = conn.execute(
        "SELECT je.id, je.description, "
        "ROUND(SUM(jl.debit_amount), 2) as total_debit, "
        "ROUND(SUM(jl.credit_amount), 2) as total_credit "
        "FROM journal_entries je "
        "JOIN journal_lines jl ON jl.journal_entry_id = je.id "
        "WHERE je.status = 'posted' "
        "GROUP BY je.id "
        "HAVING ABS(total_debit - total_credit) > 0.01"
    ).fetchall()
    for r in rows:
        issues.append({
            "type": "unbalanced_journal",
            "severity": "error",
            "journal_id": r["id"],
            "description": r["description"],
            "total_debit": r["total_debit"],
            "total_credit": r["total_credit"],
            "difference": round(r["total_debit"] - r["total_credit"], 2),
            "message": f"Journal #{r['id']} ({r['description']}) ist unausgeglichen: "
                       f"Soll={r['total_debit']}, Haben={r['total_credit']}.",
        })

    # 4. Failed bookings in audit log
    rows = conn.execute(
        "SELECT id, details, created_at "
        "FROM audit_log "
        "WHERE event_type = 'booking_failed' "
        "ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        issues.append({
            "type": "recent_failure",
            "severity": "info",
            "audit_id": r["id"],
            "details": r["details"],
            "timestamp": r["created_at"],
            "message": f"Fehlgeschlagene Buchung am {r['created_at']}.",
        })

    conn.close()

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos = [i for i in issues if i["severity"] == "info"]

    output({
        "success": True,
        "clean": len(errors) == 0 and len(warnings) == 0,
        "summary": f"{len(errors)} Fehler, {len(warnings)} Warnungen, {len(infos)} Hinweise",
        "issues": issues,
    })


if __name__ == "__main__":
    main()
