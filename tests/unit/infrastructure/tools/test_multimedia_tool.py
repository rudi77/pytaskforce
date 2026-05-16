"""Tests for MultimediaTool — image read produces ``attachments`` shape."""

from __future__ import annotations

import base64
from pathlib import Path

from taskforce.infrastructure.tools.native.multimedia_tool import MultimediaTool

# Smallest valid PNG: 1x1 transparent pixel.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


async def test_image_returns_attachments_for_multimodal_pipeline(tmp_path: Path) -> None:
    """Reading an image must yield the attachments convention so the
    tool-result message factory can inject a multimodal user follow-up."""
    img_path = tmp_path / "tiny.png"
    img_path.write_bytes(_PNG_1X1)

    tool = MultimediaTool()
    result = await tool.execute(file_path=str(img_path))

    assert result["success"] is True
    assert result["type"] == "image"
    # Short human-readable summary for the tool message text.
    assert "tiny.png" in result["output"]
    assert "passed to llm" in result["output"].lower()

    # Attachments: framework-wide convention.
    assert "attachments" in result
    atts = result["attachments"]
    assert isinstance(atts, list) and len(atts) == 1
    att = atts[0]
    assert att["type"] == "image"
    assert att["mime_type"] == "image/png"
    assert att["data_url"].startswith("data:image/png;base64,")
    assert att["file_name"] == "tiny.png"
    assert att["file_path"] == str(img_path)


async def test_image_missing_file_returns_error(tmp_path: Path) -> None:
    tool = MultimediaTool()
    result = await tool.execute(file_path=str(tmp_path / "does-not-exist.png"))
    assert result["success"] is False
    assert "not found" in result["error"].lower()
