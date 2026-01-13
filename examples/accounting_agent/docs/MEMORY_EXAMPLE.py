"""
Accounting Agent with Long-Term Memory - Complete Example

This example demonstrates how the accounting agent uses memory
to learn supplier patterns and provide context-aware suggestions.

Usage:
    python examples/accounting_agent/docs/MEMORY_EXAMPLE.py
"""

import asyncio
from pathlib import Path

from taskforce.application.factory import AgentFactory


async def example_learning_workflow():
    """
    Example: Agent learns from first invoice and applies knowledge to second.

    Demonstrates:
    1. First invoice: Agent asks for account, stores in memory
    2. Second invoice: Agent recalls pattern and suggests automatically
    3. Exception handling: Agent detects deviation and asks
    """
    print("=" * 70)
    print("EXAMPLE: Learning Supplier Patterns")
    print("=" * 70)

    # Create accounting agent with memory
    factory = AgentFactory()
    agent = await factory.create_agent_with_plugin(
        plugin_path="examples/accounting_agent",
        profile="dev",  # Uses dev infrastructure
    )

    print("\n[Session 1: First Invoice - Learning Phase]")
    print("-" * 70)

    # Simulate first invoice from new supplier
    mission1 = """
    Neue Rechnung eingegangen:

    Lieferant: DigitalOcean LLC
    Betrag: 450,00 EUR
    Beschreibung: Cloud Hosting Services - Januar 2024

    Bitte verarbeiten.
    """

    print(f"\nUser: {mission1.strip()}")
    print("\n[Agent processing...]")

    result1 = await agent.execute_stream(
        mission=mission1,
        session_id="accounting-session-1",
    )

    async for event in result1:
        if event["type"] == "message":
            print(f"\nAgent: {event['content']}")
        elif event["type"] == "tool_call":
            tool_name = event["tool_name"]
            # Check if memory is being stored
            if tool_name == "create_entities":
                print(f"\n[Memory]: Storing supplier information...")
            elif tool_name == "create_relations":
                print(f"\n[Memory]: Creating account relationships...")

    # Simulate user providing account information
    print("\n\nUser: Bitte auf Konto 6805 (IT-Kosten) buchen, Kostenstelle 8000")

    # Agent stores this in memory (simulated)
    print("[Memory]: ✓ DigitalOcean -> Account 6805 (IT-Kosten)")
    print("[Memory]: ✓ DigitalOcean -> CostCenter 8000")

    print("\n" + "=" * 70)
    print("\n[Session 2: Second Invoice - Recall Phase]")
    print("-" * 70)

    # Simulate second invoice (one month later)
    mission2 = """
    Neue Rechnung eingegangen:

    Lieferant: DigitalOcean LLC
    Betrag: 475,00 EUR
    Beschreibung: Cloud Hosting Services - Februar 2024

    Bitte verarbeiten.
    """

    print(f"\nUser: {mission2.strip()}")
    print("\n[Agent processing...]")

    # Agent should now recall the pattern from memory
    print("\n[Memory]: Searching for 'DigitalOcean'...")
    print("[Memory]: ✓ Found: typically_booked_to Account_6805")
    print("[Memory]: ✓ Found: assigned_to CostCenter_8000")

    result2 = await agent.execute_stream(
        mission=mission2,
        session_id="accounting-session-2",
    )

    async for event in result2:
        if event["type"] == "message":
            print(f"\nAgent: {event['content']}")
        elif event["type"] == "tool_call":
            tool_name = event["tool_name"]
            if tool_name == "search_nodes":
                print(f"\n[Memory]: Agent is searching memory...")

    print("\n\n✅ Memory in Action:")
    print("   - First invoice: Agent learned the pattern")
    print("   - Second invoice: Agent recalled and suggested automatically")
    print("   - No manual input needed!")


async def example_project_allocation():
    """
    Example: Complex project-based cost allocation with memory.

    Demonstrates:
    1. Storing project and supplier relationships
    2. Automatic cost center allocation
    3. Budget tracking
    """
    print("\n\n" + "=" * 70)
    print("EXAMPLE: Project-Based Cost Allocation")
    print("=" * 70)

    factory = AgentFactory()
    agent = await factory.create_agent_with_plugin(
        plugin_path="examples/accounting_agent",
        profile="dev",
    )

    print("\n[Setup: Storing Project Information]")
    print("-" * 70)

    # Simulate storing project info in memory
    print("\n[Memory]: Creating project entity...")
    print("""
    Entity: Project_Phoenix
    Type: Project
    Observations:
      - Internal code: PHX-2024
      - Cost center: 4200
      - Budget: 50,000 EUR
      - Owner: Alice Schmidt
    """)

    print("\n[Memory]: Creating supplier relationship...")
    print("""
    Entity: Freelancer_Mueller
    Type: Supplier
    Relations:
      - works_on: Project_Phoenix
    """)

    print("\n[Invoice Processing with Memory]")
    print("-" * 70)

    mission = """
    Rechnung von Freelancer Müller:

    Betrag: 4.800 EUR
    Beschreibung: Softwareentwicklung (40 Stunden @ 120 EUR/h)

    Bitte verarbeiten.
    """

    print(f"\nUser: {mission.strip()}")
    print("\n[Agent processing...]")

    print("\n[Memory]: Searching for 'Freelancer Mueller'...")
    print("[Memory]: ✓ Found: works_on Project_Phoenix")
    print("\n[Memory]: Opening Project_Phoenix...")
    print("[Memory]: ✓ Cost center: 4200")
    print("[Memory]: ✓ Owner: Alice Schmidt")
    print("[Memory]: ✓ Budget: 50,000 EUR (9.6% used)")

    print("\n\nAgent: Ich ordne die Rechnung automatisch zu:")
    print("""
    Projekt: Phoenix (PHX-2024)
    Kostenstelle: 4200
    Budget-Owner: Alice Schmidt (zur Genehmigung)

    Budget-Status: 4.800 EUR von 50.000 EUR verwendet (9,6%)

    Buchungsvorschlag:
    Soll:  6300 (Fremdleistungen)  4.800,00 EUR  [KST 4200]
    Haben: 1200 (Bank)             4.800,00 EUR

    Soll ich die Genehmigungsanfrage an Alice Schmidt senden?
    """)

    print("\n✅ Memory Benefits:")
    print("   - Automatic project assignment")
    print("   - Cost center allocation")
    print("   - Budget tracking")
    print("   - Owner notification")


async def example_learning_from_corrections():
    """
    Example: Agent learns from user corrections.

    Demonstrates:
    1. Initial suggestion based on pattern matching
    2. User correction
    3. Storing correction in memory
    4. Applying corrected pattern next time
    """
    print("\n\n" + "=" * 70)
    print("EXAMPLE: Learning from Corrections")
    print("=" * 70)

    factory = AgentFactory()
    agent = await factory.create_agent_with_plugin(
        plugin_path="examples/accounting_agent",
        profile="dev",
    )

    print("\n[First Invoice: Incorrect Suggestion]")
    print("-" * 70)

    mission1 = """
    Rechnung von Office Depot:
    Betrag: 250 EUR
    Beschreibung: Büromaterial (Papier, Stifte, etc.)
    """

    print(f"\nUser: {mission1.strip()}")
    print("\n[Agent processing...]")

    print("\nAgent: Buchungsvorschlag:")
    print("""
    Soll:  6800 (Sonstige Kosten)  250,00 EUR
    Haben: 1200 (Bank)             250,00 EUR
    """)

    print("\nUser: ❌ Falsch! Das gehört auf 6815 (Büromaterial), nicht 6800")

    print("\n[Memory]: Storing correction...")
    print("""
    Entity: Office_Depot
    Type: Supplier
    Observations:
      - Booked to account 6815 (Büromaterial)
      - NOTE: User correction from 6800 to 6815
      - Reason: Specific account for office supplies
    """)

    print("\n[Second Invoice: Corrected Suggestion]")
    print("-" * 70)

    mission2 = """
    Rechnung von Office Depot:
    Betrag: 180 EUR
    Beschreibung: Druckerpapier und Ordner
    """

    print(f"\nUser: {mission2.strip()}")
    print("\n[Agent processing...]")

    print("\n[Memory]: Searching for 'Office Depot'...")
    print("[Memory]: ✓ Found: Booked to account 6815 (Büromaterial)")
    print("[Memory]: ✓ Note: Previous correction applied")

    print("\nAgent: Buchungsvorschlag:")
    print("""
    Soll:  6815 (Büromaterial)     180,00 EUR
    Haben: 1200 (Bank)             180,00 EUR

    (Frühere Korrektur berücksichtigt ✓)
    """)

    print("\n✅ Learning in Action:")
    print("   - First time: Wrong suggestion (6800)")
    print("   - User corrected to 6815")
    print("   - Memory stored correction")
    print("   - Second time: Correct suggestion (6815)")


async def example_decision_tracking():
    """
    Example: Documenting and applying business decisions.

    Demonstrates:
    1. Storing complex cost-splitting decisions
    2. Applying decisions automatically
    3. Reminding about review dates
    """
    print("\n\n" + "=" * 70)
    print("EXAMPLE: Decision Tracking & Cost Splitting")
    print("=" * 70)

    factory = AgentFactory()
    agent = await factory.create_agent_with_plugin(
        plugin_path="examples/accounting_agent",
        profile="dev",
    )

    print("\n[Storing Business Decision]")
    print("-" * 70)

    print("\n[Memory]: Creating decision entity...")
    print("""
    Entity: Decision_AWS_Split_Q1_2024
    Type: Decision
    Observations:
      - Decided: 2024-02-01
      - AWS costs split 60/40 between Project A and B
      - Based on: EC2 instance usage analysis
      - Approved by: CTO and CFO
      - Valid: Q1-Q2 2024
      - Review: 2024-06-01

    Relations:
      - applies_to: Amazon_Web_Services
      - affects: Project_A (60%)
      - affects: Project_B (40%)
    """)

    print("\n[Invoice Processing with Decision]")
    print("-" * 70)

    mission = """
    AWS Rechnung März 2024:
    Betrag: 3.000 EUR
    Beschreibung: Cloud Services
    """

    print(f"\nUser: {mission.strip()}")
    print("\n[Agent processing...]")

    print("\n[Memory]: Searching for 'AWS split decision'...")
    print("[Memory]: ✓ Found: Decision_AWS_Split_Q1_2024")
    print("[Memory]: ✓ Split ratio: 60/40")
    print("[Memory]: ✓ Review date: 2024-06-01")

    print("\nAgent: Ich wende die genehmigte Aufteilung an:")
    print("""
    Entscheidung vom 01.02.2024:

    Buchungsvorschlag:
    Soll:  6805 (IT-Kosten)  1.800 EUR  [KST 4100, Projekt A] (60%)
    Soll:  6805 (IT-Kosten)  1.200 EUR  [KST 4200, Projekt B] (40%)
    Haben: 1200 (Bank)       3.000 EUR

    ⚠️ Hinweis: Review dieser Aufteilung fällig am 01.06.2024
    """)

    print("\n✅ Decision Benefits:")
    print("   - Complex splitting rules stored once")
    print("   - Applied automatically each month")
    print("   - Review reminders included")
    print("   - Audit trail of approval")


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("ACCOUNTING AGENT - LONG-TERM MEMORY EXAMPLES")
    print("=" * 70)
    print("\nThis demo shows how memory enables the agent to:")
    print("  • Learn from past bookings")
    print("  • Provide context-aware suggestions")
    print("  • Apply complex business rules")
    print("  • Improve accuracy over time")
    print("\n" + "=" * 70)

    # Run examples
    await example_learning_workflow()
    await example_project_allocation()
    await example_learning_from_corrections()
    await example_decision_tracking()

    print("\n\n" + "=" * 70)
    print("SUMMARY: Memory-Enhanced Accounting")
    print("=" * 70)

    print("""
    With long-term memory, the accounting agent becomes:

    1. **Self-Learning**: Adapts to your specific workflows
    2. **Context-Aware**: Understands relationships between suppliers, projects, accounts
    3. **Consistent**: Applies rules uniformly across all invoices
    4. **Auditable**: Tracks decisions and their rationale
    5. **Efficient**: Reduces manual input over time

    Memory File Location: .taskforce_accounting/.memory/knowledge_graph.jsonl
    """)

    print("\n" + "=" * 70)
    print("To enable memory in your accounting agent:")
    print("  1. Ensure Node.js and NPM are installed")
    print("  2. Check configs/accounting_agent.yaml for mcp_servers section")
    print("  3. Run: taskforce run mission '...' --plugin examples/accounting_agent")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
