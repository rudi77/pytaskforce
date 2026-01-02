# Self-Maintaining Documentation
This file should be updated automatically when project-specific patterns, conventions, or important information are discovered during work sessions. Add relevant details here to help future interactions understand the codebase better. Anything that is very general knowledge about this project and that should be remembered always should be added here.

- Taskforce exception types live in `src/taskforce/core/domain/errors.py` (TaskforceError + LLMError, ToolError, etc.). Infra tools should convert unexpected failures into `ToolError` payloads via `tool_error_payload`.
