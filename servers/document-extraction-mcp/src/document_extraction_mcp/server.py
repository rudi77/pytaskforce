"""Document Extraction MCP Server.

Provides tools for document understanding:
- ocr_extract: Extract text with bounding boxes using PaddleOCR
- layout_detect: Detect document regions (tables, charts, text)
- reading_order: Sort OCR regions into reading sequence
- crop_region: Crop a region and return base64 image
- analyze_table: Extract table structure via VLM
- analyze_chart: Extract chart data via VLM
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)

# Create MCP server
server = Server("document-extraction-mcp")

# Lazy-loaded engines (initialized on first use)
_ocr_engine = None
_layout_engine = None
_layout_model = None


def get_ocr_engine():
    """Get or initialize PaddleOCR engine."""
    global _ocr_engine
    if _ocr_engine is None:
        logger.info("initializing_paddleocr")
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(lang="en", show_log=False)
        logger.info("paddleocr_initialized")
    return _ocr_engine


def get_layout_engine():
    """Get or initialize PaddleOCR LayoutDetection engine."""
    global _layout_engine
    if _layout_engine is None:
        logger.info("initializing_layout_detection")
        from paddleocr import LayoutDetection

        _layout_engine = LayoutDetection()
        logger.info("layout_detection_initialized")
    return _layout_engine


def get_layout_model():
    """Get or initialize LayoutReader model for reading order."""
    global _layout_model
    if _layout_model is None:
        logger.info("initializing_layoutreader")
        from transformers import LayoutLMv3ForTokenClassification

        model_slug = "hantian/layoutreader"
        _layout_model = LayoutLMv3ForTokenClassification.from_pretrained(model_slug)
        logger.info("layoutreader_initialized")
    return _layout_model


# Tool definitions
TOOLS = [
    Tool(
        name="ocr_extract",
        description="Extract text from a document image using OCR. Returns text regions with bounding boxes and confidence scores.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the input image file (PNG, JPG, PDF page)",
                }
            },
            "required": ["image_path"],
        },
    ),
    Tool(
        name="layout_detect",
        description="Detect document layout regions (text, table, chart, figure, title). Returns region types with bounding boxes.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the input image file",
                }
            },
            "required": ["image_path"],
        },
    ),
    Tool(
        name="reading_order",
        description="Determine the reading order of OCR regions using LayoutLMv3. Input is OCR regions with bounding boxes.",
        inputSchema={
            "type": "object",
            "properties": {
                "regions": {
                    "type": "array",
                    "description": "OCR regions with bbox data",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "bbox": {
                                "type": "array",
                                "description": "Bounding box as [x1, y1, x2, y2]",
                                "items": {"type": "number"},
                            },
                        },
                        "required": ["text", "bbox"],
                    },
                },
                "image_width": {
                    "type": "number",
                    "description": "Width of the source image in pixels",
                },
                "image_height": {
                    "type": "number",
                    "description": "Height of the source image in pixels",
                },
            },
            "required": ["regions"],
        },
    ),
    Tool(
        name="crop_region",
        description="Crop a region from an image and return it as base64-encoded PNG.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the input image file",
                },
                "bbox": {
                    "type": "array",
                    "description": "Bounding box as [x1, y1, x2, y2]",
                    "items": {"type": "number"},
                },
                "padding": {
                    "type": "integer",
                    "description": "Padding around the region in pixels (default: 10)",
                    "default": 10,
                },
            },
            "required": ["image_path", "bbox"],
        },
    ),
    Tool(
        name="analyze_table",
        description="Analyze a table image using a Vision-Language Model. Returns structured table data with headers and rows.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image of the table",
                },
                "image_path": {
                    "type": "string",
                    "description": "Alternative: Path to the table image file",
                },
            },
        },
    ),
    Tool(
        name="analyze_chart",
        description="Analyze a chart/figure image using a Vision-Language Model. Returns chart type, axes, data points, and trends.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image of the chart",
                },
                "image_path": {
                    "type": "string",
                    "description": "Alternative: Path to the chart image file",
                },
            },
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return list of available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Execute a tool and return results."""
    logger.info("tool_called", tool=name, arguments=arguments)

    try:
        if name == "ocr_extract":
            result = await handle_ocr_extract(arguments)
        elif name == "layout_detect":
            result = await handle_layout_detect(arguments)
        elif name == "reading_order":
            result = await handle_reading_order(arguments)
        elif name == "crop_region":
            result = await handle_crop_region(arguments)
        elif name == "analyze_table":
            result = await handle_analyze_table(arguments)
        elif name == "analyze_chart":
            result = await handle_analyze_chart(arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        logger.info("tool_completed", tool=name, success="error" not in result)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])

    except Exception as e:
        logger.exception("tool_error", tool=name, error=str(e))
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": str(e)}))]
        )


async def handle_ocr_extract(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle ocr_extract tool call."""
    from document_extraction_mcp.tools.ocr import ocr_extract

    image_path = arguments.get("image_path")
    if not image_path:
        return {"error": "Missing required parameter: image_path"}

    return await asyncio.to_thread(ocr_extract, image_path)


async def handle_layout_detect(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle layout_detect tool call."""
    from document_extraction_mcp.tools.layout import layout_detect

    image_path = arguments.get("image_path")
    if not image_path:
        return {"error": "Missing required parameter: image_path"}

    return await asyncio.to_thread(layout_detect, image_path)


async def handle_reading_order(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle reading_order tool call."""
    from document_extraction_mcp.tools.reading_order import reading_order

    regions = arguments.get("regions")
    if not regions:
        return {"error": "Missing required parameter: regions"}

    image_width = arguments.get("image_width")
    image_height = arguments.get("image_height")

    return await asyncio.to_thread(reading_order, regions, image_width, image_height)


async def handle_crop_region(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle crop_region tool call."""
    from document_extraction_mcp.tools.crop import crop_region

    image_path = arguments.get("image_path")
    bbox = arguments.get("bbox")

    if not image_path:
        return {"error": "Missing required parameter: image_path"}
    if not bbox:
        return {"error": "Missing required parameter: bbox"}

    padding = arguments.get("padding", 10)

    return await asyncio.to_thread(crop_region, image_path, bbox, padding)


async def handle_analyze_table(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle analyze_table tool call."""
    from document_extraction_mcp.tools.vlm import analyze_table

    image_base64 = arguments.get("image_base64")
    image_path = arguments.get("image_path")

    if not image_base64 and not image_path:
        return {"error": "Must provide either image_base64 or image_path"}

    return await analyze_table(image_base64=image_base64, image_path=image_path)


async def handle_analyze_chart(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle analyze_chart tool call."""
    from document_extraction_mcp.tools.vlm import analyze_chart

    image_base64 = arguments.get("image_base64")
    image_path = arguments.get("image_path")

    if not image_base64 and not image_path:
        return {"error": "Must provide either image_base64 or image_path"}

    return await analyze_chart(image_base64=image_base64, image_path=image_path)


async def run_server():
    """Run the MCP server."""
    logger.info("starting_document_extraction_mcp_server")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
