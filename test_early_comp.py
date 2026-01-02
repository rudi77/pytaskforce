"""
Test script to verify early completion persistence.
"""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from taskforce.application.factory import AgentFactory
from taskforce.core.interfaces.todolist import TaskStatus
from taskforce.core.domain.plan import TodoItem, TodoList


async def test_early_completion():
    """Test that early completion correctly persists skipped tasks."""
    print("Creating agent...")
    factory = AgentFactory()
    agent = factory.create_agent(profile="dev")

    session_id = "test-early-complete"

    # Create a todolist with 2 items
    items = [
        TodoItem(position=1, description="Step 1", acceptance_criteria="Done", dependencies=[], status=TaskStatus.PENDING),
        TodoItem(position=2, description="Step 2", acceptance_criteria="Done", dependencies=[], status=TaskStatus.PENDING),
    ]
    todolist = TodoList(
        mission="Test", 
        items=items, 
        todolist_id="test-list-1",
        open_questions=[],
        notes=""
    )
    
    # Save it via manager
    await agent.todolist_manager.update_todolist(todolist)
    print(f"Created todolist: {todolist.todolist_id}")
    
    # Simulate Agent.execute logic for early completion
    print("\n=== Simulating Early Completion ===")
    
    # Mark step 1 complete
    step1 = todolist.items[0]
    step1.status = TaskStatus.COMPLETED
    
    # Mark remaining steps skipped (logic from Agent.execute)
    for step in todolist.items:
        if step.status == TaskStatus.PENDING:
            step.status = TaskStatus.SKIPPED
            print(f"Marked step {step.position} as SKIPPED")
            
    # Debug: Check to_dict content
    print(f"DEBUG to_dict before save: {json.dumps(todolist.to_dict(), indent=2)}")

    # Update via manager
    await agent.todolist_manager.update_todolist(todolist)
    print("Updated todolist via manager")
    
    # Now verify loading
    print("\n=== Verifying Load ===")
    loaded_list = await agent.todolist_manager.load_todolist(todolist.todolist_id)
    
    print(f"Loaded ID: {loaded_list.todolist_id}")
    for item in loaded_list.items:
        print(f"Step {item.position}: {item.status}")
        
    # Check _is_plan_complete
    is_complete = agent._is_plan_complete(loaded_list)
    print(f"\nIs plan complete? {is_complete}")
    
    if is_complete:
        print("OK: Logic works correctly!")
    else:
        print("FAIL: Logic failed - plan should be complete!")


if __name__ == "__main__":
    asyncio.run(test_early_completion())
