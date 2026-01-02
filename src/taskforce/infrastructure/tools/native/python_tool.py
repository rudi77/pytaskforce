"""
Python Code Execution Tool

Executes Python code in an isolated namespace with pre-imported libraries.
Migrated from Agent V2 with full preservation of execution semantics.
"""

import contextlib
import os
from pathlib import Path
from typing import Any, Dict, Optional

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class PythonTool(ToolProtocol):
    """Execute Python code in isolated namespace with pre-imported libraries."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return (
            "Execute Python code for complex logic, data processing, and custom operations. "
            "Your code must assign the final output to a variable named 'result'. "
            "Pre-imported modules: os, sys, json, re, pathlib, shutil, subprocess, datetime, time, random, "
            "base64, hashlib, tempfile, csv, pandas as pd, matplotlib.pyplot as plt, and typing types (Dict, List, Any, Optional); "
            "from datetime: datetime, timedelta. "
            "Builtins available include common utilities (print, len, range, enumerate, str, int, float, bool, list, dict, set, tuple, "
            "sum, min, max, abs, round, sorted, reversed, zip, map, filter, next, any, all, isinstance, open, __import__, locals). "
            "If you need input variables (e.g., 'data'), pass them in via the 'context' dict; its keys are exposed as top-level variables."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Must assign output to 'result' variable.",
                },
                "context": {
                    "type": "object",
                    "description": "Context variables to expose as top-level variables in code namespace",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for code execution (optional)",
                },
            },
            "required": ["code"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.HIGH

    def get_approval_preview(self, **kwargs: Any) -> str:
        code = kwargs.get("code", "")
        code_preview = code[:200] + "..." if len(code) > 200 else code
        cwd = kwargs.get("cwd", "current directory")
        return f"⚠️ PYTHON CODE EXECUTION\nTool: {self.name}\nWorking Directory: {cwd}\nCode Preview:\n{code_preview}"

    async def execute(
        self,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        cwd: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute Python code in controlled namespace.

        Args:
            code: Python code to execute (must set 'result' variable)
            context: Optional context dict with variables to expose
            cwd: Optional working directory for execution

        Returns:
            Dictionary with:
            - success: bool - True if execution succeeded
            - result: Any - Value of 'result' variable
            - variables: Dict - All user-defined variables
            - context_updated: Dict - Updated context dict
            - error: str - Error message (if failed)
            - type: str - Error type (if failed)
            - traceback: str - Full traceback (if failed)
            - hints: List[str] - Helpful hints for fixing errors (if failed)
        """

        # CWD context manager
        @contextlib.contextmanager
        def safe_chdir(path):
            original = os.getcwd()
            try:
                if path:
                    os.chdir(path)
                yield
            finally:
                try:
                    os.chdir(original)
                except (OSError, FileNotFoundError):
                    pass

        # Validate and prepare cwd
        cwd_path = None
        if cwd is not None:
            if not isinstance(cwd, str):
                return {"success": False, "error": "cwd must be a string path"}
            sanitized = cwd.strip()
            if (sanitized.startswith('"') and sanitized.endswith('"')) or (
                sanitized.startswith("'") and sanitized.endswith("'")
            ):
                sanitized = sanitized[1:-1]
            sanitized = os.path.expandvars(os.path.expanduser(sanitized))
            if os.name == "nt":
                sanitized = sanitized.replace("/", "\\")
            p = Path(sanitized)
            if not p.exists() or not p.is_dir():
                return {
                    "success": False,
                    "error": f"cwd does not exist or is not a directory: {sanitized}",
                }
            cwd_path = str(p)

        # Import code block
        import_code = """
import os, sys, json, re, pathlib, shutil
import subprocess, datetime, time, random
import base64, hashlib, tempfile, csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
"""

        # Optional imports (pandas, matplotlib)
        optional_imports = """
try:
    import pandas as pd
except ImportError:
    pd = None
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
"""

        # Normalize context parameter to dict
        context_dict = {}
        if context:
            if isinstance(context, dict):
                context_dict = context
            elif isinstance(context, str):
                # Try to parse as JSON if it's a string
                try:
                    import json

                    context_dict = json.loads(context)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Build safe namespace with restricted builtins
        safe_namespace = {
            "__builtins__": {
                # Basic functions
                "print": print,
                "len": len,
                "range": range,
                "enumerate": enumerate,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "sum": sum,
                "min": min,
                "max": max,
                "abs": abs,
                "round": round,
                "sorted": sorted,
                "reversed": reversed,
                "zip": zip,
                "map": map,
                "filter": filter,
                "next": next,
                "any": any,
                "all": all,
                "isinstance": isinstance,
                "open": open,
                "__import__": __import__,
                "locals": locals,
                # Exception classes
                "Exception": Exception,
                "ImportError": ImportError,
                "ValueError": ValueError,
                "TypeError": TypeError,
                "KeyError": KeyError,
                "IndexError": IndexError,
                "AttributeError": AttributeError,
                "OSError": OSError,
                "FileNotFoundError": FileNotFoundError,
                "RuntimeError": RuntimeError,
                "StopIteration": StopIteration,
            },
            "context": context_dict,
        }

        # Expose context keys as top-level variables
        if context_dict:
            for key, value in context_dict.items():
                if (
                    isinstance(key, str)
                    and key.isidentifier()
                    and key not in safe_namespace
                ):
                    safe_namespace[key] = value

        try:
            # Execute imports first
            exec(import_code, safe_namespace)
            exec(optional_imports, safe_namespace)
        except ImportError as e:
            return {
                "success": False,
                "error": f"Missing library: {e.name}",
                "hint": f"Install with: pip install {e.name}",
                "type": "ImportError",
            }

        try:
            # Execute user code
            with safe_chdir(cwd_path):
                exec(code, safe_namespace)

            # Check for 'result' variable
            if "result" not in safe_namespace:
                return {
                    "success": False,
                    "error": "Code must assign output to 'result' variable",
                    "hint": "Add: result = your_output",
                    "variables": list(safe_namespace.keys()),
                }

            # Sanitize outputs to ensure they are pickle/JSON safe
            def _sanitize(value, depth: int = 0):
                if depth > 4:
                    return repr(value)
                if value is None or isinstance(value, (bool, int, float, str)):
                    return value
                if isinstance(value, (bytes, bytearray)):
                    try:
                        return bytes(value).decode("utf-8", errors="replace")
                    except Exception:
                        return repr(value)
                if isinstance(value, Path):
                    return str(value)
                if isinstance(value, (list, tuple, set)):
                    return [_sanitize(v, depth + 1) for v in value]
                if isinstance(value, dict):
                    return {
                        str(_sanitize(k, depth + 1)): _sanitize(v, depth + 1)
                        for k, v in value.items()
                    }
                try:
                    return repr(value)
                except Exception:
                    return f"<unserializable {type(value).__name__}>"

            result_value = _sanitize(safe_namespace.get("result", None))

            # Get all user-defined variables
            raw_user_vars = {
                k: v
                for k, v in safe_namespace.items()
                if not k.startswith("_")
                and k
                not in [
                    "os",
                    "sys",
                    "json",
                    "re",
                    "pathlib",
                    "shutil",
                    "subprocess",
                    "datetime",
                    "time",
                    "random",
                    "base64",
                    "hashlib",
                    "tempfile",
                    "csv",
                    "Path",
                    "pd",
                    "plt",
                    "timedelta",
                    "Dict",
                    "List",
                    "Any",
                    "Optional",
                    "context",
                ]
            }
            user_vars = {k: _sanitize(v) for k, v in raw_user_vars.items()}

            return {
                "success": True,
                "result": result_value,
                "variables": user_vars,
                "context_updated": _sanitize(context_dict),
            }

        except Exception as e:
            import traceback

            # Provide helpful hints for common errors
            hints = []
            error_type = type(e).__name__
            error_msg = str(e)

            if error_type == "NameError" and "not defined" in error_msg:
                var_name = error_msg.split("'")[1] if "'" in error_msg else "unknown"
                hints.append(f"Variable '{var_name}' is not defined.")
                hints.append(
                    f"REMEMBER: Each Python call has an ISOLATED namespace!"
                )
                hints.append(f"  1. If '{var_name}' is from a previous step, you must:")
                hints.append(f"     → Re-read the source data (CSV, JSON, etc.), OR")
                hints.append(f"     → Request it via 'context' parameter")
                hints.append(
                    f"  2. If '{var_name}' should be created here, define it in your code"
                )
                hints.append(
                    f"  3. Check the file path and make sure the data source exists"
                )

            elif error_type == "KeyError":
                hints.append("KeyError: Check if the key exists in the dictionary")
                hints.append("Use .get() method or check with 'if key in dict'")

            elif error_type == "FileNotFoundError":
                hints.append("File not found. Check:")
                hints.append("  1. The file path is correct")
                hints.append("  2. The file exists in the current directory")
                hints.append("  3. Use absolute path or set 'cwd' parameter")

            elif error_type == "ImportError":
                hints.append("Import failed. The library may not be installed.")
                hints.append("Try using pd, plt, or other pre-imported libraries")

            elif error_type == "AttributeError":
                hints.append(
                    "AttributeError: Check if you're calling the right method/attribute"
                )
                hints.append("Make sure the object is of the expected type")
                hints.append("Use type() or isinstance() to verify object types")

            return {
                "success": False,
                "error": error_msg,
                "type": error_type,
                "traceback": traceback.format_exc(),
                "hints": hints,
                "code_snippet": code[:200] + "..." if len(code) > 200 else code,
            }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "code" not in kwargs:
            return False, "Missing required parameter: code"
        if not isinstance(kwargs["code"], str):
            return False, "Parameter 'code' must be a string"
        return True, None

