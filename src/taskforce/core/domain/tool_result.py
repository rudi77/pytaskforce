"""
Tool Result Data Types

Defines typed data structures for tool execution results,
replacing Dict[str, Any] with concrete types.

Also includes tool result store data models (ToolResultHandle, ToolResultPreview,
LineageNode, LineageGraph) that support the ToolResultStoreProtocol interface.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ToolResult:
    """
    Structured result from tool execution.

    Replaces Dict[str, Any] for tool return values with a typed dataclass.

    Attributes:
        success: Whether the tool execution succeeded.
        output: Primary output string (file content, command output, etc.).
        message: Human-readable status message.
        error: Error message if execution failed.
        error_type: Exception class name for debugging.
        metadata: Additional execution metadata (optional).
    """

    success: bool
    output: str = ""
    message: str = ""
    error: str = ""
    error_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for backward compatibility.

        Returns:
            Dictionary representation of the result.
        """
        result: dict[str, Any] = {"success": self.success}
        if self.output:
            result["output"] = self.output
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        if self.error_type:
            result["error_type"] = self.error_type
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResult":
        """
        Create ToolResult from dictionary.

        Args:
            data: Dictionary with tool result data.

        Returns:
            ToolResult instance.
        """
        return cls(
            success=data.get("success", False),
            output=data.get("output", ""),
            message=data.get("message", ""),
            error=data.get("error", ""),
            error_type=data.get("error_type", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def success_result(
        cls,
        output: str = "",
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        """
        Create a successful result.

        Args:
            output: Primary output string.
            message: Human-readable success message.
            metadata: Additional metadata.

        Returns:
            ToolResult with success=True.
        """
        return cls(
            success=True,
            output=output,
            message=message,
            metadata=metadata or {},
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        error_type: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        """
        Create a failed result.

        Args:
            error: Error message.
            error_type: Exception class name.
            metadata: Additional metadata.

        Returns:
            ToolResult with success=False.
        """
        return cls(
            success=False,
            error=error,
            error_type=error_type,
            metadata=metadata or {},
        )


@dataclass
class PlanTask:
    """
    A single task in a plan.

    Replaces Dict with "description" and "status" keys.
    """

    description: str
    status: str = "PENDING"

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for serialization."""
        return {"description": self.description, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "PlanTask":
        """Create PlanTask from dictionary."""
        return cls(
            description=data.get("description", ""),
            status=data.get("status", "PENDING"),
        )


def _utcnow_str() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class ToolResultHandle:
    """
    Lightweight reference to a stored tool result.

    This handle is stored in message history and session state instead of
    the full tool output, keeping token usage under control.

    Attributes:
        id: Unique identifier for this result (e.g., UUID)
        tool: Name of the tool that produced this result
        created_at: ISO 8601 timestamp of result creation
        size_bytes: Size of stored result in bytes
        size_chars: Size of stored result in characters (for text results)
        schema_version: Version of handle format (for future migrations)
        metadata: Additional metadata (e.g., session_id, step, success flag)
    """

    id: str
    tool: str
    created_at: str  # ISO 8601 format
    size_bytes: int
    size_chars: int
    schema_version: str = "1.0"
    metadata: dict[str, Any] | None = None
    # Lineage tracking fields (Story 2.2)
    used_in_answer: bool = False
    reasoning_step: int | None = None
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert handle to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "size_chars": self.size_chars,
            "schema_version": self.schema_version,
            "metadata": self.metadata or {},
            "used_in_answer": self.used_in_answer,
            "reasoning_step": self.reasoning_step,
            "evidence_id": self.evidence_id,
        }

    def mark_used_in_answer(self, evidence_id: str | None = None) -> None:
        """Mark this result as used in the final answer.

        Args:
            evidence_id: Optional evidence ID linking to evidence chain
        """
        self.used_in_answer = True
        if evidence_id:
            self.evidence_id = evidence_id

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResultHandle":
        """Create handle from dictionary."""
        return cls(
            id=data["id"],
            tool=data["tool"],
            created_at=data["created_at"],
            size_bytes=data["size_bytes"],
            size_chars=data["size_chars"],
            schema_version=data.get("schema_version", "1.0"),
            metadata=data.get("metadata"),
            used_in_answer=data.get("used_in_answer", False),
            reasoning_step=data.get("reasoning_step"),
            evidence_id=data.get("evidence_id"),
        )


@dataclass
class ToolResultPreview:
    """
    Short preview of a tool result for LLM context.

    Previews are stored in message history alongside handles to give the LLM
    enough context without overwhelming the prompt with full outputs.

    Attributes:
        handle: Reference to the full result
        preview_text: Short excerpt (200-500 chars)
        truncated: Whether the preview is truncated from a larger result
    """

    handle: ToolResultHandle
    preview_text: str
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert preview to dictionary for JSON serialization."""
        return {
            "handle": self.handle.to_dict(),
            "preview_text": self.preview_text,
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResultPreview":
        """Create preview from dictionary."""
        return cls(
            handle=ToolResultHandle.from_dict(data["handle"]),
            preview_text=data["preview_text"],
            truncated=data["truncated"],
        )


@dataclass
class LineageNode:
    """Node in a lineage graph representing a tool execution.

    Attributes:
        handle: The tool result handle
        step_number: The reasoning step where this tool was called
        parent_handles: Tool results that led to this execution
        child_handles: Tool results that depend on this one
        reasoning_context: Why this tool was called
    """

    handle: ToolResultHandle
    step_number: int
    parent_handles: list[str] = field(default_factory=list)
    child_handles: list[str] = field(default_factory=list)
    reasoning_context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "handle": self.handle.to_dict(),
            "step_number": self.step_number,
            "parent_handles": self.parent_handles,
            "child_handles": self.child_handles,
            "reasoning_context": self.reasoning_context,
        }


@dataclass
class LineageGraph:
    """Graph tracking the lineage of tool results in an execution.

    This graph enables tracing how tool results contributed to the
    final answer, supporting audit and compliance requirements.

    Attributes:
        session_id: Session this lineage belongs to
        nodes: Map of handle ID to lineage node
        final_answer_handles: Handles directly used in the final answer
        created_at: When this lineage was created
    """

    session_id: str
    nodes: dict[str, LineageNode] = field(default_factory=dict)
    final_answer_handles: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow_str)

    def add_node(
        self,
        handle: ToolResultHandle,
        step_number: int,
        parent_handles: list[str] | None = None,
        reasoning_context: str | None = None,
    ) -> LineageNode:
        """Add a node to the lineage graph.

        Args:
            handle: The tool result handle
            step_number: Reasoning step number
            parent_handles: Handles that led to this execution
            reasoning_context: Why this tool was called

        Returns:
            The created lineage node
        """
        node = LineageNode(
            handle=handle,
            step_number=step_number,
            parent_handles=parent_handles or [],
            reasoning_context=reasoning_context,
        )
        self.nodes[handle.id] = node

        # Update parent nodes' child lists
        for parent_id in node.parent_handles:
            if parent_id in self.nodes:
                self.nodes[parent_id].child_handles.append(handle.id)

        return node

    def mark_used_in_answer(self, handle_ids: list[str]) -> None:
        """Mark handles as used in the final answer.

        Args:
            handle_ids: List of handle IDs used in the answer
        """
        self.final_answer_handles = handle_ids
        for handle_id in handle_ids:
            if handle_id in self.nodes:
                self.nodes[handle_id].handle.mark_used_in_answer()

    def get_answer_lineage(self) -> list[LineageNode]:
        """Get all nodes that contributed to the final answer.

        Returns:
            List of lineage nodes in execution order
        """
        # Get direct answer nodes and all ancestors
        visited = set()
        result = []

        def collect_ancestors(handle_id: str) -> None:
            if handle_id in visited or handle_id not in self.nodes:
                return
            visited.add(handle_id)
            node = self.nodes[handle_id]
            for parent_id in node.parent_handles:
                collect_ancestors(parent_id)
            result.append(node)

        for handle_id in self.final_answer_handles:
            collect_ancestors(handle_id)

        return sorted(result, key=lambda n: n.step_number)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "final_answer_handles": self.final_answer_handles,
            "created_at": self.created_at,
        }

    def to_mermaid(self) -> str:
        """Generate a Mermaid diagram of the lineage graph.

        Returns:
            Mermaid diagram string
        """
        lines = ["graph TD"]

        # Add nodes
        for handle_id, node in self.nodes.items():
            short_id = handle_id[:8]
            tool_name = node.handle.tool
            used = "✓" if node.handle.used_in_answer else ""
            lines.append(f'    {short_id}["{tool_name} {used}"]')

        # Add edges
        for handle_id, node in self.nodes.items():
            short_id = handle_id[:8]
            for child_id in node.child_handles:
                child_short = child_id[:8]
                lines.append(f"    {short_id} --> {child_short}")

        # Style nodes used in answer
        for handle_id in self.final_answer_handles:
            short_id = handle_id[:8]
            lines.append(f"    style {short_id} fill:#90EE90")

        return "\n".join(lines)
