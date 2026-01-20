# Document Extraction Agent Plugin

This plugin provides tool stubs for the document extraction multi-agent workflow
(OCR → reading order → layout detection → VLM analysis → synthesis).

## Included Tools

- `ocr_extract`
- `reading_order`
- `layout_detect`
- `crop_region`
- `analyze_table`
- `analyze_chart`

## Configuration

The plugin ships with a default config:

```
plugins/document_extraction_agent/configs/document_extraction_agent.yaml
```

Specialist agent profiles for the multi-agent workflow live in:

```
plugins/document_extraction_agent/configs/agents/
```

Prompt and tool sketches live alongside the plugin:

```
plugins/document_extraction_agent/docs/templates/document_extraction/
```

## Notes

The tool implementations are placeholders that return standardized
"not implemented" errors. Replace the bodies with your OCR/Layout/VLM logic
(e.g., PaddleOCR, LayoutReader, and a vision-language model API).
