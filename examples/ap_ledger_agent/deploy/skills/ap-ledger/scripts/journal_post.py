"""Finalize a journal entry (draft -> posted).

Usage:
  python journal_post.py --journal-id 1
"""

import argparse
from _db import error, get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a journal entry")
    parser.add_argument("--journal-id", required=True, type=int, help="Journal entry ID")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)

    try:
        result = store.post_journal(args.journal_id)
        output({
            "success": True,
            "journal_id": args.journal_id,
            "status": "posted",
            "posted_at": result.get("posted_at"),
            "vendor": result.get("vendor_name_raw"),
            "total_gross": result.get("total_gross"),
        })
    except ValueError as e:
        error(str(e))


if __name__ == "__main__":
    main()
