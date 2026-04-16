"""Write an immutable audit log entry.

Usage:
  python audit_log.py --event-type invoice_posted --entity-type invoice --entity-id 1
  python audit_log.py --event-type invoice_posted --entity-type invoice --entity-id 1 \
    --actor agent --details-json '{"amount": 186.00}'
"""

import argparse
import json
from _db import get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Write audit log entry")
    parser.add_argument("--event-type", required=True, help="Event type")
    parser.add_argument("--entity-type", required=True,
                        help="Entity type (invoice, journal_entry, vendor)")
    parser.add_argument("--entity-id", required=True, type=int, help="Entity ID")
    parser.add_argument("--actor", default="agent", help="Who performed the action")
    parser.add_argument("--details-json", default="{}", help="Additional details as JSON")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)

    details = args.details_json
    if isinstance(details, str):
        try:
            json.loads(details)
        except json.JSONDecodeError:
            details = json.dumps({"raw": details})

    audit_id = store.write_audit(
        event_type=args.event_type,
        entity_type=args.entity_type,
        entity_id=args.entity_id,
        actor=args.actor,
        details=details,
    )
    output({
        "success": True,
        "audit_id": audit_id,
        "event_type": args.event_type,
    })


if __name__ == "__main__":
    main()
