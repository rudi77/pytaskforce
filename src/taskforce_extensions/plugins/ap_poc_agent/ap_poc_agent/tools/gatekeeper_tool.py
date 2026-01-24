"""Gatekeeper tool for invoice extraction and compliance checks.

This tool delegates to the invoice-extraction skill script for deterministic,
token-efficient extraction.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class GatekeeperTool:
    """Extract structured invoice data and validate §14 UStG fields.

    This tool executes the invoice-extraction skill script which handles:
    - OCR text extraction via document-extraction-mcp
    - Field parsing (invoice_id, dates, amounts, supplier, recipient)
    - §14 UStG compliance validation

    The script-based approach is deterministic and token-efficient.
    """

    @property
    def name(self) -> str:
        """Return tool name."""
        return "gatekeeper_extract_invoice"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Extract invoice data from PDF/image files. "
            "Uses the invoice-extraction skill script for OCR and parsing. "
            "Returns structured JSON with §14 UStG compliance validation."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "invoice_path": {
                    "type": "string",
                    "description": "Path to invoice file (PDF, PNG, JPG, or JSON)",
                },
            },
            "required": ["invoice_path"],
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "invoice_path" not in kwargs:
            return False, "invoice_path is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Extract invoice fields using the skill script."""
        invoice_path = str(kwargs["invoice_path"])

        # Find the skill script
        script_path = _find_skill_script()
        if not script_path:
            return {
                "success": False,
                "error": "invoice-extraction skill script not found",
                "error_type": "FileNotFoundError",
            }

        # Execute the skill script
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), invoice_path],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout for OCR
            )

            if result.returncode != 0:
                # Try to parse error from stdout first, then stderr
                error_msg = result.stdout.strip() or result.stderr.strip()
                try:
                    error_data = json.loads(result.stdout)
                    return error_data
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": error_msg or "Script execution failed",
                        "error_type": "ScriptError",
                    }

            # Parse the JSON output
            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Invoice extraction timed out after 120 seconds",
                "error_type": "TimeoutError",
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON from script: {e}",
                "error_type": "JSONDecodeError",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }


def _find_skill_script() -> Path | None:
    """Locate the invoice extraction skill script.

    Searches for the script in:
    1. Relative to this file (plugin location)
    2. taskforce_extensions/skills directory
    3. Current working directory
    """
    script_name = "extract_invoice.py"
    skill_path = "skills/invoice-extraction/scripts"

    # Search paths to try
    search_roots = [
        Path(__file__).resolve().parent.parent.parent.parent,  # From plugin
        Path.cwd(),  # Current directory
    ]

    for root in search_roots:
        # Try taskforce_extensions location
        candidate = root / "src" / "taskforce_extensions" / skill_path / script_name
        if candidate.exists():
            return candidate

        # Try direct skills location
        candidate = root / skill_path / script_name
        if candidate.exists():
            return candidate

        # Search parent directories
        for parent in root.parents:
            candidate = parent / "src" / "taskforce_extensions" / skill_path / script_name
            if candidate.exists():
                return candidate

    return None
