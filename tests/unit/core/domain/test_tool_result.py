"""Tests for ToolResult and PlanTask dataclasses."""


from taskforce.core.domain.tool_result import PlanTask, ToolResult


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_create_success(self) -> None:
        result = ToolResult(success=True, output="file content here", message="Read OK")
        assert result.success is True
        assert result.output == "file content here"
        assert result.message == "Read OK"
        assert result.error == ""
        assert result.error_type == ""
        assert result.metadata == {}

    def test_create_failure(self) -> None:
        result = ToolResult(
            success=False,
            error="File not found",
            error_type="FileNotFoundError",
        )
        assert result.success is False
        assert result.error == "File not found"
        assert result.error_type == "FileNotFoundError"

    def test_to_dict_success_includes_populated_fields(self) -> None:
        result = ToolResult(
            success=True,
            output="data",
            message="Done",
            metadata={"lines": 42},
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "data"
        assert d["message"] == "Done"
        assert d["metadata"]["lines"] == 42
        # Empty fields should not be present
        assert "error" not in d
        assert "error_type" not in d

    def test_to_dict_failure_includes_error_fields(self) -> None:
        result = ToolResult(
            success=False,
            error="Timeout",
            error_type="TimeoutError",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Timeout"
        assert d["error_type"] == "TimeoutError"
        # Empty fields should not be present
        assert "output" not in d
        assert "message" not in d
        assert "metadata" not in d

    def test_to_dict_minimal_success(self) -> None:
        result = ToolResult(success=True)
        d = result.to_dict()
        assert d == {"success": True}

    def test_to_dict_minimal_failure(self) -> None:
        result = ToolResult(success=False)
        d = result.to_dict()
        assert d == {"success": False}

    def test_from_dict_success(self) -> None:
        data = {
            "success": True,
            "output": "hello",
            "message": "OK",
            "metadata": {"key": "value"},
        }
        result = ToolResult.from_dict(data)
        assert result.success is True
        assert result.output == "hello"
        assert result.message == "OK"
        assert result.metadata == {"key": "value"}

    def test_from_dict_failure(self) -> None:
        data = {
            "success": False,
            "error": "Bad input",
            "error_type": "ValueError",
        }
        result = ToolResult.from_dict(data)
        assert result.success is False
        assert result.error == "Bad input"
        assert result.error_type == "ValueError"

    def test_from_dict_empty(self) -> None:
        result = ToolResult.from_dict({})
        assert result.success is False
        assert result.output == ""
        assert result.message == ""
        assert result.error == ""
        assert result.error_type == ""
        assert result.metadata == {}

    def test_from_dict_partial(self) -> None:
        result = ToolResult.from_dict({"success": True, "output": "partial"})
        assert result.success is True
        assert result.output == "partial"
        assert result.error == ""

    def test_success_result_factory(self) -> None:
        result = ToolResult.success_result(output="data", message="OK")
        assert result.success is True
        assert result.output == "data"
        assert result.message == "OK"
        assert result.metadata == {}

    def test_success_result_factory_with_metadata(self) -> None:
        result = ToolResult.success_result(
            output="content",
            metadata={"size": 1024},
        )
        assert result.metadata["size"] == 1024

    def test_success_result_factory_defaults(self) -> None:
        result = ToolResult.success_result()
        assert result.success is True
        assert result.output == ""
        assert result.message == ""
        assert result.metadata == {}

    def test_error_result_factory(self) -> None:
        result = ToolResult.error_result(error="Crash", error_type="RuntimeError")
        assert result.success is False
        assert result.error == "Crash"
        assert result.error_type == "RuntimeError"
        assert result.metadata == {}

    def test_error_result_factory_with_metadata(self) -> None:
        result = ToolResult.error_result(
            error="Timeout",
            metadata={"elapsed_ms": 5000},
        )
        assert result.metadata["elapsed_ms"] == 5000

    def test_error_result_factory_minimal(self) -> None:
        result = ToolResult.error_result(error="Failed")
        assert result.success is False
        assert result.error == "Failed"
        assert result.error_type == ""

    def test_roundtrip(self) -> None:
        original = ToolResult(
            success=True,
            output="file content",
            message="Read complete",
            metadata={"path": "/tmp/file.txt"},
        )
        restored = ToolResult.from_dict(original.to_dict())
        assert restored.success == original.success
        assert restored.output == original.output
        assert restored.message == original.message
        assert restored.metadata == original.metadata

    def test_roundtrip_error(self) -> None:
        original = ToolResult.error_result(
            error="Connection refused",
            error_type="ConnectionError",
            metadata={"host": "localhost"},
        )
        restored = ToolResult.from_dict(original.to_dict())
        assert restored.success is False
        assert restored.error == original.error
        assert restored.error_type == original.error_type
        assert restored.metadata == original.metadata

    def test_metadata_default_is_independent(self) -> None:
        """Default metadata dicts should be independent across instances."""
        r1 = ToolResult(success=True)
        r2 = ToolResult(success=True)
        r1.metadata["key"] = "value"
        assert r2.metadata == {}


class TestPlanTask:
    """Tests for PlanTask dataclass."""

    def test_create_default(self) -> None:
        task = PlanTask(description="Read the file")
        assert task.description == "Read the file"
        assert task.status == "PENDING"

    def test_create_with_status(self) -> None:
        task = PlanTask(description="Deploy app", status="DONE")
        assert task.status == "DONE"

    def test_to_dict(self) -> None:
        task = PlanTask(description="Write tests", status="PENDING")
        d = task.to_dict()
        assert d == {"description": "Write tests", "status": "PENDING"}

    def test_from_dict(self) -> None:
        data = {"description": "Review code", "status": "DONE"}
        task = PlanTask.from_dict(data)
        assert task.description == "Review code"
        assert task.status == "DONE"

    def test_from_dict_defaults(self) -> None:
        task = PlanTask.from_dict({})
        assert task.description == ""
        assert task.status == "PENDING"

    def test_from_dict_partial(self) -> None:
        task = PlanTask.from_dict({"description": "Only desc"})
        assert task.description == "Only desc"
        assert task.status == "PENDING"

    def test_roundtrip(self) -> None:
        original = PlanTask(description="Analyze data", status="DONE")
        restored = PlanTask.from_dict(original.to_dict())
        assert restored.description == original.description
        assert restored.status == original.status

    def test_empty_description(self) -> None:
        task = PlanTask(description="")
        assert task.description == ""
