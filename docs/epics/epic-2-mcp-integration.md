# MCP Server Integration - Brownfield Enhancement

## Epic Goal

Enable the Taskforce agent to discover and use tools provided by local and remote Model Context Protocol (MCP) servers through configuration, expanding its capabilities dynamically without code changes.

## Epic Description

**Existing System Context:**

- **Current Functionality:** Tools are currently hardcoded classes implementing `ToolProtocol`, instantiated by `AgentFactory` based on a static list in `configs/*.yaml`.
- **Technology Stack:** Python 3.11, Clean Architecture, `uv` for dependency management.
- **Integration Points:** `AgentFactory._create_native_tools`, `configs/*.yaml` schema.

**Enhancement Details:**

- **What's being added:**
    - Support for `mcp_servers` configuration in YAML (command-based for local, URL-based for remote).
    - `MCPClient` infrastructure adapter to communicate with MCP servers.
    - `MCPToolWrapper` to adapt MCP tools to `ToolProtocol`.
    - Updates to `AgentFactory` to connect to servers, list tools, and wrap them.
- **Integration Approach:**
    - Extend `AgentFactory` to process `mcp_servers` config section.
    - Use `mcp` python package (or implement minimal client) to interact with servers.
    - Wrap discovered tools as `ToolProtocol` instances so the `Agent` sees them as normal tools.
- **Success Criteria:**
    - Agent can execute tools from a local MCP server (e.g., filesystem).
    - Agent can execute tools from a remote MCP server (SSE).
    - Configuration allows defining multiple servers.

## Stories

1. **Story 2.1: MCP Infrastructure Adapters**
   - Implement `MCPClient` to manage connections to stdio/SSE servers.
   - Implement `MCPToolWrapper` that implements `ToolProtocol` and delegates execution to `MCPClient`.
   - Ensure parameter schema conversion from MCP format to OpenAI function calling format.
   - Add `mcp` dependency to `pyproject.toml`.

2. **Story 2.2: Configuration & Factory Integration**
   - Update `configs/dev.yaml` and `configs/prod.yaml` to support `mcp_servers` section.
   - Update `AgentFactory` to read `mcp_servers` config, initialize clients, fetch tool lists, and create `MCPToolWrapper` instances.
   - Ensure graceful handling of server connection failures (log warning, skip server).

3. **Story 2.3: Validation with Filesystem Server**
   - Add configuration for `@modelcontextprotocol/server-filesystem` in `configs/dev.yaml` (commented out or active).
   - Verify agent can discover and use filesystem tools (read/write/list) via MCP.
   - Document how to add new MCP servers in `docs/architecture/section-3-tech-stack.md` or similar.

## Compatibility Requirements

- [x] Existing APIs remain unchanged.
- [x] Database schema changes are backward compatible (N/A).
- [x] UI changes follow existing patterns (N/A).
- [x] Performance impact is minimal (async tool loading).

## Risk Mitigation

- **Primary Risk:** MCP server latency or instability causing agent startup delays or runtime errors.
- **Mitigation:** Implement timeouts for tool discovery and execution. Isolate tool failures so they don't crash the agent.
- **Rollback Plan:** Revert configuration changes (remove `mcp_servers` section) and revert code changes if necessary.

## Definition of Done

- [ ] All stories completed with acceptance criteria met.
- [ ] Existing functionality verified through testing.
- [ ] Integration points (AgentFactory) working correctly.
- [ ] Documentation updated appropriately.
- [ ] No regression in existing features.

