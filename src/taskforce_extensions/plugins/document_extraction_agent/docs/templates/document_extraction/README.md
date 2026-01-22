# Document Extraction Multi-Agent Templates

This directory provides a multi-agent template structure for an agentic
Document Information Extraction workflow (OCR → reading order → layout
classification → VLM analysis → synthesis).

## Directory Layout

```
plugins/document_extraction_agent/
  configs/
    document_extraction_agent.yaml
    agents/
      orchestrator.yaml
      ocr_agent.yaml
      layout_agent.yaml
      reading_order_agent.yaml
      vlm_table_agent.yaml
      vlm_chart_agent.yaml
      synthesis_agent.yaml
  document_extraction_agent/
    tools/
      document_extraction_tools.py
  docs/templates/document_extraction/
    README.md
    tools.md
    prompts/
      orchestrator.md
      ocr_agent.md
      layout_agent.md
      reading_order_agent.md
      vlm_table_agent.md
      vlm_chart_agent.md
      synthesis_agent.md
```

## Usage (CLI)

Load the orchestrator profile and let it delegate work:

```powershell
# Example (assuming custom tool implementations exist)
TASKFORCE_PROFILE=plugins/document_extraction_agent/configs/agents/orchestrator \
  taskforce run mission "Extract tables and charts from report.png" --plugin plugins/document_extraction_agent
```

## Notes

- The YAML profiles reference tool names that must be implemented as
  Taskforce tools (see `tools.md` for schema sketches).
- Prompt templates under `prompts/` can be copied into the YAML
  `system_prompt` fields or used as canonical references.
- Tool stubs and agent configs live in the plugin for wiring in OCR, layout,
  and VLM logic.
