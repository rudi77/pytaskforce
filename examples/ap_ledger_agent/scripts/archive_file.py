"""Archive a receipt/invoice file to permanent storage.

Copies the file to the archive directory with a structured name:
  belege/YYYY/MM/YYYY-MM-DD_<vendor>_<amount>.<ext>

Usage:
  python archive_file.py --source "C:/tmp/receipt.pdf" --date 2026-01-24 --vendor "Wella" --amount 119.00
  python archive_file.py --source "C:/tmp/photo.jpg" --date 2026-01-24 --vendor "Tageslosung" --amount 186.00

Returns JSON with the archived file path.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = _PLUGIN_DIR / "belege"


def _sanitize(name: str) -> str:
    """Remove special characters for safe filenames."""
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^\w\-.]", "", name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive a receipt file")
    parser.add_argument("--source", required=True, help="Path to the source file")
    parser.add_argument("--date", required=True, help="Invoice date YYYY-MM-DD")
    parser.add_argument("--vendor", default="Beleg", help="Vendor name")
    parser.add_argument("--amount", type=float, default=0, help="Gross amount")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        json.dump({"success": False, "error": f"File not found: {args.source}"}, sys.stdout)
        sys.exit(1)

    # Build archive path: belege/2026/01/2026-01-24_Wella_119.00.pdf
    year = args.date[:4]
    month = args.date[5:7]
    ext = source.suffix.lower() or ".bin"
    vendor_safe = _sanitize(args.vendor)
    amount_str = f"{args.amount:.2f}" if args.amount else ""
    filename = f"{args.date}_{vendor_safe}"
    if amount_str:
        filename += f"_{amount_str}"
    filename += ext

    dest_dir = ARCHIVE_DIR / year / month
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    # Avoid overwriting: append counter if exists
    counter = 1
    while dest.exists():
        stem = f"{args.date}_{vendor_safe}"
        if amount_str:
            stem += f"_{amount_str}"
        dest = dest_dir / f"{stem}_{counter}{ext}"
        counter += 1

    shutil.copy2(str(source), str(dest))

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    json.dump({
        "success": True,
        "archived_path": str(dest),
        "relative_path": str(dest.relative_to(_PLUGIN_DIR)),
        "original": str(source),
        "size_bytes": dest.stat().st_size,
    }, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
