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
import os
import subprocess
import sys
import time
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

# Debug log file for diagnosing MCP tool hangs (safe: file I/O only).
_DEBUG_LOG_PATH = Path(__file__).with_name("mcp_tool_debug.log")


def _debug_log(message: str) -> None:
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8", errors="ignore") as f:
            f.write(message + "\n")
    except Exception:
        # Never let debugging interfere with tool execution
        pass


def _run_tool_subprocess(
    tool_module: str,
    tool_func: str,
    args: list[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run a tool function in a fresh subprocess.

    This avoids rare but real deadlocks when initializing heavy ML stacks inside
    a long-running stdio MCP server process on Windows.
    """
    code = (
        "import json, sys\n"
        f"from {tool_module} import {tool_func}\n"
        f"result = {tool_func}(*sys.argv[1:])\n"
        "print(json.dumps(result))\n"
    )
    env = os.environ.copy()
    # Reduce noisy progress output and avoid network checks where possible.
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("TQDM_DISABLE", "1")
    env.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
            timeout=timeout_seconds,
            close_fds=True,
        )
    except subprocess.TimeoutExpired:
        return {
            "error": (
                "Tool subprocess timed out after "
                f"{timeout_seconds:.0f}s"
            )
        }

    stdout = (proc.stdout or "").strip()
    stderr = ""

    if proc.returncode != 0:
        return {
            "error": "Tool subprocess failed",
            "returncode": proc.returncode,
            "stderr": stderr[:2000],
            "stdout": stdout[:2000],
        }

    try:
        return json.loads(stdout)
    except Exception:
        return {
            "error": "Tool subprocess returned non-JSON output",
            "stdout": stdout[:2000],
            "stderr": stderr[:2000],
        }

# Note: We intentionally avoid caching heavy ML engines in-process here.
# Tools are executed in fresh subprocesses via `_run_tool_subprocess` to avoid
# Windows deadlocks and stderr backpressure issues in long-lived stdio servers.


# Tool definitions
TOOLS = [
    Tool(
        name="ocr_extract",
        description=(
            "Extract text from a document image using OCR. Returns text regions "
            "with bounding boxes and confidence scores."
        ),
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
        description=(
            "Detect document layout regions (text, table, chart, figure, title). "
            "Returns region types with bounding boxes."
        ),
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
    image_path = arguments.get("image_path")
    if not image_path:
        return {"error": "Missing required parameter: image_path"}

    start_time = time.time()
    logger.info("tool_started", tool="ocr_extract", image_path=image_path)
    _debug_log(f"{time.time():.3f} ocr_extract START path={image_path}")
    
    try:
        # Run OCR in a fresh subprocess to avoid Windows deadlocks in long-lived
        # stdio MCP server processes.
        result = _run_tool_subprocess(
            tool_module="document_extraction_mcp.tools.ocr",
            tool_func="ocr_extract",
            args=[image_path],
            timeout_seconds=300.0,
        )
        duration = time.time() - start_time
        logger.info(
            "tool_finished",
            tool="ocr_extract",
            duration_seconds=duration,
            success="error" not in result,
        )
        _debug_log(
            f"{time.time():.3f} ocr_extract DONE duration={duration:.3f}"
        )
        return result
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(
            "tool_error",
            tool="ocr_extract",
            duration_seconds=duration,
            error=str(e),
        )
        _debug_log(
            f"{time.time():.3f} ocr_extract ERROR duration={duration:.3f}"
        )
        return {"error": f"OCR extraction failed: {str(e)}"}


async def handle_layout_detect(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle layout_detect tool call."""
    image_path = arguments.get("image_path")
    if not image_path:
        return {"error": "Missing required parameter: image_path"}

    start_time = time.time()
    logger.info("tool_started", tool="layout_detect", image_path=image_path)
    
    try:
        # Same approach as OCR: run in subprocess to avoid deadlocks.
        result = _run_tool_subprocess(
            tool_module="document_extraction_mcp.tools.layout",
            tool_func="layout_detect",
            args=[image_path],
            timeout_seconds=300.0,
        )
        duration = time.time() - start_time
        logger.info("tool_finished", tool="layout_detect", duration_seconds=duration, success="error" not in result)
        return result
    except Exception as e:
        duration = time.time() - start_time
        logger.exception("tool_error", tool="layout_detect", duration_seconds=duration, error=str(e))
        return {"error": f"Layout detection failed: {str(e)}"}


async def handle_reading_order(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle reading_order tool call."""
    regions = arguments.get("regions")
    if not regions:
        return {"error": "Missing required parameter: regions"}

    image_width = arguments.get("image_width")
    image_height = arguments.get("image_height")

    start_time = time.time()
    logger.info("tool_started", tool="reading_order", region_count=len(regions) if regions else 0)
    
    try:
        # Run reading_order in subprocess to avoid torch/transformers deadlocks
        # and avoid large stderr output blocking the MCP client.
        result = _run_tool_subprocess(
            tool_module="document_extraction_mcp.tools.reading_order",
            tool_func="reading_order_from_json",
            args=[
                json.dumps(regions),
                json.dumps(image_width),
                json.dumps(image_height),
            ],
            timeout_seconds=600.0,
        )
        duration = time.time() - start_time
        logger.info("tool_finished", tool="reading_order", duration_seconds=duration, success="error" not in result)
        return result
    except Exception as e:
        duration = time.time() - start_time
        logger.exception("tool_error", tool="reading_order", duration_seconds=duration, error=str(e))
        return {"error": f"Reading order detection failed: {str(e)}"}


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
