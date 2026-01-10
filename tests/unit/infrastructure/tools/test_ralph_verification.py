"""
Unit tests for Ralph Verification Tool

Tests RalphVerificationTool functionality including py_compile and pytest integration.
"""

import sys
from pathlib import Path

import pytest

# Add ralph_plugin directory to path for plugin imports
project_root = Path(__file__).parent.parent.parent.parent.parent
ralph_plugin_dir = project_root / "examples" / "ralph_plugin"
if str(ralph_plugin_dir) not in sys.path:
    sys.path.insert(0, str(ralph_plugin_dir))

from ralph_plugin.tools.verification_tool import RalphVerificationTool  # noqa: E402


class TestRalphVerificationTool:
    """Test suite for RalphVerificationTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a RalphVerificationTool instance with temporary project root."""
        return RalphVerificationTool(project_root=str(tmp_path), pytest_timeout=10)

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "ralph_verify"
        assert "verify" in tool.description.lower()
        assert tool.requires_approval is False  # Verification is read-only
        assert tool.approval_risk_level.value == "low"
        assert tool.supports_parallelism is True

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "files" in schema["properties"]
        assert "test_path" in schema["properties"]
        assert "test_pattern" in schema["properties"]
        assert "action" in schema["required"]
        assert schema["properties"]["action"]["enum"] == [
            "verify_syntax",
            "verify_tests",
            "full_verify",
        ]

    def test_validate_params_verify_syntax(self, tool):
        """Test parameter validation for verify_syntax action."""
        valid, error = tool.validate_params(action="verify_syntax", files=["test.py"])
        assert valid is True
        assert error is None

    def test_validate_params_verify_syntax_missing_files(self, tool):
        """Test parameter validation for verify_syntax without files."""
        valid, error = tool.validate_params(action="verify_syntax")
        assert valid is False
        assert "files" in error

    def test_validate_params_verify_tests(self, tool):
        """Test parameter validation for verify_tests action."""
        valid, error = tool.validate_params(action="verify_tests", test_path="tests/")
        assert valid is True
        assert error is None

    def test_validate_params_verify_tests_missing_path(self, tool):
        """Test parameter validation for verify_tests without test_path."""
        valid, error = tool.validate_params(action="verify_tests")
        assert valid is False
        assert "test_path" in error

    def test_validate_params_full_verify(self, tool):
        """Test parameter validation for full_verify action."""
        # full_verify doesn't require both, just valid action
        valid, error = tool.validate_params(action="full_verify")
        assert valid is True
        assert error is None

    def test_validate_params_invalid_action(self, tool):
        """Test parameter validation with invalid action."""
        valid, error = tool.validate_params(action="invalid_action")
        assert valid is False
        assert "Invalid action" in error

    @pytest.mark.asyncio
    async def test_verify_syntax_valid_file(self, tool, tmp_path):
        """Test py_compile on valid Python file."""
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("def hello():\n    return 'world'\n")

        result = await tool.execute(action="verify_syntax", files=[str(valid_file)])

        assert result["success"] is True
        assert result["files_checked"] == 1
        assert "passed" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_verify_syntax_invalid_file(self, tool, tmp_path):
        """Test py_compile fails on invalid syntax."""
        invalid_file = tmp_path / "invalid.py"
        invalid_file.write_text("def hello(:\n    pass\n")  # Syntax error

        result = await tool.execute(action="verify_syntax", files=[str(invalid_file)])

        assert result["success"] is False
        assert "errors" in result
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_verify_syntax_multiple_files(self, tool, tmp_path):
        """Test py_compile on multiple files."""
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("x = 1\n")
        file2.write_text("y = 2\n")

        result = await tool.execute(
            action="verify_syntax", files=[str(file1), str(file2)]
        )

        assert result["success"] is True
        assert result["files_checked"] == 2

    @pytest.mark.asyncio
    async def test_verify_syntax_file_not_found(self, tool, tmp_path):
        """Test py_compile with non-existent file."""
        result = await tool.execute(
            action="verify_syntax", files=[str(tmp_path / "nonexistent.py")]
        )

        assert result["success"] is False
        assert "errors" in result
        assert "not found" in result["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_verify_syntax_skips_non_python(self, tool, tmp_path):
        """Test that non-Python files are skipped."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("This is not Python")

        result = await tool.execute(action="verify_syntax", files=[str(txt_file)])

        assert result["success"] is True
        assert result["files_checked"] == 0

    @pytest.mark.asyncio
    async def test_verify_syntax_empty_list(self, tool):
        """Test py_compile with empty file list."""
        result = await tool.execute(action="verify_syntax", files=[])

        assert result["success"] is True
        assert result["files_checked"] == 0

    @pytest.mark.asyncio
    async def test_verify_tests_passing(self, tool, tmp_path):
        """Test pytest integration with passing tests."""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("def test_pass():\n    assert True\n")

        result = await tool.execute(action="verify_tests", test_path=str(test_file))

        assert result["success"] is True
        assert result["returncode"] == 0

    @pytest.mark.asyncio
    async def test_verify_tests_failing(self, tool, tmp_path):
        """Test pytest integration with failing tests."""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("def test_fail():\n    assert False\n")

        result = await tool.execute(action="verify_tests", test_path=str(test_file))

        assert result["success"] is False
        assert result["returncode"] != 0

    @pytest.mark.asyncio
    async def test_verify_tests_path_not_found(self, tool, tmp_path):
        """Test pytest with non-existent path."""
        result = await tool.execute(
            action="verify_tests", test_path=str(tmp_path / "nonexistent_tests")
        )

        assert result["success"] is False
        assert "not found" in result.get("error", "").lower() or "not found" in result.get("output", "").lower()

    @pytest.mark.asyncio
    async def test_verify_tests_no_path(self, tool):
        """Test pytest with no test_path (should succeed with skip message)."""
        result = await tool.execute(action="verify_tests", test_path=None)

        assert result["success"] is True
        assert "no test path" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_full_verify_syntax_and_tests_pass(self, tool, tmp_path):
        """Test full verification when both syntax and tests pass."""
        # Create valid Python file
        code_file = tmp_path / "app.py"
        code_file.write_text("def add(a, b):\n    return a + b\n")

        # Create passing test - use forward slashes for cross-platform compatibility
        tmp_path_str = str(tmp_path).replace("\\", "/")
        test_file = tmp_path / "test_app.py"
        test_file.write_text(
            "import sys\n"
            f"sys.path.insert(0, r'{tmp_path_str}')\n"
            "from app import add\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        )

        result = await tool.execute(
            action="full_verify",
            files=[str(code_file)],
            test_path=str(test_file),
        )

        assert result["success"] is True
        assert "syntax_files_checked" in result
        assert result["syntax_files_checked"] == 1

    @pytest.mark.asyncio
    async def test_full_verify_syntax_fails(self, tool, tmp_path):
        """Test full verification stops on syntax error."""
        # Create invalid Python file
        code_file = tmp_path / "app.py"
        code_file.write_text("def broken(:\n    pass\n")

        # Test file (would pass if syntax was OK)
        test_file = tmp_path / "test_app.py"
        test_file.write_text("def test_pass():\n    assert True\n")

        result = await tool.execute(
            action="full_verify",
            files=[str(code_file)],
            test_path=str(test_file),
        )

        assert result["success"] is False
        assert result["stage"] == "syntax"
        assert "syntax" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_full_verify_tests_fail(self, tool, tmp_path):
        """Test full verification when syntax passes but tests fail."""
        # Create valid Python file
        code_file = tmp_path / "app.py"
        code_file.write_text("def add(a, b):\n    return a + b\n")

        # Create failing test - use forward slashes for cross-platform compatibility
        tmp_path_str = str(tmp_path).replace("\\", "/")
        test_file = tmp_path / "test_app.py"
        test_file.write_text(
            "import sys\n"
            f"sys.path.insert(0, r'{tmp_path_str}')\n"
            "from app import add\n"
            "def test_add_wrong():\n"
            "    assert add(1, 2) == 999  # Will fail\n"
        )

        result = await tool.execute(
            action="full_verify",
            files=[str(code_file)],
            test_path=str(test_file),
        )

        assert result["success"] is False
        assert result["stage"] == "tests"
        assert "test" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_full_verify_no_test_path(self, tool, tmp_path):
        """Test full verification with only syntax check (no test_path)."""
        code_file = tmp_path / "app.py"
        code_file.write_text("x = 1\n")

        result = await tool.execute(
            action="full_verify",
            files=[str(code_file)],
            test_path=None,
        )

        assert result["success"] is True
        assert result["syntax_files_checked"] == 1

    @pytest.mark.asyncio
    async def test_output_truncation(self, tool, tmp_path):
        """Test that long pytest output is truncated."""
        # Create test that generates lots of output
        test_file = tmp_path / "test_verbose.py"
        test_content = "def test_verbose():\n"
        for i in range(100):
            test_content += f"    print('Line {i}' * 50)\n"
        test_content += "    assert True\n"
        test_file.write_text(test_content)

        result = await tool.execute(action="verify_tests", test_path=str(test_file))

        assert result["success"] is True
        # Output should be truncated to ~2000 chars
        assert len(result.get("output", "")) <= 3000  # Allow some margin

    def test_get_approval_preview(self, tool):
        """Test approval preview generation."""
        preview = tool.get_approval_preview(
            action="full_verify",
            files=["app.py", "util.py"],
            test_path="tests/",
        )

        assert "ralph_verify" in preview
        assert "full_verify" in preview
        assert "app.py" in preview
        assert "tests/" in preview
