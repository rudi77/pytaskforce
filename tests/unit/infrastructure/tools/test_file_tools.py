"""
Unit tests for File Tools

Tests FileReadTool and FileWriteTool functionality.
"""

import pytest

from taskforce.infrastructure.tools.native.file_tools import (
    FileReadTool,
    FileWriteTool,
)


class TestFileReadTool:
    """Test suite for FileReadTool."""

    @pytest.fixture
    def tool(self):
        """Create a FileReadTool instance."""
        return FileReadTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "file_read"
        assert "Read file contents" in tool.description
        assert tool.requires_approval is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "encoding" in schema["properties"]
        assert "max_size_mb" in schema["properties"]
        assert "path" in schema["required"]

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, tmp_path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content)

        result = await tool.execute(path=str(test_file))

        assert result["success"] is True
        assert result["content"] == test_content
        assert result["size"] == len(test_content)
        assert "path" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool):
        """Test reading a non-existent file."""
        result = await tool.execute(path="/nonexistent/file.txt")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_file_size_limit(self, tool, tmp_path):
        """Test file size limit enforcement."""
        test_file = tmp_path / "large.txt"
        # Create a file larger than 1MB
        test_file.write_text("x" * (2 * 1024 * 1024))

        result = await tool.execute(path=str(test_file), max_size_mb=1)

        assert result["success"] is False
        assert "too large" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_custom_encoding(self, tool, tmp_path):
        """Test reading file with custom encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content", encoding="ascii")

        result = await tool.execute(path=str(test_file), encoding="ascii")

        assert result["success"] is True
        assert result["content"] == "Test content"

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(path="/test/file.txt")

        assert valid is True
        assert error is None

    def test_validate_params_missing_path(self, tool):
        """Test parameter validation with missing path."""
        valid, error = tool.validate_params()

        assert valid is False
        assert "path" in error


class TestFileWriteTool:
    """Test suite for FileWriteTool."""

    @pytest.fixture
    def tool(self):
        """Create a FileWriteTool instance."""
        return FileWriteTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "file_write"
        assert "content to a file" in tool.description
        assert tool.requires_approval is True

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "content" in schema["properties"]
        assert "backup" in schema["properties"]
        assert "path" in schema["required"]
        assert "content" in schema["required"]

    @pytest.mark.asyncio
    async def test_write_new_file(self, tool, tmp_path):
        """Test writing a new file."""
        test_file = tmp_path / "new.txt"
        test_content = "New content"

        result = await tool.execute(path=str(test_file), content=test_content)

        assert result["success"] is True
        assert result["size"] == len(test_content)
        assert test_file.exists()
        assert test_file.read_text() == test_content

    @pytest.mark.asyncio
    async def test_overwrite_existing_file(self, tool, tmp_path):
        """Test overwriting an existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        new_content = "New content"
        result = await tool.execute(path=str(test_file), content=new_content)

        assert result["success"] is True
        assert test_file.read_text() == new_content

    @pytest.mark.asyncio
    async def test_backup_creation(self, tool, tmp_path):
        """Test that backup is created when overwriting."""
        test_file = tmp_path / "test.txt"
        old_content = "Old content"
        test_file.write_text(old_content)

        result = await tool.execute(path=str(test_file), content="New content", backup=True)

        assert result["success"] is True
        assert result["backed_up"] is True

        backup_file = tmp_path / "test.txt.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == old_content

    @pytest.mark.asyncio
    async def test_no_backup(self, tool, tmp_path):
        """Test writing without backup."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Old content")

        result = await tool.execute(path=str(test_file), content="New content", backup=False)

        assert result["success"] is True
        assert result["backed_up"] is False

        backup_file = tmp_path / "test.txt.bak"
        assert not backup_file.exists()

    @pytest.mark.asyncio
    async def test_append_to_existing_file(self, tool, tmp_path):
        """Test appending content to an existing file."""
        test_file = tmp_path / "log.md"
        test_file.write_text("# Log\n")

        result = await tool.execute(path=str(test_file), content="- entry 1\n", mode="append")

        assert result["success"] is True
        assert result["mode"] == "append"
        assert result["appended"] == len("- entry 1\n")
        assert test_file.read_text() == "# Log\n- entry 1\n"

    @pytest.mark.asyncio
    async def test_append_creates_new_file(self, tool, tmp_path):
        """Test appending to a non-existent file creates it."""
        test_file = tmp_path / "new_log.md"

        result = await tool.execute(path=str(test_file), content="first line\n", mode="append")

        assert result["success"] is True
        assert test_file.exists()
        assert test_file.read_text() == "first line\n"

    @pytest.mark.asyncio
    async def test_create_parent_directories(self, tool, tmp_path):
        """Test that parent directories are created automatically."""
        test_file = tmp_path / "subdir" / "nested" / "file.txt"

        result = await tool.execute(path=str(test_file), content="Content")

        assert result["success"] is True
        assert test_file.exists()
        assert test_file.read_text() == "Content"

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(path="/test.txt", content="test")

        assert valid is True
        assert error is None

    def test_validate_params_missing_path(self, tool):
        """Test parameter validation with missing path."""
        valid, error = tool.validate_params(content="test")

        assert valid is False
        assert "path" in error

    def test_validate_params_missing_content(self, tool):
        """Test parameter validation with missing content."""
        valid, error = tool.validate_params(path="/test.txt")

        assert valid is False
        assert "content" in error


# ----------------------------------------------------------------------
# Workspace path scoping (ADR-022 §5)
# ----------------------------------------------------------------------


class TestFileToolsWorkspaceScoping:
    """Tools resolve paths against the active workspace, if any."""

    @pytest.fixture(autouse=True)
    def _reset_workspace(self):
        from taskforce.core.interfaces.workspace import set_workspace_context

        set_workspace_context(None)
        yield
        set_workspace_context(None)

    @pytest.fixture
    def workspace(self, tmp_path):
        """Install a workspace context rooted at tmp_path."""
        from dataclasses import dataclass
        from pathlib import Path

        from taskforce.core.interfaces.workspace import set_workspace_context

        @dataclass
        class _Ctx:
            _root: Path

            def root(self) -> Path:
                return self._root

        set_workspace_context(_Ctx(tmp_path))
        return tmp_path

    @pytest.mark.asyncio
    async def test_file_read_respects_workspace_root(self, workspace):
        target = workspace / "doc.md"
        target.write_text("hello", encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute(path="doc.md")

        assert result["success"] is True
        assert result["content"] == "hello"

    @pytest.mark.asyncio
    async def test_file_read_rejects_traversal(self, workspace):
        # Create a file outside the workspace that the agent tries to read.
        outside = workspace.parent / "secret.txt"
        outside.write_text("classified", encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute(path="../secret.txt")

        assert result["success"] is False
        assert "escapes workspace" in result["error"]

    @pytest.mark.asyncio
    async def test_file_write_respects_workspace_root(self, workspace):
        tool = FileWriteTool()
        result = await tool.execute(path="output.log", content="line1")

        assert result["success"] is True
        assert (workspace / "output.log").read_text() == "line1"

    @pytest.mark.asyncio
    async def test_file_write_rejects_absolute_outside_root(self, workspace, tmp_path):
        outside = tmp_path.parent / "evil.txt"
        tool = FileWriteTool()
        result = await tool.execute(path=str(outside), content="x")

        assert result["success"] is False
        assert "escapes workspace" in result["error"]
        assert not outside.exists()

    @pytest.mark.asyncio
    async def test_no_context_keeps_legacy_behaviour(self, tmp_path):
        """Without a workspace context the tools behave as before."""
        from taskforce.core.interfaces.workspace import set_workspace_context

        set_workspace_context(None)

        target = tmp_path / "anywhere.md"
        target.write_text("fine", encoding="utf-8")

        tool = FileReadTool()
        # Absolute path with no scoping → success.
        result = await tool.execute(path=str(target))
        assert result["success"] is True
        assert result["content"] == "fine"
