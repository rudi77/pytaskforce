"""Build an A2A ``AgentCard`` from a Taskforce profile.

The card published at ``/.well-known/agent-card.json`` is derived from
profile metadata (name, description, declared tools) plus the
``a2a.server`` config block (auth scheme, advertised callback URL).
Tools surface as :class:`a2a.types.AgentSkill` so remote clients can
discover what the agent can do without needing a Taskforce-specific
schema.
"""

from __future__ import annotations

from typing import Any

from taskforce.application.config_schema import A2aAuthSchema, A2aServerSchema
from taskforce.infrastructure.a2a._sdk import load_types


def build_agent_card(
    *,
    profile_name: str,
    description: str,
    base_url: str,
    server_config: A2aServerSchema,
    tools: list[str],
    version: str = "1.0.0",
) -> Any:
    """Construct an ``a2a.types.AgentCard`` proto for the local server.

    Tools become :class:`AgentSkill` entries; capabilities advertise
    streaming + push-notification support; ``securitySchemes`` is
    derived from ``server_config.auth``.
    """
    types = load_types()
    name = server_config.agent_name or profile_name
    desc = server_config.agent_description or description or f"Taskforce profile {profile_name!r}"
    card = types.AgentCard(
        name=name,
        description=desc,
        version=version,
    )
    card.capabilities.streaming = True
    card.capabilities.push_notifications = True
    skills = [_skill_for_tool(t, types) for t in tools]
    card.skills.extend(skills)
    card.default_input_modes.append("text/plain")
    card.default_output_modes.append("text/plain")
    _apply_security(card, server_config.auth, types)
    interface = card.supported_interfaces.add()
    interface.protocol_binding = "JSONRPC"
    interface.url = base_url.rstrip("/")
    return card


def _skill_for_tool(tool_name: str, types: Any) -> Any:
    skill = types.AgentSkill(
        id=tool_name,
        name=tool_name.replace("_", " ").title(),
        description=f"Invoke the {tool_name!r} tool on the Taskforce agent",
    )
    skill.tags.append("taskforce")
    skill.input_modes.append("text/plain")
    skill.output_modes.append("text/plain")
    return skill


def _apply_security(card: Any, auth: A2aAuthSchema, types: Any) -> None:
    if auth.type == "none":
        return
    requirement = card.security_requirements.add()
    if auth.type == "bearer":
        requirement.schemes["bearer"].list.append("")
        card.security_schemes["bearer"].http_auth_security_scheme.scheme = "Bearer"
    elif auth.type == "api_key":
        requirement.schemes["api_key"].list.append("")
        api = card.security_schemes["api_key"].api_key_security_scheme
        api.name = auth.api_key_header or "X-API-Key"
        api.location = "header"
    elif auth.type == "oauth2":
        scopes_list = requirement.schemes["oauth2"].list
        if auth.scopes:
            scopes_list.extend(auth.scopes)
        else:
            scopes_list.append("")
        flow = card.security_schemes["oauth2"].oauth2_security_scheme.flows.client_credentials
        if auth.token_url:
            flow.token_url = auth.token_url
        for sc in auth.scopes:
            flow.scopes[sc] = sc
    elif auth.type == "oidc":
        requirement.schemes["oidc"].list.append("")
        oidc = card.security_schemes["oidc"].open_id_connect_security_scheme
        if auth.token_url:
            oidc.open_id_connect_url = auth.token_url
    elif auth.type == "mtls":
        requirement.schemes["mtls"].list.append("")
        card.security_schemes["mtls"].mtls_security_scheme.SetInParent()
