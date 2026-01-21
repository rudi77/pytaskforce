# Document Extraction MCP Server

A standalone MCP (Model Context Protocol) server providing document extraction tools for OCR, layout detection, reading order analysis, and VLM-based table/chart extraction.

## Features

| Tool | Description | Backend |
|------|-------------|---------|
| `ocr_extract` | Extract text with bounding boxes | PaddleOCR |
| `layout_detect` | Detect document regions (table, chart, text, figure) | PaddleOCR LayoutDetection |
| `reading_order` | Sort OCR regions into reading sequence | LayoutReader + LayoutLMv3 |
| `crop_region` | Crop a region, return base64 image | Pillow |
| `analyze_table` | Extract structured table data | VLM (GPT-4o-mini) |
| `analyze_chart` | Extract chart metadata and trends | VLM (GPT-4o-mini) |

## Installation

This server has its own isolated virtual environment with heavy ML dependencies (~4GB total).
**Requires CUDA 12.1** for GPU acceleration.

```bash
cd servers/document-extraction-mcp

# Step 1: Install base dependencies (includes paddlepaddle-gpu)
uv sync

# Step 2: Install PyTorch with CUDA 12.1
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Verify GPU Support

```bash
uv run python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
uv run python -c "import paddle; print(f'PaddlePaddle GPU: {paddle.device.is_compiled_with_cuda()}')"
```

### First Run (Model Download)

On first use, models will be downloaded automatically:
- PaddleOCR models (~200MB)
- LayoutLMv3 model (~500MB)

## Usage

### With Taskforce

The server is configured in the document extraction plugin:

```bash
# From project root
taskforce run mission "Extract tables from invoice.pdf" \
  --plugin plugins/document_extraction_agent
```

### Standalone Testing

```bash
# Run the server directly
cd servers/document-extraction-mcp
uv run python -m document_extraction_mcp.server

# Or use the entry point
uv run document-extraction-mcp
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required for VLM) | API key for vision model |
| `VLM_MODEL` | `gpt-4o-mini` | Model for table/chart analysis |
| `AZURE_API_KEY` | - | Azure OpenAI key (if using Azure) |
| `AZURE_API_BASE` | - | Azure endpoint |

### Plugin Configuration

In `plugins/document_extraction_agent/configs/document_extraction_agent.yaml`:

```yaml
mcp_servers:
  - type: stdio
    command: uv
    args:
      - "--directory"
      - "servers/document-extraction-mcp"
      - "run"
      - "python"
      - "-m"
      - "document_extraction_mcp.server"
    env:
      OPENAI_API_KEY: "${OPENAI_API_KEY}"
      VLM_MODEL: "gpt-4o"  # Optional: use full GPT-4o
```

## Tool Details

### ocr_extract

Extract text from document images with bounding boxes.

**Input:**
```json
{
  "image_path": "/path/to/document.png"
}
```

**Output:**
```json
{
  "success": true,
  "region_count": 42,
  "image_width": 1200,
  "image_height": 1600,
  "regions": [
    {
      "index": 0,
      "text": "Invoice #12345",
      "confidence": 0.98,
      "bbox": [100, 50, 300, 80],
      "polygon": [[100, 50], [300, 50], [300, 80], [100, 80]]
    }
  ]
}
```

### layout_detect

Detect document layout regions (tables, charts, figures, text blocks).

**Input:**
```json
{
  "image_path": "/path/to/document.png"
}
```

**Output:**
```json
{
  "success": true,
  "region_count": 5,
  "type_summary": {"table": 1, "chart": 1, "text": 3},
  "regions": [
    {
      "region_id": 0,
      "region_type": "table",
      "confidence": 0.95,
      "bbox": [50, 200, 550, 400]
    }
  ]
}
```

### reading_order

Determine the reading order of OCR regions using LayoutLMv3.

**Input:**
```json
{
  "regions": [
    {"text": "Title", "bbox": [100, 50, 300, 80]},
    {"text": "Column 1", "bbox": [50, 100, 200, 130]},
    {"text": "Column 2", "bbox": [250, 100, 400, 130]}
  ],
  "image_width": 500,
  "image_height": 700
}
```

**Output:**
```json
{
  "success": true,
  "reading_order": [0, 1, 2],
  "ordered_text": ["Title", "Column 1", "Column 2"]
}
```

### crop_region

Crop a region from an image and return as base64.

**Input:**
```json
{
  "image_path": "/path/to/document.png",
  "bbox": [50, 200, 550, 400],
  "padding": 10
}
```

**Output:**
```json
{
  "success": true,
  "image_base64": "iVBORw0KGgo...",
  "width": 520,
  "height": 220
}
```

### analyze_table

Extract structured data from a table image using VLM.

**Input:**
```json
{
  "image_base64": "iVBORw0KGgo..."
}
```
or
```json
{
  "image_path": "/path/to/table.png"
}
```

**Output:**
```json
{
  "success": true,
  "table_data": {
    "table_title": "Q1 Sales Report",
    "column_headers": ["Product", "Units", "Revenue"],
    "rows": [
      {"row_label": "Widget A", "values": [100, "$1,000"]},
      {"row_label": "Widget B", "values": [50, "$500"]}
    ],
    "notes": "Source: Internal Sales Data"
  }
}
```

### analyze_chart

Extract data from a chart/figure image using VLM.

**Input:**
```json
{
  "image_base64": "iVBORw0KGgo..."
}
```

**Output:**
```json
{
  "success": true,
  "chart_data": {
    "chart_type": "line",
    "title": "Monthly Revenue Trend",
    "x_axis": {"label": "Month", "ticks": ["Jan", "Feb", "Mar"]},
    "y_axis": {"label": "Revenue ($)", "ticks": [0, 500, 1000]},
    "key_data_points": [{"Jan": 200}, {"Feb": 450}, {"Mar": 800}],
    "trends": "Steady upward trend with 100% growth over Q1"
  }
}
```

## Workflow Example

Typical document extraction workflow:

```python
# 1. Run OCR to get text regions
ocr_result = ocr_extract(image_path="report.png")

# 2. Get reading order for the text
ordered = reading_order(regions=ocr_result["regions"])

# 3. Detect layout regions (tables, charts)
layout = layout_detect(image_path="report.png")

# 4. For each table/chart region, crop and analyze
for region in layout["regions"]:
    if region["region_type"] == "table":
        cropped = crop_region(
            image_path="report.png",
            bbox=region["bbox"]
        )
        table_data = analyze_table(
            image_base64=cropped["image_base64"]
        )
    elif region["region_type"] == "chart":
        cropped = crop_region(
            image_path="report.png",
            bbox=region["bbox"]
        )
        chart_data = analyze_chart(
            image_base64=cropped["image_base64"]
        )
```

## Uninstallation

To remove the server and free up disk space:

```bash
# Remove the virtual environment
rm -rf servers/document-extraction-mcp/.venv

# Or remove the entire server
rm -rf servers/document-extraction-mcp
```

## Troubleshooting

### PaddleOCR Installation Issues

On Windows, you may need Visual C++ Build Tools:
```bash
# Install Visual C++ Build Tools from:
# https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

### CUDA Support

For GPU acceleration:
```bash
# Install CUDA-enabled PaddlePaddle
pip install paddlepaddle-gpu

# Install CUDA-enabled PyTorch
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

### Memory Issues

The models require significant RAM (~4GB). If you encounter OOM errors:
- Close other applications
- Use smaller batch sizes
- Consider running on a machine with more RAM
