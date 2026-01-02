"""
Native Tools Package

Provides all native tools migrated from Agent V2.
These tools implement the ToolProtocol interface for dependency injection.
"""

from taskforce.infrastructure.tools.native.ask_user_tool import AskUserTool
from taskforce.infrastructure.tools.native.file_tools import FileReadTool, FileWriteTool
from taskforce.infrastructure.tools.native.git_tools import GitHubTool, GitTool
from taskforce.infrastructure.tools.native.llm_tool import LLMTool
from taskforce.infrastructure.tools.native.python_tool import PythonTool
from taskforce.infrastructure.tools.native.shell_tool import PowerShellTool, ShellTool
from taskforce.infrastructure.tools.native.web_tools import WebFetchTool, WebSearchTool

__all__ = [
    "PythonTool",
    "FileReadTool",
    "FileWriteTool",
    "GitTool",
    "GitHubTool",
    "ShellTool",
    "PowerShellTool",
    "WebSearchTool",
    "WebFetchTool",
    "LLMTool",
    "AskUserTool",
]
