"""
Check if memory tools are loaded in agent

Run with: uv run python examples/check_memory_tools.py
"""

import asyncio
from taskforce.application.factory import AgentFactory


async def main():
    print("Checking memory tools in coding_agent...\n")

    factory = AgentFactory()
    agent = await factory.create_agent(profile="coding_agent")

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
        status = "✅" if tool in tool_names else "❌"
        print(f"{status} {tool}")
        if tool in tool_names:
            found += 1

    print("-" * 50)
    print(f"\nResult: {found}/{len(memory_tools)} memory tools loaded")

    if found == len(memory_tools):
        print("\n🎉 Memory integration successful!")
    else:
        print("\n⚠️  Some memory tools missing. Check MCP server config.")

    print("\nAll available tools:")
    for name in sorted(tool_names):
        print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
