"""Tool to extract text from PDF documents using Docling CLI.

For photos (JPG/PNG), the LLM's native vision capability is used directly.
This tool is only needed for PDF → Markdown conversion.

Requires: `pip install docling` (or `uv pip install docling`)
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


class DoclingExtractTool:
    """Extract text content from PDF/image files using the Docling CLI."""

    @property
    def name(self) -> str:
        return "ap_docling_extract"

    @property
    def description(self) -> str:
        return (
            "Extract text from a PDF document and convert it to Markdown. "
            "Use this for PDF invoices/receipts. For photos (JPG/PNG), "
            "use your vision capability directly instead. "
            "Requires the docling CLI to be installed."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF or image file",
                },
            },
            "required": ["file_path"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> str:
        return "low"

    @property
    def supports_parallelism(self) -> bool:
        return False

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        file_path = kwargs.get("file_path", "")
        if not file_path:
            return False, "file_path is required"
        path = Path(file_path)
        if not path.exists():
            return False, f"File not found: {file_path}"
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            return False, (
                f"Unsupported file type: {path.suffix}. "
                f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
            )
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        file_path = kwargs["file_path"]
        path = Path(file_path).resolve()

        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # Run docling CLI
            process = await asyncio.create_subprocess_exec(
                "docling",
                "--image-export-mode", "placeholder",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(path.parent),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=120
            )

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                # Fallback: try python -m docling
                process2 = await asyncio.create_subprocess_exec(
                    "python", "-m", "docling",
                    "--image-export-mode", "placeholder",
                    str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(path.parent),
                )
                stdout, stderr = await asyncio.wait_for(
                    process2.communicate(), timeout=120
                )
                if process2.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Docling extraction failed: {error_msg}. "
                        "Is docling installed? Run: pip install docling",
                    }

            # Find generated .md file
            md_path = path.with_suffix(".md")
            if not md_path.exists():
                # Check in output directory
                for candidate in path.parent.glob("*.md"):
                    if path.stem in candidate.stem:
                        md_path = candidate
                        break

            if md_path.exists():
                markdown_content = md_path.read_text(encoding="utf-8")
            else:
                # Fallback to stdout
                markdown_content = stdout.decode("utf-8", errors="replace")

            if not markdown_content.strip():
                return {
                    "success": False,
                    "error": "Docling produced empty output. File may be unreadable.",
                }

            # Clean up image placeholders
            markdown_content = re.sub(
                r"!\[.*?\]\(.*?\)", "", markdown_content
            ).strip()

            return {
                "success": True,
                "markdown": markdown_content,
                "source_file": str(path),
                "char_count": len(markdown_content),
            }

        except asyncio.TimeoutError:
            return {"success": False, "error": "Docling extraction timed out (120s)"}
        except FileNotFoundError:
            return {
                "success": False,
                "error": "docling CLI not found. Install with: pip install docling",
            }
        except Exception as e:
            return {"success": False, "error": f"Extraction error: {str(e)}"}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Extract text from: {kwargs.get('file_path', '?')}"
