# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Gateway conversation store renamed and moved on disk.** The Communication
  Gateway's `FileConversationStore` (in
  `taskforce.infrastructure.communication`) is now `GatewayConversationStore`
  and writes to `.taskforce/gateway_sessions/{channel}/{conversation_id}.json`
  instead of `.taskforce/conversations/{channel}/{conversation_id}.json`. This
  removes a name and path collision with the persistence-layer
  `FileConversationStore` (ADR-016). The corresponding in-memory class is
  `InMemoryGatewayConversationStore`.
  - **Migration:** existing channel-to-session mappings under
    `.taskforce/conversations/{channel}/` are not auto-migrated. To preserve
    them, move the files: `mv .taskforce/conversations/{channel} .taskforce/gateway_sessions/{channel}`.
    Otherwise the gateway will mint new sessions on next inbound message.

### Removed

- **`FileHeartbeatStore`** (`taskforce.infrastructure.runtime`). Heartbeats
  were recorded per ReAct step but never read by production code, so the
  per-step file write produced disk churn without a consumer. The
  infrastructure builder now uses `InMemoryHeartbeatStore` even when
  `runtime.store: file` is configured. `FileCheckpointStore` continues to
  persist checkpoints normally; infer cross-process liveness from checkpoint
  mtimes if needed.

## [0.1.0] - 2026-01-05

### Added

- Initial release of Taskforce multi-agent orchestration framework
- **LeanAgent** with ReAct loop execution and native tool calling
- **Planning Strategies**: NativeReAct, PlanAndExecute, PlanAndReact
- **Native Tools**:
  - File operations (read, write)
  - Shell execution (PowerShell)
  - Python code execution
  - Git and GitHub integration
  - Web search and fetch
  - Ask user for input
- **MCP Tool Integration** (stdio and SSE protocols)
- **CLI Interface** with Typer:
  - `taskforce run mission` - Execute missions
  - `taskforce chat` - Interactive chat mode
  - `taskforce tools list` - List available tools
  - `taskforce sessions` - Session management
  - `taskforce config` - Configuration management
- **REST API** with FastAPI for microservice deployment
- **Persistence**: File-based (dev) and PostgreSQL (prod) state managers
- **RAG Integration**: Azure AI Search semantic search tools
- **Observability**: Arize Phoenix tracing integration
- **Context Management**: Configurable context policies for LLM calls
- **Custom Agent Definitions**: YAML-based agent configuration

### Architecture

- Clean Architecture (Hexagonal) with four-layer separation:
  - Core: Pure domain logic and protocols
  - Infrastructure: External integrations (LLM, persistence, tools)
  - Application: Use cases and dependency injection
  - API: CLI and REST entrypoints
- Protocol-based design using Python Protocols (PEP 544)
- Async-first implementation for all I/O operations

[Unreleased]: https://github.com/yourorg/pytaskforce/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourorg/pytaskforce/releases/tag/v0.1.0
