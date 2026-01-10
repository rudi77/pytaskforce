"""
Ralph Verification Tool

Provides real verification via py_compile and pytest before allowing story completion.
This prevents "hallucinated validation" where stories are marked complete without actual verification.
"""

import asyncio
import py_compile
import subprocess
from pathlib import Path
from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class RalphVerificationTool(ToolProtocol):
    """
    Tool for verifying code before marking stories as complete.

    Supports:
    - Syntax verification via py_compile
    - Test execution via pytest
    - Combined verification (syntax + tests)
    """

    def __init__(self, project_root: str | None = None, pytest_timeout: int = 60):
        """
        Initialize RalphVerificationTool.

        Args:
            project_root: Root directory for test execution (default: current directory)
            pytest_timeout: Timeout in seconds for pytest execution (default: 60)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.pytest_timeout = pytest_timeout

    @property
    def name(self) -> str:
        """Return tool name."""
        return "ralph_verify"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Verify Python code before marking stories as complete. "
            "Actions: 'verify_syntax' runs py_compile on files, "
            "'verify_tests' runs pytest on test files, "
            "'full_verify' runs both syntax and test verification. "
            "Returns success only if all checks pass."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["verify_syntax", "verify_tests", "full_verify"],
                    "description": (
                        "Action to perform: 'verify_syntax' for py_compile, "
                        "'verify_tests' for pytest, 'full_verify' for both"
                    ),
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Python files to verify with py_compile (for verify_syntax and full_verify)",
                },
                "test_path": {
                    "type": "string",
                    "description": "Path to test file or directory for pytest (for verify_tests and full_verify)",
                },
                "test_pattern": {
                    "type": "string",
                    "description": "Optional pytest -k pattern for selective test running",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        """Verification is read-only, no approval needed."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - verification is read-only."""
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        """Verification can run in parallel."""
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        action = kwargs.get("action", "unknown")
        files = kwargs.get("files", [])
        test_path = kwargs.get("test_path")

        preview = f"Tool: {self.name}\nAction: {action}\n"
        if files:
            preview += f"Files to verify: {', '.join(files[:5])}"
            if len(files) > 5:
                preview += f" ... and {len(files) - 5} more"
            preview += "\n"
        if test_path:
            preview += f"Test path: {test_path}\n"
        return preview

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        action = kwargs.get("action")
        if action not in ["verify_syntax", "verify_tests", "full_verify"]:
            return False, f"Invalid action: {action}. Must be 'verify_syntax', 'verify_tests', or 'full_verify'"

        if action in ["verify_syntax", "full_verify"]:
            files = kwargs.get("files")
            if not files and action == "verify_syntax":
                return False, "files is required for verify_syntax action"

        if action in ["verify_tests", "full_verify"]:
            test_path = kwargs.get("test_path")
            if not test_path and action == "verify_tests":
                return False, "test_path is required for verify_tests action"

        return True, None

    async def execute(
        self,
        action: str,
        files: list[str] | None = None,
        test_path: str | None = None,
        test_pattern: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute verification action.

        Args:
            action: 'verify_syntax', 'verify_tests', or 'full_verify'
            files: Python files to verify (for syntax verification)
            test_path: Path to test file/directory (for test verification)
            test_pattern: Optional pytest -k pattern

        Returns:
            Dictionary with success status and verification results
        """
        try:
            if action == "verify_syntax":
                return await self._verify_syntax(files or [])
            elif action == "verify_tests":
                return await self._verify_tests(test_path, test_pattern)
            elif action == "full_verify":
                # First verify syntax
                if files:
                    syntax_result = await self._verify_syntax(files)
                    if not syntax_result["success"]:
                        return {
                            "success": False,
                            "stage": "syntax",
                            "error": "Syntax verification failed",
                            "details": syntax_result.get("errors", []),
                            "output": "Fix syntax errors before tests can run.",
                        }

                # Then verify tests (if test_path provided)
                if test_path:
                    test_result = await self._verify_tests(test_path, test_pattern)
                    if not test_result["success"]:
                        return {
                            "success": False,
                            "stage": "tests",
                            "error": "Test verification failed",
                            "details": test_result.get("output", ""),
                            "output": "Fix failing tests before marking story complete.",
                        }

                return {
                    "success": True,
                    "output": "Full verification passed: syntax OK, tests OK.",
                    "syntax_files_checked": len(files) if files else 0,
                    "test_path": test_path,
                }
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    async def _verify_syntax(self, files: list[str]) -> dict[str, Any]:
        """
        Run py_compile on specified files.

        Args:
            files: List of Python file paths to verify

        Returns:
            Dictionary with success status and any errors found
        """
        if not files:
            return {"success": True, "files_checked": 0, "output": "No files to verify."}

        errors = []
        files_checked = 0

        for file_path in files:
            path = Path(file_path)

            # Skip non-Python files
            if not file_path.endswith(".py"):
                continue

            # Check if file exists
            if not path.exists():
                errors.append(f"File not found: {file_path}")
                continue

            files_checked += 1

            try:
                # Run py_compile synchronously (it's fast enough)
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as e:
                # Extract just the error message, not the full traceback
                error_msg = str(e)
                errors.append(f"{file_path}: {error_msg}")

        if errors:
            return {
                "success": False,
                "files_checked": files_checked,
                "errors": errors,
                "output": f"Syntax errors found in {len(errors)} file(s).",
            }

        return {
            "success": True,
            "files_checked": files_checked,
            "output": f"Syntax verification passed for {files_checked} file(s).",
        }

    async def _verify_tests(
        self, test_path: str | None, test_pattern: str | None = None
    ) -> dict[str, Any]:
        """
        Run pytest on specified path.

        Args:
            test_path: Path to test file or directory
            test_pattern: Optional pytest -k pattern for selective running

        Returns:
            Dictionary with success status and pytest output
        """
        if not test_path:
            return {"success": True, "output": "No test path specified, skipping tests."}

        path = Path(test_path)
        if not path.exists():
            return {
                "success": False,
                "error": f"Test path not found: {test_path}",
                "output": f"Cannot run tests: {test_path} does not exist.",
            }

        # Build pytest command
        cmd = ["python", "-m", "pytest", str(path), "-v", "--tb=short"]
        if test_pattern:
            cmd.extend(["-k", test_pattern])

        try:
            # Run pytest asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.pytest_timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": f"pytest timed out after {self.pytest_timeout} seconds",
                    "output": "Test execution exceeded timeout. Consider breaking tests into smaller chunks.",
                }

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate output to avoid context bloat
            max_output = 2000
            if len(stdout_str) > max_output:
                stdout_str = stdout_str[:max_output] + "\n... (output truncated)"

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "output": stdout_str,
                "stderr": stderr_str[:500] if stderr_str else None,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "pytest not found. Ensure pytest is installed.",
                "output": "Install pytest: pip install pytest",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }
