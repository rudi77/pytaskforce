"""Shared database helper for AP Ledger CLI scripts."""

import json
import os
import sys
from pathlib import Path

# Add the plugin package to sys.path so scripts can import SQLiteStore
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore  # noqa: E402

DB_PATH = _PLUGIN_DIR / "db" / "ap-ledger.db"
_CONFIG_PATH = _PLUGIN_DIR / "configs" / "ap_ledger_agent.yaml"


def _detect_country() -> str:
    """Read country from config YAML or environment variable."""
    env = os.environ.get("AP_LEDGER_COUNTRY")
    if env:
        return env.upper()
    try:
        import yaml
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return (config.get("country") or "AT").upper()
    except Exception:
        return "AT"


COUNTRY = _detect_country()


def get_store(db_path: str | None = None, country: str | None = None) -> SQLiteStore:
    """Return an initialized SQLiteStore.

    If the DB does not exist yet, it is created with the seed data
    for the configured country (AT or DE).
    """
    path = db_path or str(DB_PATH)
    c = country or COUNTRY
    store = SQLiteStore(path, country=c)
    store.ensure_initialized()
    return store


def output(data: dict) -> None:
    """Print JSON result to stdout."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(data, ensure_ascii=False, default=str))


def error(msg: str) -> None:
    """Print JSON error to stdout and exit."""
    output({"success": False, "error": msg})
    sys.exit(1)
