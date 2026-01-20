"""VLM-based analysis tools for tables and charts."""

import base64
import json
import os
from pathlib import Path
from typing import Any


# Load prompts from files
def _load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / f"{name}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return ""


# Default prompts (used if files not found)
TABLE_ANALYSIS_PROMPT = """You are a Table Extraction specialist.
Extract structured data from this table image.

1. **Identify Structure**:
    - Column headers, row labels, data cells
2. **Extract All Data**:
    - Preserve exact values and alignment
3. **Handle Special Cases**:
    - Merged cells, empty cells (mark as null), multi-line headers

Return a JSON object with this structure:
```json
{
  "table_title": "...",
  "column_headers": ["header1", "header2", ...],
  "rows": [
    {"row_label": "...", "values": [val1, val2, ...]},
    ...
  ],
  "notes": "any footnotes or source info"
}
```
"""

CHART_ANALYSIS_PROMPT = """You are a Chart Analysis specialist.
Analyze this chart/figure image and extract:

1. **Chart Type**: (line, bar, scatter, pie, etc.)
2. **Title**: (if visible)
3. **Axes**: X-axis label, Y-axis label, and tick values
4. **Data Points**: Key values (peaks, troughs, endpoints)
5. **Trends**: Overall pattern description
6. **Legend**: (if present)

Return a JSON object with this structure:
```json
{
  "chart_type": "...",
  "title": "...",
  "x_axis": {"label": "...", "ticks": [...]},
  "y_axis": {"label": "...", "ticks": [...]},
  "key_data_points": [...],
  "trends": "...",
  "legend": [...]
}
```
"""


def _get_prompt(name: str, default: str) -> str:
    """Get prompt from file or use default."""
    loaded = _load_prompt(name)
    return loaded if loaded else default


def _image_to_base64(image_path: str) -> str:
    """Convert an image file to base64 string."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _call_vlm(image_base64: str, prompt: str) -> dict[str, Any]:
    """Call Vision-Language Model with an image and prompt.

    Uses LiteLLM to support multiple providers (OpenAI, Azure, etc.)
    """
    try:
        import litellm

        # Get model from environment or use default
        model = os.environ.get("VLM_MODEL", "gpt-4o-mini")

        # Construct multimodal message
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

        # Call the VLM
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            max_tokens=2000,
            temperature=0,
        )

        content = response.choices[0].message.content

        # Try to parse as JSON
        try:
            # Extract JSON from markdown code block if present
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
                parsed = json.loads(json_str)
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
                parsed = json.loads(json_str)
            else:
                parsed = json.loads(content)
            return {"success": True, "data": parsed, "raw_response": content}
        except json.JSONDecodeError:
            # Return raw text if not valid JSON
            return {"success": True, "data": None, "raw_response": content}

    except ImportError:
        return {"error": "LiteLLM not installed. Run: pip install litellm"}
    except Exception as e:
        return {"error": f"VLM call failed: {str(e)}"}


async def analyze_table(
    image_base64: str | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    """Analyze a table image using a Vision-Language Model.

    Args:
        image_base64: Base64-encoded image of the table
        image_path: Alternative: path to the table image file

    Returns:
        Dict with structured table data (headers, rows, notes)
    """
    # Get image as base64
    if image_base64 is None:
        if image_path is None:
            return {"error": "Must provide either image_base64 or image_path"}
        try:
            image_base64 = _image_to_base64(image_path)
        except FileNotFoundError as e:
            return {"error": str(e)}

    # Get prompt
    prompt = _get_prompt("table_analysis", TABLE_ANALYSIS_PROMPT)

    # Call VLM
    result = await _call_vlm(image_base64, prompt)

    if "error" in result:
        return result

    return {
        "success": True,
        "table_data": result.get("data"),
        "raw_response": result.get("raw_response"),
    }


async def analyze_chart(
    image_base64: str | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    """Analyze a chart/figure image using a Vision-Language Model.

    Args:
        image_base64: Base64-encoded image of the chart
        image_path: Alternative: path to the chart image file

    Returns:
        Dict with chart metadata (type, axes, data points, trends)
    """
    # Get image as base64
    if image_base64 is None:
        if image_path is None:
            return {"error": "Must provide either image_base64 or image_path"}
        try:
            image_base64 = _image_to_base64(image_path)
        except FileNotFoundError as e:
            return {"error": str(e)}

    # Get prompt
    prompt = _get_prompt("chart_analysis", CHART_ANALYSIS_PROMPT)

    # Call VLM
    result = await _call_vlm(image_base64, prompt)

    if "error" in result:
        return result

    return {
        "success": True,
        "chart_data": result.get("data"),
        "raw_response": result.get("raw_response"),
    }
