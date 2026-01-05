# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
