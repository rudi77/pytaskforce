# Self-Maintaining Documentation
This file should be updated automatically when project-specific patterns, conventions, or important information are discovered during work sessions. Add relevant details here to help future interactions understand the codebase better. Anything that is very general knowledge about this project and that should be remembered always should be added here.

- Execution API errors now use a standardized payload (`code`, `message`, `details`, optional `detail`) via `ErrorResponse`, with responses emitted from `HTTPException` objects tagged by the `X-Taskforce-Error: 1` header and handled in `taskforce.api.server.taskforce_http_exception_handler`.
