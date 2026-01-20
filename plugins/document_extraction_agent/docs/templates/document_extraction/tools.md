# Tool Sketches (Document Extraction)

These sketches describe the expected Taskforce tool interfaces for the
Document Extraction multi-agent workflow.

## 1) ocr_extract

**Purpose:** Run OCR on a document image and return text regions.

**Parameters (JSON schema):**
```json
{
  "type": "object",
  "properties": {
    "document_path": {
      "type": "string",
      "description": "Path to input image/PDF page."
    }
  },
  "required": ["document_path"]
}
```

**Returns:**
```json
{
  "success": true,
  "result": {
    "regions": [
      {
        "text": "...",
        "confidence": 0.98,
        "bbox_polygon": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
        "bbox_xyxy": [x1,y1,x2,y2]
      }
    ]
  }
}
```

## 2) reading_order

**Purpose:** Determine reading order for OCR regions.

**Parameters:**
```json
{
  "type": "object",
  "properties": {
    "regions": {
      "type": "array",
      "description": "OCR regions with bbox_xyxy"
    }
  },
  "required": ["regions"]
}
```

**Returns:**
```json
{
  "success": true,
  "result": {
    "ordered_regions": [
      {
        "position": 0,
        "text": "...",
        "confidence": 0.98,
        "bbox_xyxy": [x1,y1,x2,y2]
      }
    ]
  }
}
```

## 3) layout_detect

**Purpose:** Detect layout regions (text/table/chart/figure/etc.).

**Parameters:**
```json
{
  "type": "object",
  "properties": {
    "document_path": {
      "type": "string",
      "description": "Path to input image/PDF page."
    }
  },
  "required": ["document_path"]
}
```

**Returns:**
```json
{
  "success": true,
  "result": {
    "regions": [
      {
        "region_id": 12,
        "type": "table",
        "bbox_xyxy": [x1,y1,x2,y2],
        "confidence": 0.92
      }
    ]
  }
}
```

## 4) crop_region

**Purpose:** Crop a region from the document for downstream VLM analysis.

**Parameters:**
```json
{
  "type": "object",
  "properties": {
    "document_path": {"type": "string"},
    "bbox_xyxy": {"type": "array"}
  },
  "required": ["document_path", "bbox_xyxy"]
}
```

**Returns:**
```json
{
  "success": true,
  "result": {
    "image_base64": "...",
    "bbox_xyxy": [x1,y1,x2,y2]
  }
}
```

## 5) analyze_table

**Purpose:** Extract structured data from a table crop.

**Parameters:**
```json
{
  "type": "object",
  "properties": {
    "image_base64": {"type": "string"},
    "region_id": {"type": "integer"}
  },
  "required": ["image_base64", "region_id"]
}
```

**Returns:**
```json
{
  "success": true,
  "result": {
    "region_id": 12,
    "table_title": "...",
    "column_headers": ["..."],
    "rows": [
      {"row_label": "...", "values": ["...", "..."]}
    ],
    "notes": "..."
  }
}
```

## 6) analyze_chart

**Purpose:** Extract chart metadata, axes, and key datapoints from a chart crop.

**Parameters:**
```json
{
  "type": "object",
  "properties": {
    "image_base64": {"type": "string"},
    "region_id": {"type": "integer"}
  },
  "required": ["image_base64", "region_id"]
}
```

**Returns:**
```json
{
  "success": true,
  "result": {
    "region_id": 5,
    "chart_type": "line",
    "title": "...",
    "x_axis": {"label": "...", "ticks": ["..."]},
    "y_axis": {"label": "...", "ticks": ["..."]},
    "key_data_points": ["..."],
    "trends": "...",
    "legend": ["..."]
  }
}
```
