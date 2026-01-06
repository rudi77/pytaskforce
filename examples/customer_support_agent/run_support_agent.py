"""
Customer Support Agent Example - Usage Script.

This script demonstrates how to use the Taskforce framework to create
and run a custom customer support agent with a specialized ticket
management tool.

Usage:
    python examples/customer_support_agent/run_support_agent.py
"""

import asyncio
import os
import sys
from pathlib import Path

import structlog

# Add project root to path to import taskforce
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from taskforce.application.factory import AgentFactory

# Import custom ticket tool
from examples.customer_support_agent.tools.ticket_tool import TicketTool

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


SUPPORT_SYSTEM_PROMPT = """You are a professional customer support agent for TechCorp, a software company.

Your responsibilities:
1. Handle customer inquiries with empathy and professionalism
2. Create and manage support tickets for customer issues
3. Troubleshoot technical problems
4. Search knowledge base and documentation for solutions
5. Escalate complex issues when necessary
6. Keep customers informed about ticket status

Communication Style:
- Be friendly, professional, and empathetic
- Use clear, non-technical language unless the customer is technical
- Always confirm understanding before taking action
- Provide ticket IDs for reference
- Set realistic expectations for resolution times

Ticket Management:
- Create tickets for all customer issues
- Update ticket status as you work (open → in_progress → resolved)
- Add detailed notes about troubleshooting steps
- Set appropriate priority levels (low/medium/high/critical)

Available Tools:
- ticket_manager: Create, read, update, list, and search support tickets
- web_search: Search for solutions in documentation
- web_fetch: Retrieve specific documentation pages
- python: Analyze data or generate reports
- file_read/file_write: Access customer data or export reports
- ask_user: Ask clarifying questions

Best Practices:
1. Always create a ticket for new issues
2. Document all troubleshooting steps in ticket notes
3. Search for similar past tickets before troubleshooting
4. Update ticket status as you progress
5. Confirm resolution with customer before closing tickets
"""


async def create_support_agent():
    """
    Create a customer support agent with custom tools.

    This demonstrates how to use create_lean_agent_from_definition()
    to build an agent with custom tools and system prompt.
    """
    logger.info("initializing_support_agent")

    # Create custom tools
    ticket_tool = TicketTool(tickets_dir=".taskforce_support/tickets")

    # Note: In a full implementation, you would add the ticket_tool
    # to the tools list. For this example, we'll use standard tools
    # and show how to integrate custom tools.

    # Define agent configuration
    agent_definition = {
        "system_prompt": SUPPORT_SYSTEM_PROMPT,
        "tool_allowlist": [
            "web_search",
            "web_fetch",
            "python",
            "file_read",
            "file_write",
            "ask_user",
            # "ticket_manager",  # Would need to be registered first
        ],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    factory = AgentFactory()

    # Create agent from definition
    agent = await factory.create_lean_agent_from_definition(
        agent_definition=agent_definition,
        profile="dev",  # Use dev profile for infrastructure settings
        work_dir=".taskforce_support",
    )

    # TODO: In production, you would inject custom tools here
    # For now, this demonstrates the pattern:
    # agent.tools.append(ticket_tool)

    logger.info(
        "support_agent_created",
        tools_count=len(agent.tools),
        tool_names=[t.name for t in agent.tools],
    )

    return agent


async def run_example_mission():
    """
    Run an example support mission.

    This demonstrates how a customer support agent would handle
    a typical customer inquiry.
    """
    logger.info("starting_example_mission")

    # Create the support agent
    agent = await create_support_agent()

    # Example mission: Handle a customer complaint
    mission = """
    A customer (email: [email protected]) is reporting that they cannot
    log in to their account. They say they've tried resetting their password
    but the reset email never arrives. This has been going on for 2 hours.

    Please:
    1. Create a support ticket with appropriate priority
    2. Troubleshoot the issue
    3. Search for similar past issues or documentation
    4. Provide a solution or escalation plan
    5. Update the ticket with your findings
    """

    session_id = "support-example-001"

    try:
        # Execute the mission
        logger.info("executing_mission", session_id=session_id)

        result = await agent.execute(
            mission=mission,
            session_id=session_id,
        )

        logger.info(
            "mission_completed",
            session_id=session_id,
            success=result.get("success", False),
            steps_taken=result.get("steps_taken", 0),
        )

        # Display results
        print("\n" + "=" * 80)
        print("MISSION RESULT")
        print("=" * 80)
        print(f"\nSuccess: {result.get('success', False)}")
        print(f"Steps Taken: {result.get('steps_taken', 0)}")
        print(f"\nFinal Answer:\n{result.get('final_answer', 'No answer provided')}")
        print("\n" + "=" * 80)

    except Exception as e:
        logger.error(
            "mission_failed",
            session_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def demonstrate_ticket_tool():
    """
    Demonstrate the ticket tool directly.

    This shows how the custom ticket tool works independently
    of the agent framework.
    """
    logger.info("demonstrating_ticket_tool")

    # Create ticket tool instance
    ticket_tool = TicketTool(tickets_dir=".taskforce_support/demo_tickets")

    print("\n" + "=" * 80)
    print("TICKET TOOL DEMONSTRATION")
    print("=" * 80)

    # 1. Create a ticket
    print("\n1. Creating a new ticket...")
    result = await ticket_tool.execute(
        operation="create_ticket",
        customer_email="[email protected]",
        subject="Login issues - password reset not working",
        description="Customer cannot log in. Password reset email not arriving.",
        priority="high",
    )
    print(f"   Created: {result['ticket']['ticket_id']}")
    ticket_id = result["ticket"]["ticket_id"]

    # 2. Get ticket details
    print(f"\n2. Retrieving ticket {ticket_id}...")
    result = await ticket_tool.execute(operation="get_ticket", ticket_id=ticket_id)
    print(f"   Status: {result['ticket']['status']}")
    print(f"   Priority: {result['ticket']['priority']}")

    # 3. Update ticket
    print(f"\n3. Updating ticket status and adding notes...")
    result = await ticket_tool.execute(
        operation="update_ticket",
        ticket_id=ticket_id,
        status="in_progress",
        notes="Checked email delivery logs - no blocks found. Investigating account status.",
    )
    print(f"   Updated status: {result['ticket']['status']}")
    print(f"   Notes added: {len(result['ticket']['notes'])}")

    # 4. List all tickets
    print("\n4. Listing all open tickets...")
    result = await ticket_tool.execute(operation="list_tickets", status="in_progress")
    print(f"   Found {result['count']} ticket(s) in progress")

    # 5. Search tickets
    print("\n5. Searching for tickets by email...")
    result = await ticket_tool.execute(
        operation="search_tickets", search_query="alice"
    )
    print(f"   Found {result['count']} matching ticket(s)")

    print("\n" + "=" * 80)
    print("Demonstration complete!")
    print("=" * 80 + "\n")


async def main():
    """Main entry point."""
    import logging

    # Set log level
    logging.basicConfig(level=logging.INFO)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Please set it before running this example:")
        print("  export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("CUSTOMER SUPPORT AGENT EXAMPLE")
    print("=" * 80)
    print("\nThis example demonstrates how to create a custom specialized agent")
    print("using the Taskforce framework.\n")

    # Choose what to run
    print("Choose an option:")
    print("1. Demonstrate ticket tool only (fast)")
    print("2. Run full support agent mission (requires LLM)")
    print("3. Both")

    choice = input("\nEnter choice (1/2/3): ").strip()

    if choice in ["1", "3"]:
        await demonstrate_ticket_tool()

    if choice in ["2", "3"]:
        await run_example_mission()

    print("\nExample completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
