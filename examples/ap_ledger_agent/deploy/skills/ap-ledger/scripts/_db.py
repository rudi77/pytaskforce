"""Shared database helper for AP Ledger CLI scripts.

Path resolution order:
  1. AP_LEDGER_ROOT env var (deployment root directory)
  2. Relative to skill directory (scripts/../..)

Country detection:
  1. AP_LEDGER_COUNTRY env var
  2. Defaults to "AT"
"""

import json
import os
import sys
from pathlib import Path

# Ensure local imports work (models.py, sqlite_store.py in same directory)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sqlite_store import SQLiteStore  # noqa: E402

# Resolve root directory:
#   1. AP_LEDGER_ROOT env var (explicit)
#   2. deploy/ directory (3 levels up from scripts/ — deployment mode)
#   3. examples/ap_ledger_agent/ (4 levels up — dev mode in repo)
def _resolve_root() -> Path:
    env = os.environ.get("AP_LEDGER_ROOT")
    if env:
        return Path(env)
    # Deployment mode: scripts/ -> ap-ledger/ -> skills/ -> deploy/
    deploy_root = _SCRIPTS_DIR.parent.parent.parent
    if (deploy_root / "db" / "ap-ledger.db").exists():
        return deploy_root
    # Dev mode: deploy/ -> ap_ledger_agent/  (one more level up)
    dev_root = deploy_root.parent
    if (dev_root / "db" / "ap-ledger.db").exists():
        return dev_root
    # Fallback: deploy root (DB will be created on first run)
    return deploy_root


_ROOT = _resolve_root()
DB_PATH = Path(os.environ.get("AP_LEDGER_DB_PATH", str(_ROOT / "db" / "ap-ledger.db")))


def _detect_country() -> str:
    """Read country from environment variable."""
    return os.environ.get("AP_LEDGER_COUNTRY", "AT").upper()


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


def get_belege_dir() -> Path:
    """Return the belege archive directory, creating it if needed."""
    belege = Path(os.environ.get("AP_LEDGER_BELEGE_DIR", str(_ROOT / "belege")))
    belege.mkdir(parents=True, exist_ok=True)
    return belege


def output(data: dict) -> None:
    """Print JSON result to stdout."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(data, ensure_ascii=False, default=str))


def error(msg: str) -> None:
    """Print JSON error to stdout and exit."""
    output({"success": False, "error": msg})
    sys.exit(1)
