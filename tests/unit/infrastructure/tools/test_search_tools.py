"""
Unit tests for Search Tools (GrepTool and GlobTool)

Tests file content searching and file name pattern matching.
Uses tmp_path fixture for all file system operations.
"""

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.search_tools import GlobTool, GrepTool

# ---------------------------------------------------------------------------
# GrepTool tests
# ---------------------------------------------------------------------------


class TestGrepToolMetadata:
    """Test GrepTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return GrepTool()

    def test_name(self, tool):
        assert tool.name == "grep"

    def test_description(self, tool):
        desc = tool.description.lower()
        assert "search" in desc
        assert "regex" in desc or "regular expression" in desc

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "pattern" in schema["properties"]
        assert "path" in schema["properties"]
        assert "glob" in schema["properties"]
        assert "output_mode" in schema["properties"]
        assert "case_insensitive" in schema["properties"]
        assert schema["required"] == ["pattern"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool):
        preview = tool.get_approval_preview(pattern="TODO", path="/src")
        assert "TODO" in preview
        assert "/src" in preview


class TestGrepToolValidation:
    """Test GrepTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return GrepTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(pattern="test")
        assert valid is True
        assert error is None

    def test_missing_pattern(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "pattern" in error

    def test_non_string_pattern(self, tool):
        valid, error = tool.validate_params(pattern=123)
        assert valid is False
        assert "string" in error


class TestGrepToolExecution:
    """Test GrepTool file content searching."""

    @pytest.fixture
    def tool(self):
        return GrepTool()

    @pytest.fixture
    def search_dir(self, tmp_path):
        """Create a directory structure with test files."""
        (tmp_path / "hello.py").write_text(
            "def hello():\n    print('Hello World')\n    return True\n"
        )
        (tmp_path / "test.py").write_text(
            "import pytest\n\ndef test_hello():\n    assert hello() is True\n"
        )
        (tmp_path / "readme.md").write_text(
            "# Project\n\nThis is a test project.\nHello from readme.\n"
        )
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "module.py").write_text(
            "class MyClass:\n    def method(self):\n        return 'hello'\n"
        )
        return tmp_path

    async def test_search_files_with_matches_mode(self, tool, search_dir):
        """Test default files_with_matches output mode."""
        result = await tool.execute(pattern="hello", path=str(search_dir))

        assert result["success"] is True
        assert result["pattern"] == "hello"
        assert result["count"] >= 1

    async def test_search_content_mode(self, tool, search_dir):
        """Test content output mode returns matching lines."""
        result = await tool.execute(
            pattern="def", path=str(search_dir), output_mode="content"
        )

        assert result["success"] is True
        assert result["total_matches"] >= 2
        assert len(result["matches"]) >= 2
        # Each match should have file and content
        for match in result["matches"]:
            assert "file" in match
            assert "content" in match

    async def test_search_count_mode(self, tool, search_dir):
        """Test count output mode returns match counts per file."""
        result = await tool.execute(
            pattern="hello", path=str(search_dir), output_mode="count"
        )

        assert result["success"] is True
        assert result["total_matches"] >= 1
        assert isinstance(result["counts"], dict)

    async def test_case_insensitive_search(self, tool, search_dir):
        """Test case-insensitive search."""
        result = await tool.execute(
            pattern="HELLO", path=str(search_dir), case_insensitive=True
        )

        assert result["success"] is True
        assert result["count"] >= 1

    async def test_case_sensitive_search_no_match(self, tool, search_dir):
        """Test case-sensitive search does not match wrong case."""
        result = await tool.execute(
            pattern="HELLO", path=str(search_dir), case_insensitive=False
        )

        assert result["success"] is True
        # "HELLO" in all caps should not match "hello" or "Hello"
        assert result["count"] == 0

    async def test_search_by_file_type(self, tool, search_dir):
        """Test filtering by file type."""
        result = await tool.execute(
            pattern="hello", path=str(search_dir), file_type="py"
        )

        assert result["success"] is True
        # Only .py files should be in results
        for f in result["files"]:
            assert f.endswith(".py")

    async def test_search_by_glob_pattern(self, tool, search_dir):
        """Test filtering by glob pattern."""
        result = await tool.execute(
            pattern="test", path=str(search_dir), glob="*.md"
        )

        assert result["success"] is True
        for f in result["files"]:
            assert f.endswith(".md")

    async def test_search_nonexistent_path(self, tool):
        """Test search with nonexistent path."""
        result = await tool.execute(
            pattern="test", path="/nonexistent/directory"
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_invalid_regex_pattern(self, tool, search_dir):
        """Test that invalid regex patterns are rejected."""
        result = await tool.execute(
            pattern="[invalid", path=str(search_dir)
        )

        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "regex" in result["error"].lower()

    async def test_max_results_limit(self, tool, tmp_path):
        """Test that max_results limits output."""
        # Create a file with many matching lines
        lines = "\n".join([f"match line {i}" for i in range(50)])
        (tmp_path / "many.txt").write_text(lines)

        result = await tool.execute(
            pattern="match",
            path=str(tmp_path),
            output_mode="content",
            max_results=5,
        )

        assert result["success"] is True
        assert result["total_matches"] <= 5

    async def test_content_mode_with_line_numbers(self, tool, search_dir):
        """Test content mode includes line numbers by default."""
        result = await tool.execute(
            pattern="def hello",
            path=str(search_dir),
            output_mode="content",
            include_line_numbers=True,
        )

        assert result["success"] is True
        if result["total_matches"] > 0:
            assert "line_number" in result["matches"][0]

    async def test_content_mode_without_line_numbers(self, tool, search_dir):
        """Test content mode can exclude line numbers."""
        result = await tool.execute(
            pattern="def hello",
            path=str(search_dir),
            output_mode="content",
            include_line_numbers=False,
        )

        assert result["success"] is True
        if result["total_matches"] > 0:
            assert "line_number" not in result["matches"][0]

    async def test_context_lines(self, tool, search_dir):
        """Test that context_before and context_after work."""
        result = await tool.execute(
            pattern="print",
            path=str(search_dir),
            output_mode="content",
            context_before=1,
            context_after=1,
        )

        assert result["success"] is True
        if result["total_matches"] > 0:
            match = result["matches"][0]
            assert match["context"] is not None
            # Should have before, match, and after entries
            assert len(match["context"]) >= 2

    async def test_search_single_file(self, tool, search_dir):
        """Test searching within a single file."""
        result = await tool.execute(
            pattern="import",
            path=str(search_dir / "test.py"),
        )

        assert result["success"] is True
        assert result["count"] == 1

    async def test_binary_files_skipped(self, tool, tmp_path):
        """Test that binary files are skipped."""
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        (tmp_path / "code.py").write_text("# match this line\n")

        result = await tool.execute(pattern="match", path=str(tmp_path))

        assert result["success"] is True
        for f in result["files"]:
            assert not f.endswith(".png")


class TestGrepToolCollectFiles:
    """Test the _collect_files helper method."""

    @pytest.fixture
    def tool(self):
        return GrepTool()

    def test_collect_from_single_file(self, tool, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        files = tool._collect_files(f, None)
        assert len(files) == 1

    def test_collect_with_glob_pattern(self, tool, tmp_path):
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.txt").write_text("text")
        files = tool._collect_files(tmp_path, "*.py")
        assert all(str(f).endswith(".py") for f in files)

    def test_skips_git_directory(self, tool, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")
        (tmp_path / "main.py").write_text("code")

        files = tool._collect_files(tmp_path, None)
        assert all(".git" not in str(f) for f in files)

    def test_is_binary(self, tool):
        """Test binary file detection."""
        from pathlib import Path

        assert tool._is_binary(Path("image.png")) is True
        assert tool._is_binary(Path("archive.zip")) is True
        assert tool._is_binary(Path("code.py")) is False
        assert tool._is_binary(Path("readme.md")) is False


# ---------------------------------------------------------------------------
# GlobTool tests
# ---------------------------------------------------------------------------


class TestGlobToolMetadata:
    """Test GlobTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return GlobTool()

    def test_name(self, tool):
        assert tool.name == "glob"

    def test_description(self, tool):
        desc = tool.description.lower()
        assert "find" in desc or "glob" in desc

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "pattern" in schema["properties"]
        assert "path" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert schema["required"] == ["pattern"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is True


class TestGlobToolValidation:
    """Test GlobTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return GlobTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(pattern="**/*.py")
        assert valid is True
        assert error is None

    def test_missing_pattern(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "pattern" in error

    def test_non_string_pattern(self, tool):
        valid, error = tool.validate_params(pattern=42)
        assert valid is False
        assert "string" in error


class TestGlobToolExecution:
    """Test GlobTool file pattern matching."""

    @pytest.fixture
    def tool(self):
        return GlobTool()

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project-like directory structure."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("print('hello')")
        (src / "utils.py").write_text("# utils")
        (src / "config.yaml").write_text("key: value")

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_main.py").write_text("def test(): pass")

        (tmp_path / "README.md").write_text("# README")
        (tmp_path / "setup.py").write_text("setup()")

        return tmp_path

    async def test_find_all_python_files(self, tool, project_dir):
        """Test finding all Python files."""
        result = await tool.execute(pattern="**/*.py", path=str(project_dir))

        assert result["success"] is True
        assert result["count"] >= 3
        assert all(f.endswith(".py") for f in result["files"])

    async def test_find_files_in_subdirectory(self, tool, project_dir):
        """Test finding files in a specific subdirectory."""
        result = await tool.execute(
            pattern="*.py", path=str(project_dir / "src")
        )

        assert result["success"] is True
        assert result["count"] == 2

    async def test_find_markdown_files(self, tool, project_dir):
        """Test finding markdown files."""
        result = await tool.execute(pattern="**/*.md", path=str(project_dir))

        assert result["success"] is True
        assert result["count"] >= 1
        assert any("README.md" in f for f in result["files"])

    async def test_nonexistent_path(self, tool):
        """Test with nonexistent directory."""
        result = await tool.execute(
            pattern="*.py", path="/nonexistent/directory"
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_path_is_file_not_directory(self, tool, project_dir):
        """Test that passing a file path returns an error."""
        result = await tool.execute(
            pattern="*.py", path=str(project_dir / "README.md")
        )

        assert result["success"] is False
        assert "not a directory" in result["error"].lower()

    async def test_max_results(self, tool, project_dir):
        """Test max_results limit."""
        result = await tool.execute(
            pattern="**/*.py", path=str(project_dir), max_results=2
        )

        assert result["success"] is True
        assert len(result["files"]) <= 2

    async def test_files_only(self, tool, project_dir):
        """Test that directories are excluded by default."""
        result = await tool.execute(pattern="**/*", path=str(project_dir))

        assert result["success"] is True
        # All results should be files, not directories
        from pathlib import Path

        for f in result["files"]:
            assert Path(f).is_file()

    async def test_include_hidden_false(self, tool, tmp_path):
        """Test that hidden files are excluded by default."""
        (tmp_path / ".hidden_file").write_text("hidden")
        (tmp_path / "visible_file").write_text("visible")

        result = await tool.execute(
            pattern="*", path=str(tmp_path), include_hidden=False
        )

        assert result["success"] is True
        assert all(".hidden" not in f for f in result["files"])

    async def test_include_hidden_true(self, tool, tmp_path):
        """Test that hidden files are included when requested."""
        (tmp_path / ".hidden_file").write_text("hidden")
        (tmp_path / "visible_file").write_text("visible")

        result = await tool.execute(
            pattern="*", path=str(tmp_path), include_hidden=True
        )

        assert result["success"] is True
        assert any(".hidden_file" in f for f in result["files"])

    async def test_skip_common_directories(self, tool, tmp_path):
        """Test that common non-essential directories are skipped."""
        node = tmp_path / "node_modules"
        node.mkdir()
        (node / "package.json").write_text("{}")
        (tmp_path / "app.py").write_text("code")

        result = await tool.execute(pattern="**/*", path=str(tmp_path))

        assert result["success"] is True
        assert all("node_modules" not in f for f in result["files"])

    async def test_sort_by_mtime(self, tool, tmp_path):
        """Test that results are sorted by modification time."""
        import time

        (tmp_path / "old.txt").write_text("old")
        time.sleep(0.05)
        (tmp_path / "new.txt").write_text("new")

        result = await tool.execute(
            pattern="*.txt", path=str(tmp_path), sort_by_mtime=True
        )

        assert result["success"] is True
        assert result["count"] == 2
        # Newest first
        assert "new.txt" in result["files"][0]

    async def test_no_matches(self, tool, tmp_path):
        """Test when no files match the pattern."""
        (tmp_path / "file.txt").write_text("content")

        result = await tool.execute(pattern="*.xyz", path=str(tmp_path))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["files"] == []
