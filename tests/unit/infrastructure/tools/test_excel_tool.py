"""Tests for the ExcelTool."""

import pytest
from pathlib import Path

from taskforce.infrastructure.tools.native.excel_tool import ExcelTool


@pytest.fixture
def tool():
    return ExcelTool()


@pytest.fixture
def xlsx_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.xlsx")


async def test_create_empty_workbook(tool: ExcelTool, xlsx_path: str):
    result = await tool.execute(action="create", path=xlsx_path)
    assert result["success"]
    assert Path(xlsx_path).exists()


async def test_create_with_headers_and_rows(tool: ExcelTool, xlsx_path: str):
    result = await tool.execute(
        action="create",
        path=xlsx_path,
        headers=["Name", "Age"],
        rows=[["Alice", 30], ["Bob", 25]],
    )
    assert result["success"]

    result = await tool.execute(action="read", path=xlsx_path)
    assert result["success"]
    assert result["row_count"] == 3  # 1 header + 2 data
    assert result["rows"][0] == ["Name", "Age"]
    assert result["rows"][1] == ["Alice", 30]


async def test_read_workbook(tool: ExcelTool, xlsx_path: str):
    await tool.execute(
        action="create", path=xlsx_path, headers=["Col1"], rows=[["val1"], ["val2"]]
    )
    result = await tool.execute(action="read", path=xlsx_path)
    assert result["success"]
    assert result["row_count"] == 3
    assert result["column_count"] == 1


async def test_write_cells(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path)
    result = await tool.execute(
        action="write_cells",
        path=xlsx_path,
        cells={"A1": "Hello", "B1": "World", "A2": 42},
    )
    assert result["success"]
    assert result["cells_written"] == 3

    result = await tool.execute(action="read", path=xlsx_path)
    assert result["rows"][0][0] == "Hello"
    assert result["rows"][0][1] == "World"
    assert result["rows"][1][0] == 42


async def test_write_cells_requires_cells(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path)
    result = await tool.execute(action="write_cells", path=xlsx_path)
    assert not result["success"]


async def test_append_rows(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path, headers=["A", "B"])
    result = await tool.execute(
        action="append_rows", path=xlsx_path, rows=[["x", "y"], ["z", "w"]]
    )
    assert result["success"]
    assert result["rows_appended"] == 2

    result = await tool.execute(action="read", path=xlsx_path)
    assert result["row_count"] == 3  # 1 header + 2 appended


async def test_append_rows_requires_rows(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path)
    result = await tool.execute(action="append_rows", path=xlsx_path)
    assert not result["success"]


async def test_add_sheet(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path)
    result = await tool.execute(action="add_sheet", path=xlsx_path, sheet="Sales")
    assert result["success"]
    assert result["sheet"] == "Sales"


async def test_add_sheet_duplicate(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path, sheet="Data")
    result = await tool.execute(action="add_sheet", path=xlsx_path, sheet="Data")
    assert not result["success"]
    assert "already exists" in result["error"]


async def test_info(tool: ExcelTool, xlsx_path: str):
    await tool.execute(
        action="create", path=xlsx_path, headers=["A"], rows=[["1"], ["2"]]
    )
    result = await tool.execute(action="info", path=xlsx_path)
    assert result["success"]
    assert result["sheet_count"] >= 1
    assert "Sheet1" in result["sheet_names"]


async def test_read_specific_sheet(tool: ExcelTool, xlsx_path: str):
    await tool.execute(action="create", path=xlsx_path, headers=["X"])
    await tool.execute(action="add_sheet", path=xlsx_path, sheet="Other")
    await tool.execute(action="write_cells", path=xlsx_path, sheet="Other", cells={"A1": "test"})
    result = await tool.execute(action="read", path=xlsx_path, sheet="Other")
    assert result["success"]
    assert result["sheet"] == "Other"


async def test_unknown_action(tool: ExcelTool, xlsx_path: str):
    result = await tool.execute(action="delete", path=xlsx_path)
    assert not result["success"]
    assert "Unknown action" in result["error"]
