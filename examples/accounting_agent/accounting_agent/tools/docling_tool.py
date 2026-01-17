"""
Docling CLI wrapper tool for PDF to Markdown conversion.

This tool wraps the external Docling CLI to extract text and structure
from PDF and image documents, returning the content as Markdown.
"""

import asyncio
from pathlib import Path
import re
from typing import Any

from accounting_agent.tools.tool_base import ApprovalRiskLevel


class DoclingTool:
    """
    Extract document content as Markdown using Docling CLI.

    Wraps the external docling command:
    docling "path/to/document.pdf"

    Returns the generated Markdown content.

    Prerequisites:
        - docling must be installed and available in PATH
        - Install via: pip install docling (in a separate environment)
    """

    @property
    def name(self) -> str:
        """Return tool name."""
        return "docling_extract"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Convert PDF or image documents to Markdown using the Docling CLI. "
            "Extracts text, tables, and structure from invoices and documents. "
            "Returns markdown content suitable for further processing."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to PDF or image file to extract"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional output directory for generated files"
                }
            },
            "required": ["file_path"]
        }

    @property
    def requires_approval(self) -> bool:
        """Read-only operation, no approval required."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - read-only document extraction."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        file_path = kwargs.get("file_path", "<not specified>")
        return (
            f"Tool: {self.name}\n"
            f"Operation: Extract markdown from document\n"
            f"File: {file_path}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "file_path" not in kwargs:
            return False, "Missing required parameter: file_path"
        file_path = kwargs["file_path"]
        if not isinstance(file_path, str):
            return False, "file_path must be a string"
        if not file_path.strip():
            return False, "file_path cannot be empty"
        return True, None

    async def execute(
        self,
        file_path: str,
        output_dir: str | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Execute docling CLI and return markdown output.

        Args:
            file_path: Path to PDF or image file
            output_dir: Optional output directory

        Returns:
            Dictionary with:
            - success: bool
            - markdown: Extracted markdown content (on success)
            - source_file: Original file path
            - markdown_file: Path to generated .md file (if created)
            - error: Error message (on failure)
        """
        path = Path(file_path)

        if not path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }

        if not path.is_file():
            return {
                "success": False,
                "error": f"Path is not a file: {file_path}"
            }

        # Validate file extension
        valid_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
        if path.suffix.lower() not in valid_extensions:
            return {
                "success": False,
                "error": f"Unsupported file type: {path.suffix}. "
                        f"Supported: {', '.join(valid_extensions)}"
            }

        try:
            # Build command
            cmd = ["docling", "--image-export-mode", "placeholder", str(path)]
            if output_dir:
                cmd.extend(["--output", output_dir])

            # Run docling CLI
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8").strip()
                return {
                    "success": False,
                    "error": f"Docling failed (exit code {process.returncode}): {error_msg}"
                }

            # Docling creates .md file next to the PDF or in output_dir
            if output_dir:
                md_path = Path(output_dir) / (path.stem + ".md")
            else:
                # Fallback: use current directory
                current_dir = Path.cwd()
                md_path = current_dir / (path.stem + ".md")
                print(f"Using fallback directory: {md_path}")

            if md_path.exists():
                markdown_content = md_path.read_text(encoding="utf-8")

                # this markdown may contain images. these image be removed before returning the markdown
                markdown_content = re.sub(r'!\[.*?\]\(.*?\)', '', markdown_content)
                
                return {
                    "success": True,
                    "markdown": markdown_content,
                    "source_file": str(path),
                    "markdown_file": str(md_path)
                }
            else:
                # Fallback: return stdout if no .md file created
                stdout_text = stdout.decode("utf-8").strip()
                if stdout_text:
                    return {
                        "success": True,
                        "markdown": stdout_text,
                        "source_file": str(path)
                    }
                else:
                    return {
                        "success": False,
                        "error": "Docling completed but no output was generated"
                    }

        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    "Docling CLI not found. Ensure 'docling' is installed and in PATH. "
                    "Install with: pip install docling"
                )
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error during extraction: {str(e)}",
                "error_type": type(e).__name__
            }
