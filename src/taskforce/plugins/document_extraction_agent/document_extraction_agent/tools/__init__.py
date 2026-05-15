"""Document extraction tools.

The classes below are Python-side stubs for tools that are normally
executed by the document-extraction MCP server at
``servers/document-extraction-mcp/``. They are re-exported here so that
plugin discovery (``application/plugin_loader.py``) can resolve the
parent package's ``__all__`` without importing them by attribute on a
package that doesn't expose them — that import failure surfaces as
``plugin.tools_module_import_failed`` and silently drops the plugin's
tool list.

Tool list (mirrors the MCP server):

- ``ocr_extract``    — text + bounding boxes (PaddleOCR)
- ``layout_detect``  — document regions (PaddleOCR LayoutDetection)
- ``reading_order``  — reading-sequence sort (LayoutLMv3)
- ``crop_region``    — region → base64 image (Pillow)
- ``analyze_table``  — table structure (VLM)
- ``analyze_chart``  — chart data points (VLM)
"""

from document_extraction_agent.tools.document_extraction_tools import (
    AnalyzeChartTool,
    AnalyzeTableTool,
    CropRegionTool,
    LayoutDetectTool,
    OcrExtractTool,
    ReadingOrderTool,
)

__all__ = [
    "AnalyzeChartTool",
    "AnalyzeTableTool",
    "CropRegionTool",
    "LayoutDetectTool",
    "OcrExtractTool",
    "ReadingOrderTool",
]
