"""Document extraction tools.

NOTE: The actual tool implementations are provided by the MCP server
at servers/document-extraction-mcp/. The stub classes in this module
are kept for reference but not exported.

Tools provided by MCP server:
- ocr_extract: Extract text with bounding boxes (PaddleOCR)
- layout_detect: Detect document regions (PaddleOCR LayoutDetection)
- reading_order: Sort text into reading sequence (LayoutLMv3)
- crop_region: Crop region, return base64 image (Pillow)
- analyze_table: Extract table structure (VLM)
- analyze_chart: Extract chart data (VLM)
"""

# No tools exported - all tools come from MCP server
__all__: list[str] = []
