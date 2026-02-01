"""Simple JSON-backed storage for personal assistant tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_STORE_PATH = Path(".taskforce_personal_assistant/store.json")


def ensure_store_path(path: Path) -> Path:
    """Ensure the parent directory exists and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_store(path: Path | None = None) -> dict[str, Any]:
    """Load the JSON store, creating a default structure when missing."""
    store_path = ensure_store_path(path or DEFAULT_STORE_PATH)
    if not store_path.exists():
        return {"emails": [], "events": [], "tasks": []}
    return json.loads(store_path.read_text(encoding="utf-8"))


def save_store(store: dict[str, Any], path: Path | None = None) -> None:
    """Persist the JSON store to disk."""
    store_path = ensure_store_path(path or DEFAULT_STORE_PATH)
    payload = json.dumps(store, indent=2, ensure_ascii=False)
    store_path.write_text(payload, encoding="utf-8")


def new_id(prefix: str) -> str:
    """Generate a prefixed unique identifier."""
    return f"{prefix}_{uuid4().hex}"
