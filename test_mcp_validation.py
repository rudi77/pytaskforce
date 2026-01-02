"""
End-to-end validation script for MCP filesystem server integration.

This script validates Story 2.3 acceptance criteria:
1. Agent can list files in test directory using MCP tools
2. Agent can read file contents using MCP tools
3. MCP tools are properly integrated with the agent

Usage:
    cd taskforce
    uv run python test_mcp_validation.py
"""

import asyncio
import sys
from pathlib import Path

import structlog

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from taskforce.application.factory import AgentFactory


async def main():
    """Run MCP validation tests."""
    logger = structlog.get_logger()
    
    logger.info("=== MCP Filesystem Server Validation ===")
    logger.info("Story 2.3: Validating MCP integration with filesystem server")
    
    try:
        # Create agent with dev profile (includes MCP filesystem server)
        logger.info("Creating agent with dev profile...")
        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_agent(profile="dev")
        
        # List available tools to confirm MCP tools are loaded
        logger.info("Listing available tools...")
        tool_names = list(agent.tools.keys())
        logger.info(f"Available tools ({len(tool_names)}): {', '.join(tool_names)}")
        
        # Check for MCP tools
        mcp_tools = [name for name in tool_names if "directory" in name.lower() or ("file" in name.lower() and "read_file" in name.lower())]
        if mcp_tools:
            logger.info(f"✓ MCP tools detected: {', '.join(mcp_tools)}")
        else:
            logger.warning("⚠ No obvious MCP tools detected (check tool names)")
        
        # Test 1: List files in test directory
        logger.info("\n=== Test 1: List files in test directory ===")
        mission_1 = "List all files in the .mcp_test_data directory"
        logger.info(f"Mission: {mission_1}")
        
        session_id_1 = "mcp-validation-test-1"
        result_1 = await agent.execute(mission=mission_1, session_id=session_id_1)
        
        logger.info(f"Test 1 Result: {result_1.status}")
        logger.info(f"Test 1 Output: {result_1.final_message}")
        if result_1.status == "completed":
            logger.info("✓ Test 1 PASSED: Successfully listed files")
        else:
            logger.error(f"✗ Test 1 FAILED: Status={result_1.status}")
        
        # Test 2: Read a file
        logger.info("\n=== Test 2: Read file contents ===")
        mission_2 = "Read the contents of .mcp_test_data/sample.txt and tell me what it says"
        logger.info(f"Mission: {mission_2}")
        
        session_id_2 = "mcp-validation-test-2"
        result_2 = await agent.execute(mission=mission_2, session_id=session_id_2)
        
        logger.info(f"Test 2 Result: {result_2.status}")
        logger.info(f"Test 2 Output: {result_2.final_message}")
        if result_2.status == "completed":
            logger.info("✓ Test 2 PASSED: Successfully read file")
        else:
            logger.error(f"✗ Test 2 FAILED: Status={result_2.status}")
        
        # Summary
        logger.info("\n=== Validation Summary ===")
        test_1_passed = result_1.status == "completed"
        test_2_passed = result_2.status == "completed"
        
        if test_1_passed and test_2_passed:
            logger.info("✓ ALL TESTS PASSED - MCP integration validated successfully")
            return 0
        else:
            logger.error("✗ SOME TESTS FAILED - Review logs above")
            return 1
            
    except Exception as e:
        logger.error(f"Validation failed with exception: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

