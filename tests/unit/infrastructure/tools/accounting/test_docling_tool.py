"""
Tests for DoclingTool.

Tests PDF/image to Markdown extraction via Docling CLI.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from taskforce.infrastructure.tools.native.accounting.docling_tool import (
    DoclingTool,
)


@pytest.fixture
def docling_tool() -> DoclingTool:
    """Create DoclingTool instance."""
    return DoclingTool()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a sample PDF file for testing."""
    pdf_path = tmp_path / "invoice.pdf"
    # Create minimal PDF-like content (not a real PDF)
    pdf_path.write_bytes(b"%PDF-1.4\nTest content")
    return pdf_path


class TestDoclingTool:
    """Test suite for DoclingTool."""

    def test_tool_metadata(self, docling_tool: DoclingTool):
        """Test tool metadata properties."""
        assert docling_tool.name == "docling_extract"
        assert "PDF" in docling_tool.description or "Markdown" in docling_tool.description
        assert docling_tool.requires_approval is False

    def test_parameters_schema(self, docling_tool: DoclingTool):
        """Test parameter schema structure."""
        schema = docling_tool.parameters_schema
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "file_path" in schema["required"]

    def test_validate_params_missing_file_path(self, docling_tool: DoclingTool):
        """Test validation fails without file_path."""
        valid, error = docling_tool.validate_params()
        assert valid is False
        assert "file_path" in error

    def test_validate_params_invalid_type(self, docling_tool: DoclingTool):
        """Test validation fails with non-string file_path."""
        valid, error = docling_tool.validate_params(file_path=123)
        assert valid is False
        assert "string" in error

    def test_validate_params_empty_string(self, docling_tool: DoclingTool):
        """Test validation fails with empty file_path."""
        valid, error = docling_tool.validate_params(file_path="")
        assert valid is False
        assert "empty" in error

    def test_validate_params_valid(self, docling_tool: DoclingTool):
        """Test validation passes with valid file_path."""
        valid, error = docling_tool.validate_params(file_path="/path/to/file.pdf")
        assert valid is True
        assert error is None

    def test_get_approval_preview(self, docling_tool: DoclingTool):
        """Test approval preview generation."""
        preview = docling_tool.get_approval_preview(file_path="/path/to/invoice.pdf")
        assert "docling_extract" in preview
        assert "/path/to/invoice.pdf" in preview

    @pytest.mark.asyncio
    async def test_file_not_found(self, docling_tool: DoclingTool):
        """Test error when file does not exist."""
        result = await docling_tool.execute(file_path="/nonexistent/file.pdf")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unsupported_file_type(
        self, docling_tool: DoclingTool, tmp_path: Path
    ):
        """Test error for unsupported file types."""
        txt_file = tmp_path / "document.txt"
        txt_file.write_text("Some text")

        result = await docling_tool.execute(file_path=str(txt_file))

        assert result["success"] is False
        assert "Unsupported" in result["error"]

    @pytest.mark.asyncio
    async def test_supported_file_extensions(
        self, docling_tool: DoclingTool, tmp_path: Path
    ):
        """Test that supported extensions are accepted."""
        supported = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]

        for ext in supported:
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"dummy content")

            # File exists validation should pass (CLI failure expected)
            # We're just testing extension validation
            result = await docling_tool.execute(file_path=str(test_file))
            # Should not fail due to unsupported type
            if not result["success"]:
                assert "Unsupported" not in result.get("error", "")

    @pytest.mark.asyncio
    async def test_directory_path(
        self, docling_tool: DoclingTool, tmp_path: Path
    ):
        """Test error when path is a directory."""
        result = await docling_tool.execute(file_path=str(tmp_path))

        assert result["success"] is False
        assert "not a file" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_docling_cli_not_found(
        self, docling_tool: DoclingTool, sample_pdf: Path
    ):
        """Test error when docling CLI is not installed."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError()

            result = await docling_tool.execute(file_path=str(sample_pdf))

            assert result["success"] is False
            assert "not found" in result["error"].lower()
            assert "docling" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_docling_cli_failure(
        self, docling_tool: DoclingTool, sample_pdf: Path
    ):
        """Test handling of docling CLI failure."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error message")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await docling_tool.execute(file_path=str(sample_pdf))

            assert result["success"] is False
            assert "failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_successful_extraction_with_md_file(
        self, docling_tool: DoclingTool, sample_pdf: Path
    ):
        """Test successful extraction when .md file is created."""
        # Create corresponding .md file
        md_file = sample_pdf.with_suffix(".md")
        md_content = "# Invoice\n\nExtracted content here"
        md_file.write_text(md_content, encoding="utf-8")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Success", b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await docling_tool.execute(file_path=str(sample_pdf))

            assert result["success"] is True
            assert result["markdown"] == md_content
            assert result["source_file"] == str(sample_pdf)
            assert result["markdown_file"] == str(md_file)

    @pytest.mark.asyncio
    async def test_successful_extraction_stdout(
        self, docling_tool: DoclingTool, sample_pdf: Path
    ):
        """Test successful extraction from stdout when no .md file."""
        stdout_content = "# Extracted Content\nFrom stdout"

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (stdout_content.encode(), b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await docling_tool.execute(file_path=str(sample_pdf))

            assert result["success"] is True
            assert result["markdown"] == stdout_content
            assert result["source_file"] == str(sample_pdf)

    @pytest.mark.asyncio
    async def test_custom_output_directory(
        self, docling_tool: DoclingTool, sample_pdf: Path, tmp_path: Path
    ):
        """Test extraction with custom output directory."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create expected output file
        md_file = output_dir / f"{sample_pdf.stem}.md"
        md_file.write_text("# Output content", encoding="utf-8")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            result = await docling_tool.execute(
                file_path=str(sample_pdf),
                output_dir=str(output_dir)
            )

            # Verify --output flag was passed
            call_args = mock_exec.call_args[0]
            assert "--output" in call_args
            assert str(output_dir) in call_args

    @pytest.mark.asyncio
    async def test_empty_output_handling(
        self, docling_tool: DoclingTool, sample_pdf: Path
    ):
        """Test handling when docling produces no output."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await docling_tool.execute(file_path=str(sample_pdf))

            assert result["success"] is False
            assert "no output" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_exception_handling(
        self, docling_tool: DoclingTool, sample_pdf: Path
    ):
        """Test handling of unexpected exceptions."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = RuntimeError("Unexpected error")

            result = await docling_tool.execute(file_path=str(sample_pdf))

            assert result["success"] is False
            assert "error" in result
            assert result.get("error_type") == "RuntimeError"
