"""Unified memory tool backed by file-based memory storage."""

from __future__ import annotations

from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore


class MemoryTool(ToolProtocol):
    """Tool for managing unified memory records."""

    def __init__(self, store_dir: str = ".taskforce/memory") -> None:
        self._store = FileMemoryStore(store_dir)

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Create, read, search, update, and delete memory records stored as Markdown."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "get", "list", "search", "update", "delete"],
                    "description": "Memory action to perform",
                },
                "record_id": {
                    "type": "string",
                    "description": "Memory record id for get/update/delete",
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
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        return f"Tool: {self.name}\nOperation: {action}"

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action")
        try:
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
            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            tool_error = ToolError(
                f"{self.name} failed: {exc}",
                tool_name=self.name,
                details={"action": action},
            )
            return tool_error_payload(tool_error)

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

    def _build_record(self, kwargs: dict[str, Any]) -> MemoryRecord:
        scope_value = self._require_field(kwargs, "scope")
        kind_value = self._require_field(kwargs, "kind")
        content = self._require_field(kwargs, "content")
        tags = kwargs.get("tags", [])
        metadata = kwargs.get("metadata", {})
        record_id = kwargs.get("record_id")
        record_payload: dict[str, Any] = {
            "scope": MemoryScope(scope_value),
            "kind": MemoryKind(kind_value),
            "content": content,
            "tags": list(tags),
            "metadata": dict(metadata),
        }
        if record_id:
            record_payload["id"] = str(record_id)
        return MemoryRecord(**record_payload)

    def _record_payload(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "scope": record.scope.value,
            "kind": record.kind.value,
            "content": record.content,
            "tags": record.tags,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    def _parse_scope(self, value: str | None) -> MemoryScope | None:
        return MemoryScope(value) if value else None

    def _parse_kind(self, value: str | None) -> MemoryKind | None:
        return MemoryKind(value) if value else None

    def _require_field(self, kwargs: dict[str, Any], field: str) -> str:
        value = kwargs.get(field)
        if not value:
            raise ValueError(f"Missing required parameter: {field}")
        return str(value)
