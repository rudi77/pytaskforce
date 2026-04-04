"""Tests for the DocxTool."""

import pytest
from pathlib import Path

from taskforce.infrastructure.tools.native.docx_tool import DocxTool


@pytest.fixture
def tool():
    return DocxTool()


@pytest.fixture
def docx_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.docx")


async def test_create_empty_document(tool: DocxTool, docx_path: str):
    result = await tool.execute(action="create", path=docx_path)
    assert result["success"]
    assert Path(docx_path).exists()


async def test_create_with_content(tool: DocxTool, docx_path: str):
    result = await tool.execute(action="create", path=docx_path, content="Hello World")
    assert result["success"]

    result = await tool.execute(action="read", path=docx_path)
    assert result["success"]
    assert "Hello World" in result["text"]


async def test_read_document(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="Test content")
    result = await tool.execute(action="read", path=docx_path)
    assert result["success"]
    assert "Test content" in result["text"]
    assert result["paragraph_count"] > 0


async def test_add_paragraph(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="First")
    result = await tool.execute(action="add_paragraph", path=docx_path, content="Second")
    assert result["success"]

    result = await tool.execute(action="read", path=docx_path)
    assert "First" in result["text"]
    assert "Second" in result["text"]


async def test_add_paragraph_requires_content(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="Hello")
    result = await tool.execute(action="add_paragraph", path=docx_path)
    assert not result["success"]
    assert "content" in result["error"].lower()


async def test_replace_text(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="Hello World")
    result = await tool.execute(
        action="replace_text", path=docx_path, find="World", replace="Python"
    )
    assert result["success"]
    assert result["replacements"] >= 1

    result = await tool.execute(action="read", path=docx_path)
    assert "Python" in result["text"]


async def test_replace_text_requires_find(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="Hello")
    result = await tool.execute(action="replace_text", path=docx_path, replace="X")
    assert not result["success"]


async def test_add_table(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="Before table")
    result = await tool.execute(
        action="add_table",
        path=docx_path,
        headers=["Name", "Age"],
        rows=[["Alice", "30"], ["Bob", "25"]],
    )
    assert result["success"]
    assert result["rows"] == 3  # 1 header + 2 data
    assert result["cols"] == 2

    result = await tool.execute(action="read", path=docx_path)
    assert result["table_count"] == 1


async def test_info(tool: DocxTool, docx_path: str):
    await tool.execute(action="create", path=docx_path, content="Hello", style="Heading 1")
    result = await tool.execute(action="info", path=docx_path)
    assert result["success"]
    assert result["paragraph_count"] >= 1


async def test_unknown_action(tool: DocxTool, docx_path: str):
    result = await tool.execute(action="delete", path=docx_path)
    assert not result["success"]
    assert "Unknown action" in result["error"]
