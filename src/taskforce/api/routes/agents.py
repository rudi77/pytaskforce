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

Clean Architecture Notes:
- Uses Domain Models from core/domain/agent_models.py
- Converts between API schemas and Domain models
- Uses Depends() for dependency injection (no module-level singletons)
- No direct infrastructure imports (registry provided via dependencies.py)
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from taskforce.api.dependencies import get_agent_registry
from taskforce.api.errors import http_exception as _http_exception
from taskforce.api.schemas.agent_schemas import (
    AgentListResponse,
    CustomAgentCreate,
    CustomAgentResponse,
    CustomAgentUpdate,
    PluginAgentResponse,
    ProfileAgentResponse,
)
from taskforce.application.tool_registry import get_tool_registry
from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    PluginAgentDefinition,
    ProfileAgentDefinition,
)

router = APIRouter()


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
    catalog = get_tool_registry()

    # Validate native tools
    if tool_allowlist:
        is_valid, invalid_tools = catalog.validate_native_tools(
            tool_allowlist
        )
        if not is_valid:
            available_tools = sorted(catalog.get_native_tool_names())
            raise _http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_tools",
                message="Unknown tool(s) in tool_allowlist",
                details={
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


def _domain_to_response(
    domain: CustomAgentDefinition | ProfileAgentDefinition | PluginAgentDefinition,
) -> CustomAgentResponse | ProfileAgentResponse | PluginAgentResponse:
    """Convert a domain model to an API response schema."""
    if isinstance(domain, CustomAgentDefinition):
        return CustomAgentResponse.from_domain(domain)
    elif isinstance(domain, PluginAgentDefinition):
        return PluginAgentResponse.from_domain(domain)
    else:
        return ProfileAgentResponse.from_domain(domain)


@router.post(
    "/agents",
    response_model=CustomAgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create custom agent",
    description="Create a new custom agent definition and persist as YAML",
)
def create_agent(
    agent_def: CustomAgentCreate,
    registry=Depends(get_agent_registry),
) -> CustomAgentResponse:
    """
    Create a new custom agent.

    Args:
        agent_def: Agent definition with required fields
        registry: Injected agent registry

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
        # Convert API schema to domain input
        domain_input = agent_def.to_domain()
        # Create via registry (returns domain model)
        domain_result = registry.create_agent(domain_input)
        # Convert domain model to API response
        return CustomAgentResponse.from_domain(domain_result)
    except FileExistsError as e:
        raise _http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="agent_exists",
            message=str(e),
        )
    except Exception as e:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="create_failed",
            message=f"Failed to create agent: {str(e)}",
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
def list_agents(
    registry=Depends(get_agent_registry),
) -> AgentListResponse:
    """
    List all available agents.

    Returns custom agents from configs/custom/*.yaml and profile agents
    from configs/*.yaml (excluding llm_config.yaml).

    Args:
        registry: Injected agent registry

    Returns:
        List of all agent definitions with discriminator field 'source'
    """
    domain_agents = registry.list_agents()
    # Convert domain models to API responses
    api_agents = [_domain_to_response(agent) for agent in domain_agents]
    return AgentListResponse(agents=api_agents)


@router.get(
    "/agents/{agent_id}",
    response_model=CustomAgentResponse | ProfileAgentResponse | PluginAgentResponse,
    summary="Get agent by ID",
    description="Retrieve a specific agent definition by ID",
)
def get_agent(
    agent_id: str,
    registry=Depends(get_agent_registry),
) -> CustomAgentResponse | ProfileAgentResponse | PluginAgentResponse:
    """
    Get an agent by ID.

    Searches custom agents first, then profile agents.

    Args:
        agent_id: Agent identifier
        registry: Injected agent registry

    Returns:
        Agent definition

    Raises:
        HTTPException 404: If agent not found
    """
    domain_agent = registry.get_agent(agent_id)
    if not domain_agent:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"Agent '{agent_id}' not found",
        )
    return _domain_to_response(domain_agent)


@router.put(
    "/agents/{agent_id}",
    response_model=CustomAgentResponse,
    summary="Update custom agent",
    description="Update an existing custom agent definition",
)
def update_agent(
    agent_id: str,
    agent_def: CustomAgentUpdate,
    registry=Depends(get_agent_registry),
) -> CustomAgentResponse:
    """
    Update an existing custom agent.

    Args:
        agent_id: Agent identifier to update
        agent_def: New agent definition
        registry: Injected agent registry

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
        # Convert API schema to domain input
        domain_input = agent_def.to_domain()
        # Update via registry (returns domain model)
        domain_result = registry.update_agent(agent_id, domain_input)
        # Convert domain model to API response
        return CustomAgentResponse.from_domain(domain_result)
    except FileNotFoundError as e:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e),
        )
    except Exception as e:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="update_failed",
            message=f"Failed to update agent: {str(e)}",
        )


@router.delete(
    "/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete custom agent",
    description="Delete a custom agent definition",
)
def delete_agent(
    agent_id: str,
    registry=Depends(get_agent_registry),
) -> Response:
    """
    Delete a custom agent.

    Args:
        agent_id: Agent identifier to delete
        registry: Injected agent registry

    Returns:
        204 No Content on success

    Raises:
        HTTPException 404: If agent not found
    """
    try:
        registry.delete_agent(agent_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except FileNotFoundError as e:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e),
        )
