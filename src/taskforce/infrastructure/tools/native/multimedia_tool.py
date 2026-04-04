"""
Multimedia Tool - Read Images, PDFs, and Other Media Files

Provides capabilities to read and extract information from multimedia files:
- Images: PNG, JPG, GIF, BMP, WEBP - Returns base64 encoded data for LLM vision
- PDFs: Extracts text content page by page
- Other documents: Basic metadata and content extraction
"""

import base64
import importlib.util
import mimetypes
from pathlib import Path
from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class MultimediaTool(ToolProtocol):
    """
    Read and extract content from multimedia files.

    Supports:
    - Images (PNG, JPG, GIF, BMP, WEBP): Returns base64 encoded data for vision models
    - PDFs: Extracts text content page by page
    - Jupyter notebooks (.ipynb): Returns cell contents with outputs

    This tool allows agents to analyze images, read PDF documents, and process
    other multimedia content similar to Claude Code's multimodal capabilities.
    """

    # Supported image extensions
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"}

    # Supported document extensions
    DOCUMENT_EXTENSIONS = {".pdf", ".ipynb"}

    @property
    def name(self) -> str:
        return "multimedia"

    @property
    def description(self) -> str:
        return (
            "Read multimedia files (images, PDFs, notebooks). "
            "For images: returns base64 encoded data for vision analysis. "
            "For PDFs: extracts text content. "
            "For notebooks: returns cells with outputs."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the multimedia file to read",
                },
                "page_range": {
                    "type": "string",
                    "description": "For PDFs: page range to extract (e.g., '1-5', '1,3,5'). Default: all pages.",
                },
                "max_pages": {
                    "type": "integer",
                    "description": "For PDFs: maximum number of pages to extract (default: 50)",
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Include file metadata (default: true)",
                },
            },
            "required": ["file_path"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        return f"Tool: {self.name}\nOperation: Read multimedia file\nPath: {file_path}"

    async def execute(
        self,
        file_path: str,
        page_range: str | None = None,
        max_pages: int = 50,
        include_metadata: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Read and extract content from multimedia files.

        Args:
            file_path: Path to the multimedia file
            page_range: For PDFs, page range to extract
            max_pages: Maximum pages to extract from PDFs
            include_metadata: Include file metadata

        Returns:
            Dictionary with extracted content based on file type
        """
        try:
            path = Path(file_path)

            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            if not path.is_file():
                return {"success": False, "error": f"Path is not a file: {file_path}"}

            suffix = path.suffix.lower()

            # Get basic metadata
            metadata = {}
            if include_metadata:
                stat = path.stat()
                metadata = {
                    "file_name": path.name,
                    "file_size": stat.st_size,
                    "file_type": mimetypes.guess_type(str(path))[0] or "unknown",
                    "extension": suffix,
                }

            # Handle images
            if suffix in self.IMAGE_EXTENSIONS:
                return await self._read_image(path, metadata)

            # Handle PDFs
            if suffix == ".pdf":
                return await self._read_pdf(path, page_range, max_pages, metadata)

            # Handle Jupyter notebooks
            if suffix == ".ipynb":
                return await self._read_notebook(path, metadata)

            # Unsupported file type
            return {
                "success": False,
                "error": f"Unsupported file type: {suffix}. Supported: {', '.join(self.IMAGE_EXTENSIONS | self.DOCUMENT_EXTENSIONS)}",
                "metadata": metadata,
            }

        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"file_path": file_path},
            )
            return tool_error_payload(tool_error)

    async def _read_image(self, path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """Read an image file and return base64 encoded data."""
        try:
            # Read binary data
            image_data = path.read_bytes()
            base64_data = base64.b64encode(image_data).decode("utf-8")

            # Determine MIME type
            mime_type = mimetypes.guess_type(str(path))[0] or "image/png"

            # Try to get image dimensions if PIL is available
            dimensions = None
            try:
                from PIL import Image
                with Image.open(path) as img:
                    dimensions = {"width": img.width, "height": img.height, "mode": img.mode}
            except ImportError:
                pass  # PIL not available
            except Exception:
                pass  # Could not read image with PIL

            result = {
                "success": True,
                "type": "image",
                "mime_type": mime_type,
                "base64_data": base64_data,
                "data_url": f"data:{mime_type};base64,{base64_data}",
                "metadata": metadata,
            }

            if dimensions:
                result["dimensions"] = dimensions

            return result

        except Exception as e:
            return {"success": False, "error": f"Failed to read image: {e}", "metadata": metadata}

    async def _read_pdf(
        self,
        path: Path,
        page_range: str | None,
        max_pages: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Read a PDF file and extract text content."""
        try:
            # Try PyPDF2 first (most common)
            if importlib.util.find_spec("PyPDF2") is not None:
                return await self._read_pdf_pypdf2(path, page_range, max_pages, metadata)

            # Try pdfplumber as fallback
            if importlib.util.find_spec("pdfplumber") is not None:
                return await self._read_pdf_pdfplumber(path, page_range, max_pages, metadata)

            # No PDF library available
            return {
                "success": False,
                "error": "No PDF library available. Install PyPDF2 or pdfplumber: pip install PyPDF2",
                "metadata": metadata,
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to read PDF: {e}", "metadata": metadata}

    async def _read_pdf_pypdf2(
        self,
        path: Path,
        page_range: str | None,
        max_pages: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Read PDF using PyPDF2."""
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        total_pages = len(reader.pages)

        # Parse page range
        pages_to_read = self._parse_page_range(page_range, total_pages, max_pages)

        # Extract text from pages
        pages_content = []
        for page_num in pages_to_read:
            if page_num <= total_pages:
                page = reader.pages[page_num - 1]  # 0-indexed
                text = page.extract_text() or ""
                pages_content.append({
                    "page_number": page_num,
                    "text": text,
                    "char_count": len(text),
                })

        # Get PDF metadata
        pdf_metadata = {}
        if reader.metadata:
            pdf_metadata = {
                "title": reader.metadata.get("/Title", ""),
                "author": reader.metadata.get("/Author", ""),
                "subject": reader.metadata.get("/Subject", ""),
                "creator": reader.metadata.get("/Creator", ""),
            }

        return {
            "success": True,
            "type": "pdf",
            "total_pages": total_pages,
            "pages_extracted": len(pages_content),
            "pages": pages_content,
            "pdf_metadata": pdf_metadata,
            "metadata": metadata,
        }

    async def _read_pdf_pdfplumber(
        self,
        path: Path,
        page_range: str | None,
        max_pages: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Read PDF using pdfplumber."""
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            total_pages = len(pdf.pages)
            pages_to_read = self._parse_page_range(page_range, total_pages, max_pages)

            pages_content = []
            for page_num in pages_to_read:
                if page_num <= total_pages:
                    page = pdf.pages[page_num - 1]  # 0-indexed
                    text = page.extract_text() or ""
                    pages_content.append({
                        "page_number": page_num,
                        "text": text,
                        "char_count": len(text),
                    })

            pdf_metadata = pdf.metadata or {}

            return {
                "success": True,
                "type": "pdf",
                "total_pages": total_pages,
                "pages_extracted": len(pages_content),
                "pages": pages_content,
                "pdf_metadata": pdf_metadata,
                "metadata": metadata,
            }

    async def _read_notebook(self, path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """Read a Jupyter notebook and extract cells."""
        import json

        try:
            content = path.read_text(encoding="utf-8")
            notebook = json.loads(content)

            cells = []
            for idx, cell in enumerate(notebook.get("cells", [])):
                cell_type = cell.get("cell_type", "unknown")
                source = cell.get("source", [])
                if isinstance(source, list):
                    source = "".join(source)

                cell_data = {
                    "index": idx,
                    "cell_type": cell_type,
                    "source": source,
                }

                # Include outputs for code cells
                if cell_type == "code":
                    outputs = cell.get("outputs", [])
                    output_texts = []
                    for output in outputs:
                        if "text" in output:
                            text = output["text"]
                            if isinstance(text, list):
                                text = "".join(text)
                            output_texts.append(text)
                        elif "data" in output:
                            data = output["data"]
                            if "text/plain" in data:
                                text = data["text/plain"]
                                if isinstance(text, list):
                                    text = "".join(text)
                                output_texts.append(text)
                    if output_texts:
                        cell_data["outputs"] = output_texts

                cells.append(cell_data)

            # Get notebook metadata
            nb_metadata = notebook.get("metadata", {})
            kernel_info = nb_metadata.get("kernelspec", {})

            return {
                "success": True,
                "type": "notebook",
                "cell_count": len(cells),
                "cells": cells,
                "kernel": kernel_info.get("display_name", "unknown"),
                "language": kernel_info.get("language", "unknown"),
                "metadata": metadata,
            }

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid notebook format: {e}", "metadata": metadata}

    def _parse_page_range(self, page_range: str | None, total_pages: int, max_pages: int) -> list[int]:
        """Parse page range string into list of page numbers."""
        if not page_range:
            # Return all pages up to max_pages
            return list(range(1, min(total_pages + 1, max_pages + 1)))

        pages: set[int] = set()
        parts = page_range.replace(" ", "").split(",")

        for part in parts:
            if "-" in part:
                # Range like "1-5"
                start_end = part.split("-")
                if len(start_end) == 2:
                    try:
                        start = int(start_end[0])
                        end = int(start_end[1])
                        pages.update(range(start, min(end + 1, total_pages + 1)))
                    except ValueError:
                        continue
            else:
                # Single page like "3"
                try:
                    pages.add(int(part))
                except ValueError:
                    continue

        # Filter to valid pages and limit
        valid_pages = sorted([p for p in pages if 1 <= p <= total_pages])
        return valid_pages[:max_pages]

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "file_path" not in kwargs:
            return False, "Missing required parameter: file_path"
        if not isinstance(kwargs["file_path"], str):
            return False, "Parameter 'file_path' must be a string"
        return True, None
