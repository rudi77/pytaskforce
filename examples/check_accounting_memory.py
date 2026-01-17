"""
Check if memory tools are loaded in accounting agent plugin

Run with: uv run python examples/check_accounting_memory.py
"""

import asyncio
from taskforce.application.factory import AgentFactory


async def main():
    print("Checking memory tools in accounting_agent plugin...\n")

    factory = AgentFactory()
    agent = await factory.create_agent_with_plugin(
        plugin_path="examples/accounting_agent",
        profile="dev"
    )

    # List all tools
    tool_names = list(agent.tools.keys())

    # Check for memory tools
    memory_tools = [
        "create_entities",
        "create_relations",
        "add_observations",
        "read_graph",
        "search_nodes",
        "open_nodes",
        "delete_entities",
        "delete_observations",
        "delete_relations",
    ]

    print(f"Total tools loaded: {len(tool_names)}")
    print("\nMemory tools status:")
    print("-" * 50)

    found = 0
    for tool in memory_tools:
        status = "[OK]" if tool in tool_names else "[MISSING]"
        print(f"{status} {tool}")
        if tool in tool_names:
            found += 1

    print("-" * 50)
    print(f"\nResult: {found}/{len(memory_tools)} memory tools loaded")

    if found == len(memory_tools):
        print("\n[SUCCESS] Memory integration successful!")
        print("\nNote: The knowledge_graph.jsonl file will be created when you first use")
        print("      a memory tool (e.g., create_entities). The directory is already created.")
    else:
        print("\n[WARNING] Some memory tools missing. Check MCP server config.")
        print("\nTroubleshooting:")
        print("  1. Ensure Node.js is installed (npx command available)")
        print("  2. Check logs for 'connecting_to_mcp_server' messages")
        print("  3. Verify mcp_servers config in accounting_agent.yaml")

    print("\nAll available tools:")
    for name in sorted(tool_names):
        print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
