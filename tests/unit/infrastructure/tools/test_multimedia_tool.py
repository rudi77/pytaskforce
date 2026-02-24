"""Unit tests for MultimediaTool.

Tests multimedia file reading: images, PDFs, notebooks.
"""

import json

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.multimedia_tool import MultimediaTool


class TestMultimediaToolMetadata:
    """Test MultimediaTool metadata properties."""

    @pytest.fixture
    def tool(self) -> MultimediaTool:
        return MultimediaTool()

    def test_name(self, tool: MultimediaTool) -> None:
        assert tool.name == "multimedia"

    def test_description(self, tool: MultimediaTool) -> None:
        desc = tool.description.lower()
        assert "image" in desc or "multimedia" in desc

    def test_parameters_schema(self, tool: MultimediaTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "page_range" in schema["properties"]
        assert "max_pages" in schema["properties"]
        assert schema["required"] == ["file_path"]

    def test_requires_approval(self, tool: MultimediaTool) -> None:
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool: MultimediaTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool: MultimediaTool) -> None:
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool: MultimediaTool) -> None:
        preview = tool.get_approval_preview(file_path="/tmp/image.png")
        assert "/tmp/image.png" in preview
        assert tool.name in preview


class TestMultimediaToolValidation:
    """Test MultimediaTool parameter validation."""

    @pytest.fixture
    def tool(self) -> MultimediaTool:
        return MultimediaTool()

    def test_valid_params(self, tool: MultimediaTool) -> None:
        valid, error = tool.validate_params(file_path="/tmp/image.png")
        assert valid is True
        assert error is None

    def test_missing_file_path(self, tool: MultimediaTool) -> None:
        valid, error = tool.validate_params()
        assert valid is False
        assert "file_path" in error

    def test_non_string_file_path(self, tool: MultimediaTool) -> None:
        valid, error = tool.validate_params(file_path=123)
        assert valid is False
        assert "string" in error


class TestMultimediaToolImageExecution:
    """Test reading image files."""

    @pytest.fixture
    def tool(self) -> MultimediaTool:
        return MultimediaTool()

    async def test_read_png_image(self, tool: MultimediaTool, tmp_path) -> None:
        # Create a minimal PNG file (1x1 pixel)
        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img_path = tmp_path / "test.png"
        img_path.write_bytes(png_data)

        result = await tool.execute(file_path=str(img_path))
        assert result["success"] is True
        assert result["type"] == "image"
        assert result["mime_type"] == "image/png"
        assert "base64_data" in result
        assert result["base64_data"]  # non-empty
        assert "data:image/png;base64," in result["data_url"]

    async def test_read_image_with_metadata(self, tool: MultimediaTool, tmp_path) -> None:
        img_path = tmp_path / "test.jpg"
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        result = await tool.execute(file_path=str(img_path), include_metadata=True)
        assert result["success"] is True
        assert "metadata" in result
        assert result["metadata"]["file_name"] == "test.jpg"
        assert result["metadata"]["extension"] == ".jpg"

    async def test_read_image_without_metadata(self, tool: MultimediaTool, tmp_path) -> None:
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        result = await tool.execute(file_path=str(img_path), include_metadata=False)
        assert result["success"] is True
        assert result["metadata"] == {}


class TestMultimediaToolNotebookExecution:
    """Test reading Jupyter notebooks."""

    @pytest.fixture
    def tool(self) -> MultimediaTool:
        return MultimediaTool()

    async def test_read_notebook(self, tool: MultimediaTool, tmp_path) -> None:
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Title\n", "Description text"],
                    "metadata": {},
                },
                {
                    "cell_type": "code",
                    "source": ["print('hello')"],
                    "metadata": {},
                    "outputs": [{"text": ["hello\n"]}],
                },
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        nb_path = tmp_path / "test.ipynb"
        nb_path.write_text(json.dumps(notebook), encoding="utf-8")

        result = await tool.execute(file_path=str(nb_path))
        assert result["success"] is True
        assert result["type"] == "notebook"
        assert result["cell_count"] == 2
        assert result["kernel"] == "Python 3"
        assert result["language"] == "python"
        # Check cells
        assert result["cells"][0]["cell_type"] == "markdown"
        assert result["cells"][1]["cell_type"] == "code"
        assert "hello" in result["cells"][1]["outputs"][0]

    async def test_read_invalid_notebook(self, tool: MultimediaTool, tmp_path) -> None:
        nb_path = tmp_path / "bad.ipynb"
        nb_path.write_text("not valid json{{{", encoding="utf-8")

        result = await tool.execute(file_path=str(nb_path))
        assert result["success"] is False
        assert "invalid" in result["error"].lower()


class TestMultimediaToolErrorHandling:
    """Test error handling."""

    @pytest.fixture
    def tool(self) -> MultimediaTool:
        return MultimediaTool()

    async def test_file_not_found(self, tool: MultimediaTool) -> None:
        result = await tool.execute(file_path="/nonexistent/file.png")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_path_is_directory(self, tool: MultimediaTool, tmp_path) -> None:
        result = await tool.execute(file_path=str(tmp_path))
        assert result["success"] is False
        assert "not a file" in result["error"].lower()

    async def test_unsupported_file_type(self, tool: MultimediaTool, tmp_path) -> None:
        txt_path = tmp_path / "test.xyz"
        txt_path.write_text("some content")

        result = await tool.execute(file_path=str(txt_path))
        assert result["success"] is False
        assert "unsupported" in result["error"].lower()


class TestMultimediaToolPageRange:
    """Test PDF page range parsing."""

    @pytest.fixture
    def tool(self) -> MultimediaTool:
        return MultimediaTool()

    def test_no_range_returns_all_up_to_max(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range(None, total_pages=10, max_pages=50)
        assert pages == list(range(1, 11))

    def test_no_range_respects_max_pages(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range(None, total_pages=100, max_pages=5)
        assert pages == [1, 2, 3, 4, 5]

    def test_single_page(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range("3", total_pages=10, max_pages=50)
        assert pages == [3]

    def test_page_range(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range("2-5", total_pages=10, max_pages=50)
        assert pages == [2, 3, 4, 5]

    def test_comma_separated(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range("1,3,5", total_pages=10, max_pages=50)
        assert pages == [1, 3, 5]

    def test_mixed_range_and_single(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range("1-3,7", total_pages=10, max_pages=50)
        assert pages == [1, 2, 3, 7]

    def test_out_of_bounds_filtered(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range("1,50,100", total_pages=10, max_pages=50)
        assert pages == [1]

    def test_invalid_values_skipped(self, tool: MultimediaTool) -> None:
        pages = tool._parse_page_range("abc,2,xyz", total_pages=10, max_pages=50)
        assert pages == [2]
