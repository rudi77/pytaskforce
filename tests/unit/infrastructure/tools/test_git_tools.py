"""
Unit tests for Git and GitHub Tools

Tests GitTool and GitHubTool functionality including:
- Git operations (init, add, commit, push, status, clone, remote)
- Parameter validation
- Error handling
- GitHub API operations (mocked)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.git_tools import GitHubTool, GitTool

# ---------------------------------------------------------------------------
# GitTool tests
# ---------------------------------------------------------------------------


class TestGitToolMetadata:
    """Test GitTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return GitTool()

    def test_name(self, tool):
        assert tool.name == "git"

    def test_description(self, tool):
        desc = tool.description.lower()
        assert "git" in desc

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "operation" in schema["properties"]
        assert "repo_path" in schema["properties"]
        assert "message" in schema["properties"]
        assert "files" in schema["properties"]
        assert "url" in schema["properties"]
        assert "branch" in schema["properties"]
        assert schema["required"] == ["operation"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.HIGH

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is False

    def test_get_approval_preview_push(self, tool):
        preview = tool.get_approval_preview(
            operation="push", remote="origin", branch="main"
        )
        assert "push" in preview.lower()
        assert "origin" in preview
        assert "main" in preview

    def test_get_approval_preview_other(self, tool):
        preview = tool.get_approval_preview(operation="status")
        assert "status" in preview


class TestGitToolValidation:
    """Test GitTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return GitTool()

    def test_valid_operation(self, tool):
        valid, error = tool.validate_params(operation="status")
        assert valid is True
        assert error is None

    def test_missing_operation(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "operation" in error

    def test_invalid_operation(self, tool):
        valid, error = tool.validate_params(operation="rebase")
        assert valid is False
        assert "rebase" in error

    @pytest.mark.parametrize(
        "op", ["init", "add", "commit", "push", "status", "clone", "remote"]
    )
    def test_all_valid_operations(self, tool, op):
        valid, error = tool.validate_params(operation=op)
        assert valid is True


class TestGitToolExecution:
    """Test GitTool command execution."""

    @pytest.fixture
    def tool(self):
        return GitTool()

    async def test_git_init(self, tool, tmp_path):
        """Test git init creates repository."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"Initialized empty Git repository\n", b"")
            )
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(operation="init", repo_path=str(tmp_path))

            assert result["success"] is True
            assert "git init" in result["command"]

    async def test_git_init_custom_branch(self, tool, tmp_path):
        """Test git init with custom branch name."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"Initialized\n", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="init", repo_path=str(tmp_path), branch="develop"
            )

            assert result["success"] is True
            assert "-b" in result["command"]
            assert "develop" in result["command"]

    async def test_git_add(self, tool, tmp_path):
        """Test git add files."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="add", repo_path=str(tmp_path), files=["file1.py", "file2.py"]
            )

            assert result["success"] is True
            assert "file1.py" in result["command"]
            assert "file2.py" in result["command"]

    async def test_git_add_defaults_to_all(self, tool, tmp_path):
        """Test git add with no files defaults to '.'."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(operation="add", repo_path=str(tmp_path))

            assert result["success"] is True
            assert "git add ." in result["command"]

    async def test_git_commit(self, tool, tmp_path):
        """Test git commit with message."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"[main abc1234] Initial commit\n", b"")
            )
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="commit",
                repo_path=str(tmp_path),
                message="Initial commit",
            )

            assert result["success"] is True
            assert "commit" in result["command"]

    async def test_git_commit_default_message(self, tool, tmp_path):
        """Test git commit with default message."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"committed\n", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(operation="commit", repo_path=str(tmp_path))

            assert result["success"] is True
            assert "Commit via Taskforce Agent" in result["command"]

    async def test_git_push(self, tool, tmp_path):
        """Test git push."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"Everything up-to-date\n"))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="push",
                repo_path=str(tmp_path),
                remote="origin",
                branch="main",
            )

            assert result["success"] is True
            assert "push" in result["command"]
            assert "origin" in result["command"]
            assert "main" in result["command"]

    async def test_git_status(self, tool, tmp_path):
        """Test git status."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"M  src/main.py\n?? newfile.txt\n", b"")
            )
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(operation="status", repo_path=str(tmp_path))

            assert result["success"] is True
            assert "status" in result["command"]
            assert "--short" in result["command"]

    async def test_git_clone_requires_url(self, tool):
        """Test that git clone requires a URL."""
        result = await tool.execute(operation="clone")
        assert result["success"] is False
        assert "url" in result["error"].lower()

    async def test_git_clone_with_url(self, tool):
        """Test git clone with URL."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"Cloning into 'repo'...\n", b"")
            )
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="clone",
                url="https://github.com/user/repo.git",
                repo_path="/tmp/repo",
            )

            assert result["success"] is True
            assert "clone" in result["command"]

    async def test_git_remote_add(self, tool, tmp_path):
        """Test git remote add."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="remote",
                repo_path=str(tmp_path),
                action="add",
                name="upstream",
                url="https://github.com/upstream/repo.git",
            )

            assert result["success"] is True
            assert "remote add" in result["command"]
            assert "upstream" in result["command"]

    async def test_git_remote_add_requires_url(self, tool, tmp_path):
        """Test that git remote add requires a URL."""
        result = await tool.execute(
            operation="remote", repo_path=str(tmp_path), action="add"
        )
        assert result["success"] is False
        assert "url" in result["error"].lower()

    async def test_git_remote_set_url(self, tool, tmp_path):
        """Test git remote set-url."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="remote",
                repo_path=str(tmp_path),
                action="set_url",
                url="https://github.com/new/repo.git",
            )

            assert result["success"] is True
            assert "set-url" in result["command"]

    async def test_git_remote_set_url_requires_url(self, tool, tmp_path):
        """Test that git remote set-url requires a URL."""
        result = await tool.execute(
            operation="remote", repo_path=str(tmp_path), action="set_url"
        )
        assert result["success"] is False
        assert "url" in result["error"].lower()

    async def test_git_remote_list(self, tool, tmp_path):
        """Test git remote list."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"origin\thttps://github.com/user/repo.git (fetch)\n", b"")
            )
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(
                operation="remote", repo_path=str(tmp_path), action="list"
            )

            assert result["success"] is True
            assert "remote -v" in result["command"]

    async def test_git_remote_unknown_action(self, tool, tmp_path):
        """Test git remote with unknown action."""
        result = await tool.execute(
            operation="remote", repo_path=str(tmp_path), action="remove"
        )
        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    async def test_unknown_operation(self, tool, tmp_path):
        """Test unknown git operation."""
        result = await tool.execute(operation="rebase", repo_path=str(tmp_path))
        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    async def test_repo_path_not_exists(self, tool):
        """Test with non-existent repo path for non-clone/init operations."""
        result = await tool.execute(
            operation="status", repo_path="/nonexistent/path/to/repo"
        )
        assert result["success"] is False
        assert "does not exist" in result["error"]

    async def test_command_timeout(self, tool, tmp_path):
        """Test git command timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
            mock_proc.kill = MagicMock()
            mock_create.return_value = mock_proc

            result = await tool.execute(operation="status", repo_path=str(tmp_path))

            assert result["success"] is False
            assert "error" in result


# ---------------------------------------------------------------------------
# GitHubTool tests
# ---------------------------------------------------------------------------


class TestGitHubToolMetadata:
    """Test GitHubTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return GitHubTool()

    def test_name(self, tool):
        assert tool.name == "github"

    def test_description(self, tool):
        assert "github" in tool.description.lower()

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert schema["required"] == ["action"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.HIGH

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is False


class TestGitHubToolValidation:
    """Test GitHubTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return GitHubTool()

    def test_valid_action(self, tool):
        valid, error = tool.validate_params(action="create_repo")
        assert valid is True

    def test_missing_action(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "action" in error

    def test_invalid_action(self, tool):
        valid, error = tool.validate_params(action="fork_repo")
        assert valid is False
        assert "fork_repo" in error


class TestGitHubToolExecution:
    """Test GitHubTool execution with mocked HTTP."""

    @pytest.fixture
    def tool(self):
        return GitHubTool()

    async def test_missing_github_token(self, tool):
        """Test error when GITHUB_TOKEN is not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Ensure both token env vars are cleared
            with patch("os.getenv", return_value=None):
                result = await tool.execute(action="create_repo", name="test-repo")
                assert result["success"] is False
                assert "github_token" in result["error"].lower()

    async def test_create_repo_requires_name(self, tool):
        """Test that create_repo requires a repository name."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            result = await tool.execute(action="create_repo")
            assert result["success"] is False
            assert "name" in result["error"].lower()

    async def test_create_repo_success(self, tool):
        """Test successful repository creation."""
        response_body = json.dumps(
            {"full_name": "user/test-repo", "html_url": "https://github.com/user/test-repo"}
        ).encode()

        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.getcode.return_value = 201
                mock_resp.read.return_value = response_body
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp

                result = await tool.execute(
                    action="create_repo", name="test-repo", private=True
                )

                assert result["success"] is True
                assert result["repo_full_name"] == "user/test-repo"
                assert result["response_status"] == 201

    async def test_delete_repo_requires_full_name(self, tool):
        """Test that delete_repo requires 'owner/repo' format."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            result = await tool.execute(action="delete_repo", name="test-repo")
            assert result["success"] is False
            assert "owner/repo" in result["error"]

    async def test_unknown_action(self, tool):
        """Test unknown GitHub action."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            result = await tool.execute(action="fork_repo")
            assert result["success"] is False
            assert "unknown" in result["error"].lower()
