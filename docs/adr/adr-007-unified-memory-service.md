# ADR 007: Unified Memory Service

## Status
Accepted

## Context
Taskforce previously relied on the MCP memory server (`@modelcontextprotocol/server-memory`) for long-term memory. The MCP dependency introduced operational overhead (Node/npm requirements) and tied memory to an external server process. We also needed a unified memory interface that can be swapped from file storage to other backends without changing agent code.

## Decision
We implemented a unified memory service and native `memory` tool backed by a file-based Markdown store. Memory records are stored under a profile-specific directory (`memory.store_dir`), and the agent interacts with memory through a consistent CRUD API exposed by the `memory` tool.

## Consequences
- **Pros**
  - Removes the MCP memory server dependency.
  - File-based MVP keeps setup simple and portable.
  - Consistent record model (scope/kind/tags/content/metadata) for future backends.
- **Cons**
  - Full-text search is naive (file scan).
  - No built-in vector semantics or access control enforcement yet.

## Follow-ups
- Add optional vector indexing for semantic recall.
- Add ACL enforcement and encryption hooks for enterprise deployments.
- Add automatic summarization/compaction for older records.
