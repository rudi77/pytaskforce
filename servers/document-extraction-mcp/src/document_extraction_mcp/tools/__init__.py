"""Document extraction tools.

Important: Do NOT import tool modules at package import time.

This package is imported as part of submodule imports like
`document_extraction_mcp.tools.ocr`. Eager imports here would load heavy ML
dependencies (PaddleOCR/torch/transformers/litellm) during MCP server operation
and can cause long stalls or deadlocks.
"""

__all__ = [
    "ocr_extract",
    "layout_detect",
    "reading_order",
    "crop_region",
    "analyze_table",
    "analyze_chart",
]
