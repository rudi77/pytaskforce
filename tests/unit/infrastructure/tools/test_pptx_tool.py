"""Tests for the PptxTool."""

import pytest
from pathlib import Path

from taskforce.infrastructure.tools.native.pptx_tool import PptxTool


@pytest.fixture
def tool():
    return PptxTool()


@pytest.fixture
def pptx_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.pptx")


async def test_create_empty_presentation(tool: PptxTool, pptx_path: str):
    result = await tool.execute(action="create", path=pptx_path)
    assert result["success"]
    assert Path(pptx_path).exists()


async def test_create_with_title(tool: PptxTool, pptx_path: str):
    result = await tool.execute(
        action="create", path=pptx_path, title="My Presentation", content="Subtitle"
    )
    assert result["success"]

    result = await tool.execute(action="read", path=pptx_path)
    assert result["success"]
    assert "My Presentation" in result["text"]


async def test_read_presentation(tool: PptxTool, pptx_path: str):
    await tool.execute(action="create", path=pptx_path, title="Test Slide")
    result = await tool.execute(action="read", path=pptx_path)
    assert result["success"]
    assert result["slide_count"] >= 1
    assert "Test Slide" in result["text"]


async def test_add_slide(tool: PptxTool, pptx_path: str):
    await tool.execute(action="create", path=pptx_path, title="Slide 1")
    result = await tool.execute(
        action="add_slide", path=pptx_path, title="Slide 2", content="Bullet points"
    )
    assert result["success"]
    assert result["slide_number"] == 2

    result = await tool.execute(action="read", path=pptx_path)
    assert result["slide_count"] == 2


async def test_replace_text(tool: PptxTool, pptx_path: str):
    await tool.execute(action="create", path=pptx_path, title="Hello World")
    result = await tool.execute(
        action="replace_text", path=pptx_path, find="World", replace="Python"
    )
    assert result["success"]
    assert result["replacements"] >= 1

    result = await tool.execute(action="read", path=pptx_path)
    assert "Python" in result["text"]


async def test_replace_text_requires_find(tool: PptxTool, pptx_path: str):
    await tool.execute(action="create", path=pptx_path, title="Hello")
    result = await tool.execute(action="replace_text", path=pptx_path, replace="X")
    assert not result["success"]


async def test_info(tool: PptxTool, pptx_path: str):
    await tool.execute(action="create", path=pptx_path, title="Info Test")
    result = await tool.execute(action="info", path=pptx_path)
    assert result["success"]
    assert result["slide_count"] >= 1
    assert "slides" in result


async def test_unknown_action(tool: PptxTool, pptx_path: str):
    result = await tool.execute(action="delete", path=pptx_path)
    assert not result["success"]
    assert "Unknown action" in result["error"]
