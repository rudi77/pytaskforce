"""
Unit tests for Shell and PowerShell Tools

Tests ShellTool and PowerShellTool functionality including:
- Command execution
- Dangerous command blocklist
- Timeout handling
- Working directory support
- Parameter validation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.shell_tool import PowerShellTool, ShellTool


# ---------------------------------------------------------------------------
# ShellTool tests
# ---------------------------------------------------------------------------


class TestShellToolMetadata:
    """Test ShellTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return ShellTool()

    def test_name(self, tool):
        assert tool.name == "shell"

    def test_description(self, tool):
        assert "shell" in tool.description.lower()

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "timeout" in schema["properties"]
        assert "cwd" in schema["properties"]
        assert schema["required"] == ["command"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.HIGH

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool):
        preview = tool.get_approval_preview(command="ls -la", cwd="/tmp", timeout=10)
        assert "ls -la" in preview
        assert "/tmp" in preview
        assert "10" in preview

    def test_get_approval_preview_defaults(self, tool):
        preview = tool.get_approval_preview(command="echo hello")
        assert "echo hello" in preview
        assert "current directory" in preview
        assert "30" in preview


class TestShellToolValidation:
    """Test ShellTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return ShellTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(command="ls -la")
        assert valid is True
        assert error is None

    def test_missing_command(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "command" in error

    def test_non_string_command(self, tool):
        valid, error = tool.validate_params(command=123)
        assert valid is False
        assert "string" in error


class TestShellToolDangerousCommands:
    """Test the dangerous command blocklist."""

    @pytest.fixture
    def tool(self):
        return ShellTool()

    @pytest.mark.parametrize(
        "dangerous_cmd",
        [
            "rm -rf /",
            "rm -rf /*",
            "dd if=/dev/zero of=/dev/sda",
            "dd if=/dev/random of=/dev/sda",
            "format c:",
            "del /f /s /q c:\\",
            ":(){ :|:& };:",
            "> /dev/sda",
            "mkfs.ext4 /dev/sda",
        ],
    )
    async def test_dangerous_commands_blocked(self, tool, dangerous_cmd):
        """Test that known dangerous commands are blocked."""
        result = await tool.execute(command=dangerous_cmd)
        assert result["success"] is False
        assert "blocked" in result["error"].lower()

    async def test_safe_command_not_blocked(self, tool):
        """Test that a normal command is not blocked."""
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(command="echo hello")
            assert result["success"] is True
            assert result["stdout"] == "output"


class TestShellToolExecution:
    """Test ShellTool command execution."""

    @pytest.fixture
    def tool(self):
        return ShellTool()

    async def test_successful_command(self, tool):
        """Test executing a successful command."""
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"hello world\n", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(command="echo hello world")

            assert result["success"] is True
            assert result["stdout"] == "hello world\n"
            assert result["stderr"] == ""
            assert result["returncode"] == 0
            assert result["command"] == "echo hello world"
            assert "error" not in result

    async def test_failed_command(self, tool):
        """Test executing a command that fails."""
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"", b"No such file or directory\n")
            )
            mock_proc.returncode = 1
            mock_create.return_value = mock_proc

            result = await tool.execute(command="cat nonexistent")

            assert result["success"] is False
            assert result["returncode"] == 1
            assert "No such file" in result["stderr"]
            assert "error" in result

    async def test_command_timeout(self, tool):
        """Test command timeout handling."""
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
            mock_proc.kill = MagicMock()
            mock_create.return_value = mock_proc

            result = await tool.execute(command="sleep 100", timeout=5)

            assert result["success"] is False
            assert "timed out" in result["error"]
            assert "5" in result["error"]
            mock_proc.kill.assert_called_once()

    async def test_custom_cwd(self, tool):
        """Test command execution with custom working directory."""
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"/tmp\n", b""))
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await tool.execute(command="pwd", cwd="/tmp")

            assert result["success"] is True
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs.get("cwd") == "/tmp"

    async def test_exception_returns_error_payload(self, tool):
        """Test that unexpected exceptions produce an error payload."""
        with patch(
            "asyncio.create_subprocess_shell",
            side_effect=OSError("Permission denied"),
        ):
            result = await tool.execute(command="restricted_cmd")

            assert result["success"] is False
            assert "error" in result

    async def test_failed_command_uses_stderr_as_error(self, tool):
        """Test that stderr is used as error message for failed commands."""
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 2
            mock_create.return_value = mock_proc

            result = await tool.execute(command="bad_cmd")

            assert result["success"] is False
            assert "failed with code 2" in result["error"]


# ---------------------------------------------------------------------------
# PowerShellTool tests
# ---------------------------------------------------------------------------


class TestPowerShellToolMetadata:
    """Test PowerShellTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return PowerShellTool()

    def test_name(self, tool):
        assert tool.name == "powershell"

    def test_description(self, tool):
        assert "powershell" in tool.description.lower()

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "timeout" in schema["properties"]
        assert "cwd" in schema["properties"]
        assert schema["required"] == ["command"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.HIGH

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool):
        preview = tool.get_approval_preview(command="Get-Process", cwd="C:\\", timeout=60)
        assert "Get-Process" in preview
        assert "POWERSHELL" in preview


class TestPowerShellToolValidation:
    """Test PowerShellTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return PowerShellTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(command="Get-Process")
        assert valid is True
        assert error is None

    def test_missing_command(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "command" in error

    def test_non_string_command(self, tool):
        valid, error = tool.validate_params(command=42)
        assert valid is False
        assert "string" in error


class TestPowerShellToolDangerousCommands:
    """Test PowerShell dangerous command blocklist."""

    @pytest.fixture
    def tool(self):
        return PowerShellTool()

    @pytest.mark.parametrize(
        "dangerous_cmd",
        [
            "Remove-Item -Path * -Force",
            "Remove-Item -Path * -Recurse",
            "Remove-Item -Path * -Recurse -Force",
            "remove-item -path * -force",  # Case insensitive
        ],
    )
    async def test_dangerous_powershell_commands_blocked(self, tool, dangerous_cmd):
        """Test that dangerous PowerShell commands are blocked."""
        result = await tool.execute(command=dangerous_cmd)
        assert result["success"] is False
        assert "blocked" in result["error"].lower()


class TestPowerShellToolExecution:
    """Test PowerShellTool command execution."""

    @pytest.fixture
    def tool(self):
        return PowerShellTool()

    async def test_no_powershell_executable(self, tool):
        """Test error when PowerShell is not installed."""
        with patch("shutil.which", return_value=None):
            result = await tool.execute(command="Get-Process")
            assert result["success"] is False
            assert "powershell" in result["error"].lower()

    async def test_successful_execution(self, tool):
        """Test successful PowerShell command execution."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch("asyncio.create_subprocess_exec") as mock_create:
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(b"output data\n", b""))
                mock_proc.returncode = 0
                mock_create.return_value = mock_proc

                result = await tool.execute(command="Get-Process")

                assert result["success"] is True
                assert result["stdout"] == "output data\n"
                assert result["stderr"] == ""
                assert result["returncode"] == 0

    async def test_failed_execution(self, tool):
        """Test PowerShell command that fails."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch("asyncio.create_subprocess_exec") as mock_create:
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(
                    return_value=(b"", b"cmdlet not found\n")
                )
                mock_proc.returncode = 1
                mock_create.return_value = mock_proc

                result = await tool.execute(command="Bad-Command")

                assert result["success"] is False
                assert "error" in result

    async def test_timeout_handling(self, tool):
        """Test PowerShell timeout handling."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch("asyncio.create_subprocess_exec") as mock_create:
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
                mock_proc.kill = MagicMock()
                mock_create.return_value = mock_proc

                result = await tool.execute(command="Start-Sleep -Seconds 999", timeout=1)

                assert result["success"] is False
                assert "timed out" in result["error"]

    async def test_cwd_nonexistent_directory(self, tool):
        """Test PowerShell with non-existent working directory."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            result = await tool.execute(
                command="Get-Location", cwd="/nonexistent/dir/path"
            )
            assert result["success"] is False
            assert "does not exist" in result["error"]

    async def test_cwd_valid_directory(self, tool, tmp_path):
        """Test PowerShell with a valid working directory."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch("asyncio.create_subprocess_exec") as mock_create:
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))
                mock_proc.returncode = 0
                mock_create.return_value = mock_proc

                result = await tool.execute(command="Get-Location", cwd=str(tmp_path))
                assert result["success"] is True

    async def test_cwd_non_string_rejected(self, tool):
        """Test that non-string cwd is rejected."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            result = await tool.execute(command="Get-Location", cwd=123)
            assert result["success"] is False
            assert "string" in result["error"].lower()

    async def test_cwd_quoted_paths_stripped(self, tool, tmp_path):
        """Test that quoted cwd paths are handled."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch("asyncio.create_subprocess_exec") as mock_create:
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))
                mock_proc.returncode = 0
                mock_create.return_value = mock_proc

                # Pass path wrapped in quotes
                quoted = f'"{str(tmp_path)}"'
                result = await tool.execute(command="Get-Location", cwd=quoted)
                assert result["success"] is True

    async def test_subprocess_exec_exception(self, tool):
        """Test error when subprocess creation fails."""
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("Permission denied"),
            ):
                result = await tool.execute(command="Get-Process")
                assert result["success"] is False
                assert "error" in result

    async def test_cancelled_error_handling(self, tool):
        """Test asyncio CancelledError handling."""
        import asyncio

        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            with patch("asyncio.create_subprocess_exec") as mock_create:
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(
                    side_effect=asyncio.CancelledError()
                )
                mock_proc.kill = MagicMock()
                mock_create.return_value = mock_proc

                result = await tool.execute(command="cmd", timeout=5)
                assert result["success"] is False
                assert "cancelled" in result["error"].lower()
