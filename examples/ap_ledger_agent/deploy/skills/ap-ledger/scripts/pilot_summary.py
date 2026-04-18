"""Print a daily / weekly usage summary for a BluBot pilot customer.

Reads three data sources in the customer's isolated workspace and
produces a single-screen report so you can see at a glance how the
customer is using the bot:

  - SQLite (db/ap-ledger.db)          → bookings + audit log + categories
  - Conversation history (.taskforce_ap_ledger/conversations/telegram/*)
                                       → message counts (user / assistant /
                                         tool calls)
  - Filesystem (reports/, exports/)   → reports / ZIPs delivered

Designed to be run by Rudi himself (the "Concierge"). No external deps
beyond the Python stdlib.

Usage:
  python pilot_summary.py --customer tina
  python pilot_summary.py --customer tina --days 14
  python pilot_summary.py --root C:\\blubot\\customers\\tina
  python pilot_summary.py --root /srv/blubot/customers/tina --markdown > tina.md
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Force UTF-8 stdout on Windows so the report can contain Umlauts and
# common emojis without crashing cp1252 consoles.
if sys.platform == "win32" and isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------------- #
# Customer-dir resolution
# ---------------------------------------------------------------------- #

def _default_blubot_root() -> Path:
    env = os.environ.get("BLUBOT_ROOT")
    if env:
        return Path(env)
    return Path(r"C:\blubot") if sys.platform == "win32" else Path("/srv/blubot")


def resolve_customer_dir(customer: str | None, root: Path | None) -> Path:
    if root:
        return Path(root)
    if not customer:
        raise SystemExit(
            "[pilot_summary] Need either --customer <slug> or --root <path>."
        )
    return _default_blubot_root() / "customers" / customer


# ---------------------------------------------------------------------- #
# Data sources
# ---------------------------------------------------------------------- #

def query_invoices(db_path: Path, since_iso: str) -> list[dict]:
    """All posted invoices since ``since_iso`` (ISO date string)."""
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT i.id, i.type, i.status, i.invoice_date, i.total_gross, "
            "  i.total_net, i.total_tax, i.vendor_name_raw, i.created_at, "
            "  il.category_code "
            "FROM invoices i "
            "LEFT JOIN invoice_lines il ON il.invoice_id = i.id AND il.position = 1 "
            "WHERE i.created_at >= ? "
            "ORDER BY i.invoice_date, i.id",
            (since_iso,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_audit(db_path: Path, since_iso: str) -> list[dict]:
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT event_type, entity_type, entity_id, actor, created_at "
            "FROM audit_log WHERE created_at >= ? ORDER BY id",
            (since_iso,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def collect_conversations(work_dir: Path) -> list[dict]:
    """Return all telegram conversation history entries (flattened)."""
    convo_dir = work_dir / "conversations" / "telegram"
    if not convo_dir.is_dir():
        return []
    flat: list[dict] = []
    for f in sorted(convo_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for m in data.get("history", []) or []:
            flat.append(m)
    return flat


def collect_artifacts(customer_dir: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {"pdfs": [], "zips": []}
    reports = customer_dir / "reports"
    if reports.is_dir():
        out["pdfs"] = sorted(reports.rglob("*.pdf"))
    exports = customer_dir / "exports"
    if exports.is_dir():
        out["zips"] = sorted(exports.rglob("*.zip"))
    return out


# ---------------------------------------------------------------------- #
# Analysis
# ---------------------------------------------------------------------- #

WEEKDAY_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def daily_distribution(invoices: list[dict], days: int) -> list[tuple[str, int]]:
    """Return (label, count) for each of the last ``days`` days incl. today.

    Uses ``created_at`` (when the customer booked) rather than
    ``invoice_date`` (when the underlying receipt was issued) — for a
    pilot summary we want to see customer engagement, not the timeline
    of the original receipts (which a customer might back-date weeks).
    """
    counts: dict[str, int] = defaultdict(int)
    today = datetime.now().date()
    day_labels: list[str] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        weekday_idx = d.weekday()
        label = f"{WEEKDAY_DE[weekday_idx]} {d.day:02d}.{d.month:02d}"
        day_labels.append(label)

    for inv in invoices:
        ts = inv.get("created_at") or ""
        try:
            d = datetime.fromisoformat(ts.split(".")[0]).date()  # tolerate microseconds
        except ValueError:
            continue
        weekday_idx = d.weekday()
        label = f"{WEEKDAY_DE[weekday_idx]} {d.day:02d}.{d.month:02d}"
        counts[label] += 1

    return [(label, counts[label]) for label in day_labels]


def message_breakdown(messages: list[dict]) -> dict[str, int]:
    out = Counter({"user": 0, "assistant": 0, "tool": 0, "tool_calls": 0, "system": 0})
    for m in messages:
        role = m.get("role", "unknown")
        if role in out:
            out[role] += 1
        else:
            out["system"] += 1
        # tool_calls is a list when assistant invokes tools
        tcs = m.get("tool_calls")
        if isinstance(tcs, list):
            out["tool_calls"] += len(tcs)
    return dict(out)


def find_anomalies(invoices: list[dict], audit: list[dict]) -> list[str]:
    notes: list[str] = []
    rejected = [i for i in invoices if i.get("status") not in ("posted", None)]
    if rejected:
        notes.append(f"❌ {len(rejected)} Beleg(e) nicht im Status 'posted' (status: "
                     + ", ".join(sorted({i.get('status', '?') for i in rejected})) + ")")
    correction_events = [a for a in audit if "correct" in (a.get("event_type") or "")]
    if correction_events:
        notes.append(f"⚠ {len(correction_events)} Korrektur-Event(s) im Audit-Log")
    reversal_events = [a for a in audit if "revers" in (a.get("event_type") or "")]
    if reversal_events:
        notes.append(f"⚠ {len(reversal_events)} Stornierung(en) im Audit-Log")
    return notes


# ---------------------------------------------------------------------- #
# Rendering
# ---------------------------------------------------------------------- #

def render(
    customer_label: str,
    period_label: str,
    customer_dir: Path,
    invoices: list[dict],
    audit: list[dict],
    messages: list[dict],
    artifacts: dict[str, list[Path]],
    days_dist: list[tuple[str, int]],
    msg_breakdown: dict[str, int],
    anomalies: list[str],
    *,
    markdown: bool = False,
) -> str:
    lines: list[str] = []
    sep = "═" * 60 if not markdown else "---"

    if markdown:
        lines.append(f"# BluBot Pilot-Summary — {customer_label}")
        lines.append(f"_{period_label}_  ·  `{customer_dir}`")
        lines.append("")
    else:
        lines.append(f"BluBot Pilot-Summary — {customer_label}  ({period_label})")
        lines.append(sep)
        lines.append(f"Customer dir: {customer_dir}")
        lines.append("")

    # ── Bookings ────────────────────────────────────────────────────
    revenues = [i for i in invoices if i.get("type") == "receipt"]
    expenses = [i for i in invoices if i.get("type") == "invoice"]
    rev_sum = sum((i.get("total_gross") or 0) for i in revenues)
    exp_sum = sum((i.get("total_gross") or 0) for i in expenses)

    if markdown:
        lines.append("## Buchungen")
    else:
        lines.append("Buchungen")
    lines.append(f"  Gesamt: {len(invoices)} ({len(revenues)} Einnahmen "
                 f"{rev_sum:,.2f} €, {len(expenses)} Ausgaben {exp_sum:,.2f} €)")
    if days_dist:
        chart = "  ".join(f"{label.split()[0]}:{n}" for label, n in days_dist)
        lines.append(f"  Pro Tag:  {chart}")
    cat_counter = Counter(
        (i.get("category_code") or "(none)") for i in invoices
    ).most_common(5)
    if cat_counter:
        lines.append("  Kategorien (Top 5): "
                     + ", ".join(f"{c}({n})" for c, n in cat_counter))
    lines.append("")

    # ── Messages ────────────────────────────────────────────────────
    if markdown:
        lines.append("## Nachrichten")
    else:
        lines.append("Nachrichten")
    lines.append(f"  Von Userin (user):    {msg_breakdown.get('user', 0)}")
    lines.append(f"  Von Bot (assistant):  {msg_breakdown.get('assistant', 0)}")
    lines.append(f"  Tool-Ausführungen:    {msg_breakdown.get('tool', 0)} "
                 f"(durch {msg_breakdown.get('tool_calls', 0)} tool_call-Aufrufe)")
    lines.append("")

    # ── Reports / Exports ───────────────────────────────────────────
    if markdown:
        lines.append("## Generierte Reports & Exports")
    else:
        lines.append("Generierte Reports & Exports")
    if artifacts["pdfs"]:
        lines.append(f"  PDFs ({len(artifacts['pdfs'])}):")
        for p in artifacts["pdfs"][-5:]:
            size_kb = p.stat().st_size // 1024
            lines.append(f"    {p.name}  ({size_kb} KB)")
    else:
        lines.append("  PDFs: keine")
    if artifacts["zips"]:
        lines.append(f"  Belege-ZIPs ({len(artifacts['zips'])}):")
        for z in artifacts["zips"][-3:]:
            size_kb = z.stat().st_size // 1024
            lines.append(f"    {z.name}  ({size_kb} KB)")
    else:
        lines.append("  Belege-ZIPs: keine")
    lines.append("")

    # ── Anomalies ───────────────────────────────────────────────────
    if markdown:
        lines.append("## Auffälligkeiten")
    else:
        lines.append("Auffälligkeiten")
    if anomalies:
        for note in anomalies:
            lines.append(f"  {note}")
    else:
        lines.append("  Keine — alles im grünen Bereich.")

    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# Entrypoint
# ---------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description="Pilot-Customer usage summary")
    parser.add_argument("--customer", help="Customer slug under $BLUBOT_ROOT/customers/")
    parser.add_argument("--root", type=Path, help="Direct path to customer dir (overrides --customer)")
    parser.add_argument("--days", type=int, default=7, help="Window size in days (default 7)")
    parser.add_argument("--markdown", action="store_true",
                        help="Output Markdown instead of plain text")
    args = parser.parse_args()

    customer_dir = resolve_customer_dir(args.customer, args.root)
    if not customer_dir.is_dir():
        raise SystemExit(f"[pilot_summary] Customer dir not found: {customer_dir}")

    db_path = customer_dir / "db" / "ap-ledger.db"
    work_dir = customer_dir / ".taskforce_ap_ledger"

    since = datetime.now() - timedelta(days=args.days)
    since_iso = since.strftime("%Y-%m-%d 00:00:00")

    invoices = query_invoices(db_path, since_iso)
    audit = query_audit(db_path, since_iso)
    messages = collect_conversations(work_dir)
    artifacts = collect_artifacts(customer_dir)
    days_dist = daily_distribution(invoices, args.days)
    msg_breakdown = message_breakdown(messages)
    anomalies = find_anomalies(invoices, audit)

    period_label = (
        f"{since.strftime('%Y-%m-%d')} → {datetime.now().strftime('%Y-%m-%d')} "
        f"({args.days} Tage)"
    )
    customer_label = (
        args.customer
        or os.environ.get("AP_LEDGER_CUSTOMER_NAME")
        or customer_dir.name
    )

    print(render(
        customer_label=customer_label,
        period_label=period_label,
        customer_dir=customer_dir,
        invoices=invoices,
        audit=audit,
        messages=messages,
        artifacts=artifacts,
        days_dist=days_dist,
        msg_breakdown=msg_breakdown,
        anomalies=anomalies,
        markdown=args.markdown,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
