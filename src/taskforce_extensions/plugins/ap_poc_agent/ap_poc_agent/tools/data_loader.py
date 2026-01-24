"""Shared data loading helpers for the Accounts Payable PoC plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_file(path: str) -> dict[str, Any]:
    """Load a JSON file from disk.

    Args:
        path: File path to load.

    Returns:
        Parsed JSON data.

    Raises:
        FileNotFoundError: When file does not exist.
        json.JSONDecodeError: When JSON is invalid.
    """
    file_path = Path(path)
    with file_path.open(encoding="utf-8") as handle:
        return json.load(handle)
