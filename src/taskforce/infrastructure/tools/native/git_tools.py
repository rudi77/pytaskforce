"""
Git and GitHub Tools

Provides Git operations (init, add, commit, push, etc.) and GitHub API integration.
Migrated from Agent V2 with full preservation of functionality.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import structlog

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class GitTool(ToolProtocol):
    """Comprehensive Git operations with subprocess handling."""

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Execute git operations (init, add, commit, push, status, clone, etc.)"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "init",
                        "add",
                        "commit",
                        "push",
                        "status",
                        "clone",
                        "remote",
                    ],
                    "description": "Git operation to perform",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path (default: current directory)",
                },
                "remote": {
                    "type": "string",
                    "description": "Remote name (for push), defaults to 'origin'",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (for commit operation)",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to add (for add operation)",
                },
                "url": {
                    "type": "string",
                    "description": "Remote URL (for remote/clone operations)",
                },
                "branch": {"type": "string", "description": "Branch name"},
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "set_url"],
                    "description": "Remote sub-action when operation=remote",
                },
                "name": {
                    "type": "string",
                    "description": "Remote name for operation=remote (default: origin)",
                },
            },
            "required": ["operation"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.HIGH

    def get_approval_preview(self, **kwargs: Any) -> str:
        operation = kwargs.get("operation")
        if operation == "push":
            remote = kwargs.get("remote", "origin")
            branch = kwargs.get("branch", "main")
            return f"⚠️ GIT PUSH OPERATION\nTool: {self.name}\nOperation: push\nRemote: {remote}\nBranch: {branch}"
        return f"Tool: {self.name}\nOperation: {operation}\nParameters: {kwargs}"

    async def execute(
        self, operation: str, repo_path: str = ".", **kwargs
    ) -> Dict[str, Any]:
        """
        Execute git operations.

        Args:
            operation: Git operation to perform
            repo_path: Repository path (default: current directory)
            **kwargs: Operation-specific parameters

        Returns:
            Dictionary with:
            - success: bool - True if operation succeeded
            - output: str - Command output
            - command: str - Executed command
            - error: str - Error message (if failed)
        """
        logger = structlog.get_logger().bind(tool=self.name, operation=operation)
        try:
            repo_path = Path(repo_path)

            # Ensure a valid working directory is used across operations
            if operation == "init":
                # For init, create the directory if it doesn't exist
                try:
                    if not repo_path.exists():
                        repo_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.error("git_execute_exception", error=str(e))
                    return {
                        "success": False,
                        "error": f"Failed to prepare repo directory: {e}",
                    }
            elif operation != "clone":
                # For all other operations that use cwd=repo_path, ensure it exists
                if not repo_path.exists():
                    return {
                        "success": False,
                        "error": f"Repository path does not exist: {repo_path}",
                    }

            logger.info("git_execute_start", cwd=str(repo_path), args=kwargs)

            # Build command based on operation
            if operation == "init":
                cmd = ["git", "init", "-b", kwargs.get("branch", "main")]
            elif operation == "add":
                files = kwargs.get("files", ["."])
                cmd = ["git", "add"] + files
            elif operation == "commit":
                message = kwargs.get("message", "Commit via Taskforce Agent")
                cmd = ["git", "commit", "-m", message]
            elif operation == "push":
                remote = kwargs.get("remote", "origin")
                branch = kwargs.get("branch", "main")
                cmd = ["git", "push", "-u", remote, branch]
            elif operation == "status":
                cmd = ["git", "status", "--short"]
            elif operation == "clone":
                url = kwargs.get("url")
                if not url:
                    return {"success": False, "error": "URL required for clone"}
                cmd = ["git", "clone", url, str(repo_path)]
            elif operation == "remote":
                action = kwargs.get("action", "add")
                remote_name = kwargs.get("name", "origin")
                if action == "add":
                    if not kwargs.get("url"):
                        return {
                            "success": False,
                            "error": "url is required for remote add",
                        }
                    cmd = ["git", "remote", "add", remote_name, kwargs["url"]]
                elif action == "set_url":
                    if not kwargs.get("url"):
                        return {
                            "success": False,
                            "error": "url is required for remote set_url",
                        }
                    cmd = ["git", "remote", "set-url", remote_name, kwargs["url"]]
                elif action == "list":
                    cmd = ["git", "remote", "-v"]
                else:
                    return {"success": False, "error": f"Unknown remote action: {action}"}
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

            # Execute command
            result = subprocess.run(
                cmd,
                cwd=repo_path if operation != "clone" else ".",
                capture_output=True,
                text=True,
                timeout=30,
            )

            payload = {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "command": " ".join(cmd),
            }
            if payload["success"]:
                logger.info("git_execute_success", command=payload["command"])
            else:
                logger.error(
                    "git_execute_failed", command=payload["command"], error=payload["error"]
                )
            return payload

        except subprocess.TimeoutExpired:
            logger.error("git_execute_timeout")
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            logger.error("git_execute_exception", error=str(e))
            return {"success": False, "error": str(e)}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "operation" not in kwargs:
            return False, "Missing required parameter: operation"
        operation = kwargs.get("operation")
        if operation not in [
            "init",
            "add",
            "commit",
            "push",
            "status",
            "clone",
            "remote",
        ]:
            return False, f"Invalid operation: {operation}"
        return True, None


class GitHubTool(ToolProtocol):
    """GitHub operations using GitHub REST API (requires GITHUB_TOKEN)."""

    @property
    def name(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return "GitHub operations (create/list/delete repos) using REST API. Requires GITHUB_TOKEN."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_repo", "list_repos", "delete_repo"],
                    "description": "GitHub action to perform",
                },
                "name": {"type": "string", "description": "Repository name"},
                "private": {
                    "type": "boolean",
                    "description": "Make repository private",
                },
                "description": {
                    "type": "string",
                    "description": "Repository description",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.HIGH

    def get_approval_preview(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        name = kwargs.get("name", "")
        return f"⚠️ GITHUB API OPERATION\nTool: {self.name}\nAction: {action}\nRepository: {name}"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Execute GitHub API operations.

        Args:
            action: GitHub action to perform
            **kwargs: Action-specific parameters

        Returns:
            Dictionary with:
            - success: bool - True if operation succeeded
            - response_status: int - HTTP status code
            - Additional fields based on action
            - error: str - Error message (if failed)
        """
        logger = structlog.get_logger().bind(tool=self.name, action=action)
        try:
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
            if not token:
                logger.error("github_missing_token")
                return {
                    "success": False,
                    "error": "GITHUB_TOKEN environment variable is not set",
                }

            api_base = "https://api.github.com"

            def request(
                method: str, url: str, body: Optional[Dict[str, Any]] = None
            ) -> Tuple[int, str]:
                headers = {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "TaskforceAgent",
                }
                data_bytes = None
                if body is not None:
                    data_bytes = json.dumps(body).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                req = urllib.request.Request(
                    url, data=data_bytes, headers=headers, method=method
                )
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        return resp.getcode(), resp.read().decode("utf-8")
                except urllib.error.HTTPError as e:
                    try:
                        detail = e.read().decode("utf-8")
                    except Exception:
                        detail = str(e)
                    return e.code, detail
                except urllib.error.URLError as e:
                    return 0, f"URLError: {e.reason}"
                except Exception as e:
                    return -1, f"Exception: {type(e).__name__}: {e}"

            if action == "create_repo":
                repo_name = kwargs.get("name")
                if not repo_name:
                    logger.error("github_missing_repo_name")
                    return {"success": False, "error": "Repository name required"}
                body = {
                    "name": repo_name,
                    "private": bool(kwargs.get("private", False)),
                    "description": kwargs.get("description") or "",
                }
                # Basic retry for transient 5xx
                attempts = 0
                status, text = 0, ""
                while attempts < 2:
                    attempts += 1
                    status, text = request("POST", f"{api_base}/user/repos", body)
                    if status not in (500, 502, 503, 504, -1, 0):
                        break
                    time.sleep(1)
                ok = status in (200, 201)
                payload = {}
                try:
                    payload = json.loads(text) if text else {}
                except Exception:
                    payload = {"raw": text}
                error_msg = None
                if not ok:
                    base_msg = (
                        payload.get("message") if isinstance(payload, dict) else None
                    )
                    errors = payload.get("errors") if isinstance(payload, dict) else None
                    if status == 422 and errors:
                        error_msg = f"Validation failed: {errors}"
                    elif status in (401, 403):
                        error_msg = (
                            base_msg
                            or "Authentication/authorization failed. Check GITHUB_TOKEN scopes."
                        )
                    else:
                        error_msg = base_msg or text or f"HTTP {status}"
                result = {
                    "success": ok,
                    "repo_name": repo_name,
                    "response_status": status,
                    "repo_full_name": (
                        payload.get("full_name") if isinstance(payload, dict) else None
                    ),
                    "repo_html_url": (
                        payload.get("html_url") if isinstance(payload, dict) else None
                    ),
                    "error": error_msg,
                }
                if ok:
                    logger.info(
                        "github_create_repo_success", full_name=result["repo_full_name"]
                    )
                else:
                    logger.error(
                        "github_create_repo_failed", status=status, error=error_msg
                    )
                return result

            elif action == "list_repos":
                status, text = request("GET", f"{api_base}/user/repos?per_page=20")
                ok = status == 200
                repos = []
                try:
                    data = json.loads(text) if text else []
                    repos = [
                        item.get("full_name")
                        for item in data
                        if isinstance(item, dict)
                    ]
                except Exception:
                    repos = []
                result = {
                    "success": ok,
                    "repos": repos,
                    "response_status": status,
                    "error": None if ok else text,
                }
                if ok:
                    logger.info("github_list_repos_success", count=len(repos))
                else:
                    logger.error("github_list_repos_failed", status=status)
                return result

            elif action == "delete_repo":
                full_name = kwargs.get("name")
                if not full_name or "/" not in full_name:
                    logger.error("github_invalid_repo_full_name")
                    return {
                        "success": False,
                        "error": "Repository name must be in 'owner/repo' format",
                    }
                status, text = request("DELETE", f"{api_base}/repos/{full_name}")
                ok = status in (200, 202, 204)
                result = {
                    "success": ok,
                    "repo_name": full_name,
                    "response_status": status,
                    "error": None if ok else text,
                }
                if ok:
                    logger.info("github_delete_repo_success", repo=full_name)
                else:
                    logger.error("github_delete_repo_failed", status=status, error=text)
                return result

            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                detail = str(e)
            logger.error(
                "github_http_error", status=getattr(e, "code", None), detail=detail
            )
            return {"success": False, "error": f"HTTPError {e.code}: {detail}"}
        except urllib.error.URLError as e:
            logger.error("github_url_error", reason=getattr(e, "reason", None))
            return {"success": False, "error": f"URLError: {e.reason}"}
        except Exception as e:
            logger.error("github_execute_exception", error=str(e))
            return {"success": False, "error": str(e)}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "action" not in kwargs:
            return False, "Missing required parameter: action"
        action = kwargs.get("action")
        if action not in ["create_repo", "list_repos", "delete_repo"]:
            return False, f"Invalid action: {action}"
        return True, None

