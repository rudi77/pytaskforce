"""Unified memory tool backed by file-based memory storage.

Supports human-like memory operations including reinforcement (spaced
repetition), association linking, and decay sweeps alongside standard
CRUD.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)


class MemoryTool(BaseTool):
    """Tool for managing unified memory records with human-like properties."""

    tool_name = "memory"
    tool_description = (
        "Create, read, search, update, and delete memory records stored as Markdown. "
        "Supports human-like memory features: emotional tagging, importance scoring, "
        "reinforcement on recall (spaced repetition), and associative linking. "
        "IMPORTANT: Before adding a new record, always search first to avoid duplicates. "
        "If a similar record exists, use 'update' with its record_id instead of 'add'."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "add",
                    "get",
                    "list",
                    "search",
                    "update",
                    "delete",
                    "reinforce",
                    "associate",
                    "decay_sweep",
                ],
                "description": (
                    "Memory action to perform. "
                    "'reinforce' strengthens a memory (spaced repetition). "
                    "'associate' links two memories. "
                    "'decay_sweep' runs a forgetting pass over all memories."
                ),
            },
            "record_id": {
                "type": "string",
                "description": "Memory record id for get/update/delete/reinforce",
            },
            "target_id": {
                "type": "string",
                "description": "Second record id for 'associate' action",
            },
            "scope": {
                "type": "string",
                "enum": [scope.value for scope in MemoryScope],
                "description": "Memory scope",
            },
            "kind": {
                "type": "string",
                "enum": [kind.value for kind in MemoryKind],
                "description": "Memory kind",
            },
            "content": {"type": "string", "description": "Memory content"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "metadata": {"type": "object"},
            "query": {"type": "string", "description": "Search query"},
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (default: 10)",
            },
            "emotional_valence": {
                "type": "string",
                "enum": [v.value for v in EmotionalValence],
                "description": (
                    "Emotional charge of the memory "
                    "(neutral, positive, negative, surprise, frustration)"
                ),
            },
            "importance": {
                "type": "number",
                "description": "Perceived importance 0.0-1.0 (higher = more persistent)",
            },
        },
        "required": ["action"],
    }
    tool_requires_approval = False
    tool_supports_parallelism = False

    def __init__(self, store_dir: str = ".taskforce/memory.md") -> None:
        from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore

        self._store = FileMemoryStore(store_dir)
        logger.info(
            "memory_tool.initialized",
            store_path=str(self._store._file),
            file_exists=self._store._file.exists(),
        )

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Dispatch to the appropriate action handler."""
        action = kwargs.get("action")
        logger.debug(
            "memory_tool.execute",
            action=action,
            store_path=str(self._store._file),
            params={k: v for k, v in kwargs.items() if k != "content"},
        )
        if action == "add":
            return await self._add_record(**kwargs)
        if action == "get":
            return await self._get_record(**kwargs)
        if action == "list":
            return await self._list_records(**kwargs)
        if action == "search":
            return await self._search_records(**kwargs)
        if action == "update":
            return await self._update_record(**kwargs)
        if action == "delete":
            return await self._delete_record(**kwargs)
        if action == "reinforce":
            return await self._reinforce_record(**kwargs)
        if action == "associate":
            return await self._associate_records(**kwargs)
        if action == "decay_sweep":
            return await self._decay_sweep(**kwargs)
        return {"success": False, "error": f"Unknown action: {action}"}

    async def _add_record(self, **kwargs: Any) -> dict[str, Any]:
        record = self._build_record(kwargs)
        saved = await self._store.add(record)
        return {"success": True, "record": self._record_payload(saved)}

    async def _get_record(self, **kwargs: Any) -> dict[str, Any]:
        record_id = self._require_field(kwargs, "record_id")
        record = await self._store.get(record_id)
        if not record:
            return {"success": False, "error": f"Record not found: {record_id}"}
        return {"success": True, "record": self._record_payload(record)}

    async def _list_records(self, **kwargs: Any) -> dict[str, Any]:
        scope = self._parse_scope(kwargs.get("scope"))
        kind = self._parse_kind(kwargs.get("kind"))
        records = await self._store.list(scope=scope, kind=kind)
        return {
            "success": True,
            "records": [self._record_payload(record) for record in records],
        }

    async def _search_records(self, **kwargs: Any) -> dict[str, Any]:
        query = self._require_field(kwargs, "query")
        scope = self._parse_scope(kwargs.get("scope"))
        kind = self._parse_kind(kwargs.get("kind"))
        limit = int(kwargs.get("limit", 10))
        records = await self._store.search(
            query=query, scope=scope, kind=kind, limit=limit
        )
        return {
            "success": True,
            "records": [self._record_payload(record) for record in records],
        }

    async def _update_record(self, **kwargs: Any) -> dict[str, Any]:
        record = self._build_record(kwargs)
        record_id = self._require_field(kwargs, "record_id")
        record.id = record_id
        saved = await self._store.update(record)
        return {"success": True, "record": self._record_payload(saved)}

    async def _delete_record(self, **kwargs: Any) -> dict[str, Any]:
        record_id = self._require_field(kwargs, "record_id")
        deleted = await self._store.delete(record_id)
        if not deleted:
            return {"success": False, "error": f"Record not found: {record_id}"}
        return {"success": True, "deleted": True, "record_id": record_id}

    async def _reinforce_record(self, **kwargs: Any) -> dict[str, Any]:
        """Reinforce a memory — spaced repetition effect."""
        record_id = self._require_field(kwargs, "record_id")
        record = await self._store.get(record_id)
        if not record:
            return {"success": False, "error": f"Record not found: {record_id}"}
        record.reinforce()
        saved = await self._store.update(record)
        return {
            "success": True,
            "record": self._record_payload(saved),
            "message": "Memory reinforced (spaced repetition)",
        }

    async def _associate_records(self, **kwargs: Any) -> dict[str, Any]:
        """Create a bidirectional association between two memories."""
        id_a = self._require_field(kwargs, "record_id")
        id_b = self._require_field(kwargs, "target_id")
        rec_a = await self._store.get(id_a)
        rec_b = await self._store.get(id_b)
        if not rec_a:
            return {"success": False, "error": f"Record not found: {id_a}"}
        if not rec_b:
            return {"success": False, "error": f"Record not found: {id_b}"}
        rec_a.associate_with(id_b)
        rec_b.associate_with(id_a)
        await self._store.update(rec_a)
        await self._store.update(rec_b)
        return {
            "success": True,
            "message": f"Associated {id_a[:8]} <-> {id_b[:8]}",
            "record_a": self._record_payload(rec_a),
            "record_b": self._record_payload(rec_b),
        }

    async def _decay_sweep(self, **kwargs: Any) -> dict[str, Any]:
        """Run a forgetting sweep — archive weak memories."""
        from taskforce.core.domain.memory_service import MemoryService

        service = MemoryService(self._store)
        decayed, forgotten = await service.decay_sweep()
        return {
            "success": True,
            "decayed": decayed,
            "archived": forgotten,
            "message": f"Decay sweep: {decayed} weakened, {forgotten} archived",
        }

    def _build_record(self, kwargs: dict[str, Any]) -> MemoryRecord:
        scope_value = self._require_field(kwargs, "scope")
        kind_value = self._require_field(kwargs, "kind")
        content = self._require_field(kwargs, "content")
        tags = kwargs.get("tags", [])
        metadata = kwargs.get("metadata", {})
        record_id = kwargs.get("record_id")
        valence_raw = kwargs.get("emotional_valence")
        importance_raw = kwargs.get("importance")

        record_payload: dict[str, Any] = {
            "scope": MemoryScope(scope_value),
            "kind": MemoryKind(kind_value),
            "content": content,
            "tags": list(tags),
            "metadata": dict(metadata),
        }
        if record_id:
            record_payload["id"] = str(record_id)
        if valence_raw:
            record_payload["emotional_valence"] = EmotionalValence(valence_raw)
        if importance_raw is not None:
            record_payload["importance"] = min(1.0, max(0.0, float(importance_raw)))
        return MemoryRecord(**record_payload)

    def _record_payload(self, record: MemoryRecord) -> dict[str, Any]:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "id": record.id,
            "scope": record.scope.value,
            "kind": record.kind.value,
            "content": record.content,
            "tags": record.tags,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            # Human-like properties
            "strength": round(record.strength, 4),
            "effective_strength": round(record.effective_strength(now), 4),
            "access_count": record.access_count,
            "emotional_valence": record.emotional_valence.value,
            "importance": round(record.importance, 4),
            "associations": record.associations,
        }
        if record.last_accessed:
            payload["last_accessed"] = record.last_accessed.isoformat()
        return payload

    def _parse_scope(self, value: str | None) -> MemoryScope | None:
        return MemoryScope(value) if value else None

    def _parse_kind(self, value: str | None) -> MemoryKind | None:
        return MemoryKind(value) if value else None

    def _require_field(self, kwargs: dict[str, Any], field: str) -> str:
        value = kwargs.get(field)
        if not value:
            raise ValueError(f"Missing required parameter: {field}")
        return str(value)
