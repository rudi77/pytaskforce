"""Test script to demonstrate the enhanced CLI UI.

This script shows all the different output formats and styles
available in the Taskforce CLI.

Run with:
    python test_cli_ui.py
"""

from taskforce.api.cli.output_formatter import TaskforceConsole


def demo_basic_output():
    """Demonstrate basic output styles."""
    console = TaskforceConsole(debug=False)
    
    print("\n" + "="*60)
    print("DEMO 1: Basic Output (Debug OFF)")
    print("="*60 + "\n")
    
    console.print_banner()
    console.print_system_message("Welcome to Taskforce CLI Demo!", "system")
    console.print_divider()
    
    # User message
    console.print_user_message("Can you analyze the sales data from Q4 2024?")
    
    # Agent response
    console.print_agent_message(
        "I'll analyze the Q4 2024 sales data for you. "
        "Let me start by reading the file and performing statistical analysis."
    )
    
    # Success message
    console.print_success("Analysis completed successfully!")
    
    # Warning
    console.print_warning("Some data points were missing and have been interpolated.")
    
    # System info
    console.print_system_message("Session saved", "info")


def demo_debug_output():
    """Demonstrate debug mode output."""
    console = TaskforceConsole(debug=True)
    
    print("\n" + "="*60)
    print("DEMO 2: Debug Output (Debug ON)")
    print("="*60 + "\n")
    
    console.print_banner()
    console.print_system_message("Debug mode enabled - showing agent internals", "system")
    console.print_divider()
    
    # Session info
    console.print_session_info(
        session_id="demo-session-123",
        profile="dev",
        user_context={"user_id": "john-doe", "org_id": "acme-corp"}
    )
    
    # User message
    console.print_user_message("What's the weather like today?")
    
    # Agent thought (only visible in debug mode)
    console.print_agent_message(
        "I'll check the weather for you using the web search tool.",
        thought="The user is asking about weather. I need to:\n"
                "1. Use WebSearchTool to find current weather\n"
                "2. Parse the results\n"
                "3. Format a clear response"
    )
    
    # Action (only visible in debug mode)
    console.print_action(
        "tool_call",
        "WebSearchTool.execute(query='current weather')"
    )
    
    # Observation (only visible in debug mode)
    console.print_observation(
        "Search results: Temperature: 72°F, Conditions: Sunny, "
        "Humidity: 45%, Wind: 5 mph"
    )
    
    # Debug message
    console.print_debug("Tool execution completed in 1.2 seconds")
    
    # Final response
    console.print_agent_message(
        "The current weather is sunny with a temperature of 72°F. "
        "It's a beautiful day!"
    )


def demo_error_handling():
    """Demonstrate error handling and messages."""
    console = TaskforceConsole(debug=True)
    
    print("\n" + "="*60)
    print("DEMO 3: Error Handling")
    print("="*60 + "\n")
    
    console.print_banner()
    console.print_divider("Error Scenarios")
    
    # Simple error
    console.print_error("Failed to connect to database")
    
    # Error with exception (debug mode)
    try:
        raise ValueError("Invalid configuration parameter")
    except Exception as e:
        console.print_error("Configuration error occurred", exception=e)


def demo_all_styles():
    """Show all available message styles."""
    console = TaskforceConsole(debug=True)
    
    print("\n" + "="*60)
    print("DEMO 4: All Message Styles")
    print("="*60 + "\n")
    
    console.print_banner()
    console.print_divider("Message Style Showcase")
    
    console.print_user_message("This is a user message")
    console.print_agent_message("This is an agent message")
    console.print_agent_message(
        "This is an agent message with thought",
        thought="This is the agent's internal reasoning process"
    )
    console.print_system_message("This is a system message", "system")
    console.print_system_message("This is an info message", "info")
    console.print_success("This is a success message")
    console.print_warning("This is a warning message")
    console.print_error("This is an error message")
    console.print_debug("This is a debug message")
    console.print_action("tool_call", "PythonTool.execute(code='print(42)')")
    console.print_observation("Result: 42")
    
    console.print_divider()
    console.print_system_message("Demo complete!", "success")


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("TASKFORCE CLI UI DEMONSTRATION")
    print("=" * 60)
    
    demo_basic_output()
    input("\nPress Enter to continue to next demo...")
    
    demo_debug_output()
    input("\nPress Enter to continue to next demo...")
    
    demo_error_handling()
    input("\nPress Enter to continue to next demo...")
    
    demo_all_styles()
    
    print("\n" + "="*60)
    print("All demos completed!")
    print("="*60 + "\n")
    
    print("Try it yourself:")
    print("  taskforce chat                    # Normal mode")
    print("  taskforce --debug chat            # Debug mode")
    print("  taskforce run mission 'Test'      # Execute mission")
    print("  taskforce version                 # Show version with banner")
    print()


if __name__ == "__main__":
    main()

