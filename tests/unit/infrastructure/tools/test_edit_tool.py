"""
Unit tests for Edit Tool

Tests the EditTool exact string replacement functionality including:
- Single and multiple occurrence replacement
- Backup creation
- Error cases (file not found, non-unique match, etc.)
- Parameter validation
"""

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.edit_tool import EditTool


class TestEditToolMetadata:
    """Test EditTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return EditTool()

    def test_name(self, tool):
        assert tool.name == "edit"

    def test_description(self, tool):
        desc = tool.description.lower()
        assert "replace" in desc or "edit" in desc

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "old_string" in schema["properties"]
        assert "new_string" in schema["properties"]
        assert "replace_all" in schema["properties"]
        assert "backup" in schema["properties"]
        assert "file_path" in schema["required"]
        assert "old_string" in schema["required"]
        assert "new_string" in schema["required"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool):
        preview = tool.get_approval_preview(
            file_path="/tmp/test.py",
            old_string="old code",
            new_string="new code",
            replace_all=False,
        )
        assert "/tmp/test.py" in preview
        assert "old code" in preview
        assert "new code" in preview

    def test_get_approval_preview_truncates_long_strings(self, tool):
        preview = tool.get_approval_preview(
            file_path="/tmp/test.py",
            old_string="x" * 300,
            new_string="y" * 300,
        )
        assert "..." in preview


class TestEditToolValidation:
    """Test EditTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return EditTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(
            file_path="/test.py", old_string="old", new_string="new"
        )
        assert valid is True
        assert error is None

    def test_missing_file_path(self, tool):
        valid, error = tool.validate_params(old_string="old", new_string="new")
        assert valid is False
        assert "file_path" in error

    def test_missing_old_string(self, tool):
        valid, error = tool.validate_params(file_path="/test.py", new_string="new")
        assert valid is False
        assert "old_string" in error

    def test_missing_new_string(self, tool):
        valid, error = tool.validate_params(file_path="/test.py", old_string="old")
        assert valid is False
        assert "new_string" in error

    def test_non_string_file_path(self, tool):
        valid, error = tool.validate_params(
            file_path=123, old_string="old", new_string="new"
        )
        assert valid is False
        assert "string" in error

    def test_non_string_old_string(self, tool):
        valid, error = tool.validate_params(
            file_path="/test.py", old_string=123, new_string="new"
        )
        assert valid is False
        assert "string" in error

    def test_non_string_new_string(self, tool):
        valid, error = tool.validate_params(
            file_path="/test.py", old_string="old", new_string=123
        )
        assert valid is False
        assert "string" in error


class TestEditToolExecution:
    """Test EditTool file editing operations."""

    @pytest.fixture
    def tool(self):
        return EditTool()

    async def test_single_replacement(self, tool, tmp_path):
        """Test replacing a unique string in a file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('Hello World')\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="Hello World",
            new_string="Goodbye World",
        )

        assert result["success"] is True
        assert result["occurrences_found"] == 1
        assert result["occurrences_replaced"] == 1
        assert "Goodbye World" in test_file.read_text()

    async def test_replace_all(self, tool, tmp_path):
        """Test replacing all occurrences."""
        test_file = tmp_path / "test.py"
        test_file.write_text("foo bar foo baz foo\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="foo",
            new_string="qux",
            replace_all=True,
        )

        assert result["success"] is True
        assert result["occurrences_found"] == 3
        assert result["occurrences_replaced"] == 3
        assert test_file.read_text() == "qux bar qux baz qux\n"

    async def test_non_unique_match_fails_without_replace_all(self, tool, tmp_path):
        """Test that multiple occurrences fail without replace_all."""
        test_file = tmp_path / "test.py"
        test_file.write_text("foo bar foo baz\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="foo",
            new_string="qux",
            replace_all=False,
        )

        assert result["success"] is False
        assert result["occurrences_found"] == 2
        assert "2 times" in result["error"]
        # File should be unchanged
        assert test_file.read_text() == "foo bar foo baz\n"

    async def test_string_not_found(self, tool, tmp_path):
        """Test replacing a string that does not exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="nonexistent string",
            new_string="replacement",
        )

        assert result["success"] is False
        assert result["occurrences_found"] == 0
        assert "not found" in result["error"].lower()

    async def test_same_old_and_new_string(self, tool, tmp_path):
        """Test that old_string == new_string is rejected."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="hello",
            new_string="hello",
        )

        assert result["success"] is False
        assert "different" in result["error"].lower()

    async def test_empty_old_string(self, tool, tmp_path):
        """Test that empty old_string is rejected."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="",
            new_string="something",
        )

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    async def test_file_not_found(self, tool):
        """Test editing a non-existent file."""
        result = await tool.execute(
            file_path="/nonexistent/file.py",
            old_string="old",
            new_string="new",
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_path_is_directory(self, tool, tmp_path):
        """Test editing a directory instead of a file."""
        result = await tool.execute(
            file_path=str(tmp_path),
            old_string="old",
            new_string="new",
        )

        assert result["success"] is False
        assert "not a file" in result["error"].lower()

    async def test_backup_created(self, tool, tmp_path):
        """Test that a backup file is created."""
        test_file = tmp_path / "test.py"
        original_content = "original content\n"
        test_file.write_text(original_content)

        result = await tool.execute(
            file_path=str(test_file),
            old_string="original",
            new_string="modified",
            backup=True,
        )

        assert result["success"] is True
        assert result["backed_up"] is True

        backup_file = tmp_path / "test.py.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == original_content

    async def test_no_backup(self, tool, tmp_path):
        """Test that backup is skipped when disabled."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="hello",
            new_string="goodbye",
            backup=False,
        )

        assert result["success"] is True
        assert result["backed_up"] is False

        backup_file = tmp_path / "test.py.bak"
        assert not backup_file.exists()

    async def test_preserves_whitespace(self, tool, tmp_path):
        """Test that whitespace is preserved in replacement."""
        test_file = tmp_path / "test.py"
        test_file.write_text("    indented line\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="    indented line",
            new_string="    new indented line",
        )

        assert result["success"] is True
        assert test_file.read_text() == "    new indented line\n"

    async def test_multiline_replacement(self, tool, tmp_path):
        """Test replacing a multiline string."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="line 1\nline 2",
            new_string="new line 1\nnew line 2",
        )

        assert result["success"] is True
        assert test_file.read_text() == "new line 1\nnew line 2\nline 3\n"

    async def test_result_contains_absolute_path(self, tool, tmp_path):
        """Test that the result includes the absolute file path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world\n")

        result = await tool.execute(
            file_path=str(test_file),
            old_string="hello",
            new_string="goodbye",
        )

        assert result["success"] is True
        assert result["file_path"] == str(test_file.absolute())
