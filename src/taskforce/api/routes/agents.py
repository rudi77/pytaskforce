"""
Agent Registry API Routes
==========================

HTTP endpoints for managing custom agent definitions.

Endpoints:
- POST /api/v1/agents - Create custom agent
- GET /api/v1/agents - List all agents (custom + profile)
- GET /api/v1/agents/{agent_id} - Get agent by ID
- PUT /api/v1/agents/{agent_id} - Update custom agent
- DELETE /api/v1/agents/{agent_id} - Delete custom agent

Story: 8.1 - Custom Agent Registry (CRUD + YAML Persistence)
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from taskforce.api.schemas.agent_schemas import (
    AgentListResponse,
    CustomAgentCreate,
    CustomAgentResponse,
    CustomAgentUpdate,
    ProfileAgentResponse,
)
from taskforce.application.tool_catalog import get_tool_catalog
from taskforce.infrastructure.persistence.file_agent_registry import (
    FileAgentRegistry,
)

router = APIRouter()

# Singleton registry instance
_registry = FileAgentRegistry()


def _validate_tool_allowlists(
    tool_allowlist: list[str],
    mcp_servers: list[dict],
    mcp_tool_allowlist: list[str],
) -> None:
    """
    Validate tool allowlists against the tool catalog.

    Args:
        tool_allowlist: List of native tool names
        mcp_servers: List of MCP server configurations
        mcp_tool_allowlist: List of MCP tool names

    Raises:
        HTTPException 400: If validation fails with details
    """
    catalog = get_tool_catalog()

    # Validate native tools
    if tool_allowlist:
        is_valid, invalid_tools = catalog.validate_native_tools(
            tool_allowlist
        )
        if not is_valid:
            available_tools = sorted(catalog.get_native_tool_names())
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_tools",
                    "message": "Unknown tool(s) in tool_allowlist",
                    "invalid_tools": invalid_tools,
                    "available_tools": available_tools,
                },
            )

    # Validate MCP tools if MCP servers are configured
    if mcp_servers and mcp_tool_allowlist:
        # For MVP: Basic validation that mcp_tool_allowlist is provided
        # Full MCP discovery validation would require MCP client
        # initialization which is deferred to agent factory instantiation
        # Story requirement: "graceful degradation" - we allow storing
        pass


@router.post(
    "/agents",
    response_model=CustomAgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create custom agent",
    description="Create a new custom agent definition and persist as YAML",
)
def create_agent(agent_def: CustomAgentCreate) -> CustomAgentResponse:
    """
    Create a new custom agent.

    Args:
        agent_def: Agent definition with required fields

    Returns:
        Created agent with timestamps

    Raises:
        HTTPException 409: If agent_id already exists
        HTTPException 400: If validation fails (including invalid tools)
    """
    # Validate tool allowlists
    _validate_tool_allowlists(
        agent_def.tool_allowlist,
        agent_def.mcp_servers,
        agent_def.mcp_tool_allowlist,
    )

    try:
        return _registry.create_agent(agent_def)
    except FileExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent: {str(e)}",
        )


@router.get(
    "/agents",
    response_model=AgentListResponse,
    summary="List all agents",
    description=(
        "List all agents (custom + profile). "
        "Corrupt YAML files are skipped."
    ),
)
def list_agents() -> AgentListResponse:
    """
    List all available agents.

    Returns custom agents from configs/custom/*.yaml and profile agents
    from configs/*.yaml (excluding llm_config.yaml).

    Returns:
        List of all agent definitions with discriminator field 'source'
    """
    agents = _registry.list_agents()
    return AgentListResponse(agents=agents)


@router.get(
    "/agents/{agent_id}",
    response_model=CustomAgentResponse | ProfileAgentResponse,
    summary="Get agent by ID",
    description="Retrieve a specific agent definition by ID",
)
def get_agent(
    agent_id: str,
) -> CustomAgentResponse | ProfileAgentResponse:
    """
    Get an agent by ID.

    Searches custom agents first, then profile agents.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent definition

    Raises:
        HTTPException 404: If agent not found
    """
    agent = _registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent


@router.put(
    "/agents/{agent_id}",
    response_model=CustomAgentResponse,
    summary="Update custom agent",
    description="Update an existing custom agent definition",
)
def update_agent(
    agent_id: str, agent_def: CustomAgentUpdate
) -> CustomAgentResponse:
    """
    Update an existing custom agent.

    Args:
        agent_id: Agent identifier to update
        agent_def: New agent definition

    Returns:
        Updated agent with new updated_at timestamp

    Raises:
        HTTPException 404: If agent not found
        HTTPException 400: If validation fails (including invalid tools)
    """
    # Validate tool allowlists
    _validate_tool_allowlists(
        agent_def.tool_allowlist,
        agent_def.mcp_servers,
        agent_def.mcp_tool_allowlist,
    )

    try:
        return _registry.update_agent(agent_id, agent_def)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update agent: {str(e)}",
        )


@router.delete(
    "/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete custom agent",
    description="Delete a custom agent definition",
)
def delete_agent(agent_id: str) -> Response:
    """
    Delete a custom agent.

    Args:
        agent_id: Agent identifier to delete

    Returns:
        204 No Content on success

    Raises:
        HTTPException 404: If agent not found
    """
    try:
        _registry.delete_agent(agent_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

