"""
Quick demo: Agent with long-term memory

Run with: uv run python examples/memory_demo.py
"""

import asyncio
from taskforce.application.factory import AgentFactory


async def main():
    print("=" * 70)
    print("MEMORY DEMO: Learning User Preferences")
    print("=" * 70)

    # Create agent with memory
    factory = AgentFactory()
    agent = await factory.create_agent(profile="coding_agent")

    print("\n[Session 1: Teaching the agent]")
    print("-" * 70)

    # First interaction - agent learns
    result1 = await agent.execute(
        mission="Remember: I prefer Python with type hints and avoid abbreviations",
        session_id="demo-session-1",
    )

    print(f"\nAgent: {result1.final_answer}")
    print("\n[Memory stored: User preferences]")

    print("\n" + "=" * 70)
    print("\n[Session 2: Agent recalls (in new session)]")
    print("-" * 70)

    # Second interaction - agent recalls
    result2 = await agent.execute(
        mission="Write a function to calculate factorial",
        session_id="demo-session-2",  # Different session!
    )

    print(f"\nAgent: {result2.final_answer}")
    print("\n[Memory recalled: Agent uses type hints as preferred]")

    print("\n" + "=" * 70)
    print("\nMemory file location:")
    print("  .taskforce_coding/.memory/knowledge_graph.jsonl")
    print("\nView memory:")
    print("  cat .taskforce_coding/.memory/knowledge_graph.jsonl | jq")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
