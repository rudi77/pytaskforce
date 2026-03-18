"""
File-Based Agent State Manager

Implements ``AgentStateProtocol`` for the persistent agent (ADR-016).
Stores a single global agent state in a JSON file — no session_id keying.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.interfaces.agent_state import AgentStateProtocol

logger = structlog.get_logger(__name__)


class FileAgentState:
    """File-based singleton agent state.

    State is stored in ``{work_dir}/agent_state.json``.
    Uses atomic writes (temp file + rename) and an asyncio lock
    for concurrency safety.
    """

    def __init__(
        self,
        work_dir: str = ".taskforce",
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._work_dir / "agent_state.json"
        self._lock = asyncio.Lock()
        self._time_provider = time_provider or datetime.now

    async def save(self, state_data: dict[str, Any]) -> None:
        """Persist the agent's global state atomically."""
        async with self._lock:
            state_copy = dict(state_data)
            state_copy["_version"] = int(state_copy.get("_version", 0)) + 1
            state_copy["_updated_at"] = self._time_provider().isoformat()

            payload = json.dumps(state_copy, indent=2, ensure_ascii=False)
            temp_file = self._state_file.with_suffix(".json.tmp")

            try:
                async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                    await f.write(payload)
                if self._state_file.exists():
                    self._state_file.unlink()
                temp_file.rename(self._state_file)
                logger.info("agent_state.saved", version=state_copy["_version"])
            except OSError as exc:
                logger.error("agent_state.save_failed", error=str(exc))
                raise

    async def load(self) -> dict[str, Any] | None:
        """Load the agent's global state."""
        if not self._state_file.exists():
            return None

        try:
            async with aiofiles.open(self._state_file, encoding="utf-8") as f:
                content = await f.read()
            state = json.loads(content)
            logger.info("agent_state.loaded", version=state.get("_version", 0))
            return state
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("agent_state.load_failed", error=str(exc))
            return None
