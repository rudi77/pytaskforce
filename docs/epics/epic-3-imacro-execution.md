# iMacro Execution via Python Tool - Brownfield Enhancement

## Epic Goal

Enable the agent to execute iMacro workflow scripts using the Python tool by providing access to **all loaded agent tools** within the Python execution context, allowing automated execution of previously defined workflows with any combination of available tools (native, MCP, or custom).

## Epic Description

**Existing System Context:**

- **Current Functionality:** 
  - The agent loads tools dynamically (native tools, MCP tools) via `AgentFactory`
  - The `PythonTool` executes Python code in an isolated namespace with pre-imported libraries
  - Agent tools are only accessible to the agent's ReAct loop, not to Python code executed by `PythonTool`
  - iMacros currently serve only as documentation and require manual step-by-step execution by the agent
  - Each tool implements `ToolProtocol` with `execute(**kwargs)` method
- **Technology Stack:** Python 3.11, Clean Architecture, `uv` for dependency management, OpenAI LLM provider, MCP integration
- **Integration Points:** 
  - `PythonTool` (`taskforce/infrastructure/tools/native/python_tool.py`)
  - Agent's tool registry in `Agent` class (list of `ToolProtocol` instances)
  - `AgentFactory` (tool initialization and registration)
  - System prompts (for iMacro generation guidance)

**Enhancement Details:**

- **What's being added:**
  - An `agent_tools` module/object that dynamically exposes **all loaded agent tools** in the Python execution context
  - Generic wrapper that discovers tools from the agent's registry and makes them callable as `agent_tools.{tool_name}(**kwargs)`
  - Enhanced `PythonTool` to accept an optional `tool_registry` parameter (list of `ToolProtocol` instances)
  - System prompt updates to guide iMacro generation with `agent_tools.*` calls for any available tool
  - Agent capability to execute iMacro scripts via Python tool with full tool access
- **How it integrates:**
  - `AgentFactory` passes the complete tool registry (native + MCP + custom) to `PythonTool` during initialization
  - `PythonTool.execute()` injects `agent_tools` object into the safe namespace
  - `agent_tools` dynamically exposes methods for each tool in the registry (e.g., `agent_tools.query_db()`, `agent_tools.web_search()`, `agent_tools.file_read()`)
  - Tool calls are routed to the actual `ToolProtocol.execute()` methods via async-to-sync bridge
  - Works with **any** tool that implements `ToolProtocol`, regardless of source (native, MCP, custom)
- **Success criteria:**
  - iMacros can call **any** tool loaded by the agent (native, MCP, custom)
  - User can ask agent to "execute the iMacro" and it runs via Python tool with full tool access
  - iMacros can chain multiple tool calls from different sources (e.g., MCP query_db → native python → MCP file_write)
  - Tool discovery is automatic - no hardcoded tool names in wrapper
  - Errors in iMacro execution are properly reported to the user

## Stories

1. **Story 3.1: Generic Agent Tools Wrapper Module**
   - Create `AgentToolsWrapper` class that dynamically wraps **any** tool registry
   - Implement `__getattr__` to dynamically expose tools as methods (e.g., `wrapper.query_db()` → calls tool with name "query_db")
   - Implement async-to-sync bridge for tool execution (since Python exec is sync)
   - Extract tool parameter schemas from `ToolProtocol.parameters_schema` to validate calls
   - Handle tool execution errors gracefully and return structured error responses
   - Support both positional and keyword arguments based on tool schema
   - Add unit tests for wrapper with mock tools (native and MCP-style)

2. **Story 3.2: Enhance Python Tool with Dynamic Tool Injection**
   - Modify `PythonTool.__init__()` to accept optional `tool_registry: List[ToolProtocol]` parameter
   - Update `PythonTool.execute()` to inject `agent_tools` object (instance of `AgentToolsWrapper`) into safe namespace
   - Ensure backward compatibility (Python tool works without tool_registry for standalone use)
   - Update `AgentFactory.create_agent()` to pass complete tool list to PythonTool during initialization
   - Add integration tests for Python tool with multiple tool types (native + MCP)
   - Test that iMacros can call tools by name without hardcoding

3. **Story 3.3: System Prompt Updates and End-to-End Validation**
   - Update system prompts (text2sql, generic) to guide iMacro generation with `agent_tools.*` calls
   - Add examples showing iMacros using various tools (query_db, web_search, file_read, etc.)
   - Document that `agent_tools` dynamically exposes all loaded tools
   - Update agent logic to recognize "execute iMacro" command and run script via Python tool
   - Test end-to-end workflows:
     - Generate iMacro using MCP tool → execute it
     - Generate iMacro chaining native + MCP tools → execute it
     - Verify tool discovery works for newly added MCP servers
   - Document iMacro execution in user guide with multi-tool examples

## Compatibility Requirements

- [x] Existing APIs remain unchanged (Python tool still works without agent_tools)
- [x] Database schema changes are backward compatible (N/A)
- [x] UI changes follow existing patterns (N/A)
- [x] Performance impact is minimal (tool calls already async, wrapper adds negligible overhead)

## Risk Mitigation

- **Primary Risk:** Circular dependency or deadlock if iMacro Python code tries to call tools while agent is waiting for Python execution
  - **Mitigation:** Use proper async/sync bridging with timeouts. Document that iMacros should be simple, linear workflows without complex control flow
- **Secondary Risk:** Security concern if user-generated iMacro code can access all agent tools without validation
  - **Mitigation:** iMacros run in the same security context as agent (already trusted). Consider adding optional approval step for iMacro execution
- **Rollback Plan:** Remove `agent_tools_registry` parameter from PythonTool, revert prompt changes, remove AgentToolsWrapper module

## Definition of Done

- [x] All stories completed with acceptance criteria met
- [ ] Agent can generate executable iMacros with `agent_tools.*` calls
- [ ] User can execute iMacros via "execute the iMacro" command
- [ ] iMacros can chain multiple tool calls successfully
- [ ] Error handling works correctly (tool failures reported to user)
- [ ] Existing Python tool functionality verified (no regression)
- [ ] Integration tests pass for iMacro execution workflow
- [ ] Documentation updated with iMacro execution examples

## Technical Notes

### Dynamic Tool Discovery Strategy

The wrapper uses `__getattr__` to dynamically expose any tool:

```python
import asyncio
from typing import List, Any

class AgentToolsWrapper:
    """
    Dynamic wrapper that exposes all agent tools as callable methods.
    Works with any tool implementing ToolProtocol.
    """
    def __init__(self, tool_registry: List[ToolProtocol], loop):
        # Build tool lookup by name
        self._tools = {tool.name: tool for tool in tool_registry}
        self._loop = loop
    
    def __getattr__(self, tool_name: str):
        """
        Dynamically create a callable for any tool in the registry.
        Example: agent_tools.query_db(...) → calls tool with name "query_db"
        """
        if tool_name not in self._tools:
            raise AttributeError(f"Tool '{tool_name}' not found. Available: {list(self._tools.keys())}")
        
        tool = self._tools[tool_name]
        
        def tool_caller(**kwargs) -> Any:
            # Run async tool in the event loop
            coro = tool.execute(**kwargs)
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            result = future.result(timeout=60)
            
            # Return result or raise error
            if result.get("success"):
                return result.get("result") or result.get("output")
            else:
                raise RuntimeError(f"Tool '{tool_name}' failed: {result.get('error')}")
        
        return tool_caller
    
    def list_tools(self) -> List[str]:
        """Return list of available tool names."""
        return list(self._tools.keys())
```

### Example Executable iMacros

**Example 1: Using MCP query_db tool**
```python
def iMacro_report_open_invoices():
    """
    Executable workflow using MCP query_db tool.
    """
    # Step 1: Fetch Data (calls MCP tool)
    data = agent_tools.query_db(
        query="Show all customers with open invoices including customer name, email, and invoice count"
    )
    
    # Step 2: Process
    rows = data.get("result", [])
    
    # Step 3: Format as Markdown
    report = "# Kunden mit offenen Rechnungen\n\n"
    report += "| Kunde | E-Mail | Anzahl |\n"
    report += "|-------|--------|--------|\n"
    for row in rows:
        name, email, count = row
        report += f"| {name} | {email} | {count} |\n"
    
    return report

result = iMacro_report_open_invoices()
print(result)
```

**Example 2: Chaining multiple tools (MCP + Native)**
```python
def iMacro_research_and_document():
    """
    Workflow using web_search (MCP), llm_generate (native), and file_write (MCP).
    """
    # Step 1: Research (MCP web search tool)
    search_results = agent_tools.web_search(
        query="Python async best practices 2024"
    )
    
    # Step 2: Analyze and summarize (native LLM tool)
    summary = agent_tools.llm_generate(
        prompt=f"Summarize these search results:\n{search_results}"
    )
    
    # Step 3: Save to file (MCP file tool)
    agent_tools.file_write(
        path="research_summary.md",
        content=summary
    )
    
    return "Research completed and saved to research_summary.md"

result = iMacro_research_and_document()
print(result)
```

**Example 3: Discovering available tools**
```python
def iMacro_list_capabilities():
    """
    List all available tools dynamically.
    """
    tools = agent_tools.list_tools()
    
    report = "# Available Agent Tools\n\n"
    for tool in sorted(tools):
        report += f"- `{tool}`\n"
    
    return report

print(iMacro_list_capabilities())
```

## Story Manager Handoff

**Story Manager Handoff:**

"Please develop detailed user stories for this brownfield epic. Key considerations:

- This is an enhancement to the existing Taskforce agent framework running Python 3.11 with Clean Architecture
- Integration points: 
  - `PythonTool` (needs dynamic tool_registry injection)
  - `AgentFactory` (needs to pass complete tool list to PythonTool)
  - `AgentToolsWrapper` (new module for dynamic tool exposure)
  - System prompts (need guidance for iMacro generation with any tool)
- Existing patterns to follow: 
  - `ToolProtocol` interface for all tools (native, MCP, custom)
  - Async/await for tool execution
  - Structured error responses with success/error fields
  - Dynamic tool discovery (no hardcoded tool names)
- Critical compatibility requirements: 
  - Python tool must remain backward compatible (works without tool_registry)
  - No breaking changes to existing tool interfaces
  - Proper async/sync bridging to avoid deadlocks
  - Must work with **any** tool implementing `ToolProtocol` (native, MCP, future custom)
  - Tool discovery must be automatic - wrapper should not need updates when new tools are added
- Each story must include verification that:
  - Existing Python tool functionality remains intact
  - iMacros work with native tools
  - iMacros work with MCP tools
  - iMacros work with mixed tool chains
  - New MCP servers added via config are automatically available in iMacros

The epic should enable seamless iMacro execution with **any** loaded tool while maintaining system integrity, security, and extensibility."

