"""
Agent Template Routes
=====================

Read-only catalog of curated agent starting points used by the new-agent
wizard. Templates bundle a recommended capability set and a system-prompt
skeleton; the wizard pre-fills the form from these and lets the user adjust.

Endpoints:
- GET /api/v1/agent-templates           -- list all templates
- GET /api/v1/agent-templates/{id}      -- single template

The compose-prompt helper for step 4 of the wizard lives next to these so
both wizard endpoints stay together.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.agent_templates import (
    AgentTemplate,
    get_template,
    list_templates,
)

router = APIRouter()


class AgentTemplateResponse(BaseModel):
    """One curated starting point for the wizard."""

    id: str
    name: str
    description: str
    emoji: str
    persona_hint: str
    recommended_tools: list[str]
    recommended_skills: list[str]
    system_prompt_template: str
    example_prompts: list[str]
    tone_default: str
    language_default: str

    @classmethod
    def from_domain(cls, template: AgentTemplate) -> "AgentTemplateResponse":
        return cls(
            id=template.id,
            name=template.name,
            description=template.description,
            emoji=template.emoji,
            persona_hint=template.persona_hint,
            recommended_tools=list(template.recommended_tools),
            recommended_skills=list(template.recommended_skills),
            system_prompt_template=template.system_prompt_template,
            example_prompts=list(template.example_prompts),
            tone_default=template.tone_default,
            language_default=template.language_default,
        )


class AgentTemplateListResponse(BaseModel):
    templates: list[AgentTemplateResponse]


@router.get(
    "/agent-templates",
    response_model=AgentTemplateListResponse,
    summary="List agent templates for the wizard",
)
def list_agent_templates() -> AgentTemplateListResponse:
    """Return all wizard templates, filtered to tools the server can resolve."""
    templates = [AgentTemplateResponse.from_domain(t) for t in list_templates()]
    return AgentTemplateListResponse(templates=templates)


@router.get(
    "/agent-templates/{template_id}",
    response_model=AgentTemplateResponse,
    summary="Get a single agent template",
)
def get_agent_template(template_id: str) -> AgentTemplateResponse:
    template = get_template(template_id)
    if template is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="template_not_found",
            message=f"Agent template '{template_id}' not found.",
        )
    return AgentTemplateResponse.from_domain(template)


# ---------------------------------------------------------------------------
# Compose-prompt helper (wizard step 4)
# ---------------------------------------------------------------------------


class ComposePromptRequest(BaseModel):
    """Inputs from wizard step 4."""

    template_id: str | None = Field(
        default=None,
        description="Template id (the user's starting point) or null for a blank agent.",
    )
    description: str = Field(
        default="",
        description="What the user said the agent should do (free text).",
    )
    tone: str = Field(default="professionell", description="professionell | locker | formell")
    language: str = Field(default="Deutsch", description="Output language for the agent.")
    rules: str = Field(
        default="",
        description="Additional rules the user typed in (one per line).",
    )
    use_ai: bool = Field(
        default=False,
        description=(
            "If true, run an LLM call to refine the prompt. Otherwise compose "
            "deterministically from template + inputs."
        ),
    )


class ComposePromptResponse(BaseModel):
    system_prompt: str
    used_ai: bool


def _deterministic_compose(req: ComposePromptRequest) -> str:
    """Compose a system prompt deterministically (no LLM call)."""
    parts: list[str] = []
    template_body = ""
    if req.template_id:
        template = get_template(req.template_id)
        if template is not None:
            template_body = template.system_prompt_template.strip()
    if template_body:
        parts.append(template_body)

    if req.description.strip():
        parts.append(f"Was du für den Nutzer tust:\n{req.description.strip()}")

    style_lines: list[str] = []
    if req.tone:
        style_lines.append(f"Tonfall: {req.tone}")
    if req.language:
        style_lines.append(f"Antworte standardmäßig auf: {req.language}")
    if style_lines:
        parts.append("Stil:\n" + "\n".join(f"- {line}" for line in style_lines))

    if req.rules.strip():
        rule_lines = [
            line.strip().lstrip("-• ").strip()
            for line in req.rules.splitlines()
            if line.strip()
        ]
        if rule_lines:
            parts.append("Wichtige Regeln:\n" + "\n".join(f"- {line}" for line in rule_lines))

    return "\n\n".join(parts).strip() + "\n"


async def _ai_compose(req: ComposePromptRequest, deterministic: str) -> str:
    """Refine the deterministic prompt via LLM. Returns deterministic on failure."""
    try:
        from taskforce.infrastructure.llm.litellm_service import LiteLLMService
    except Exception:  # noqa: BLE001
        return deterministic

    instruction = (
        "Du bist ein Prompt-Engineer. Schreibe den folgenden System-Prompt "
        "für einen AI-Agenten so um, dass er klar, knapp und handlungsorientiert "
        "ist. Behalte die Sprache des Originals bei. Erfinde keine Tools oder "
        "Fähigkeiten dazu. Antworte AUSSCHLIESSLICH mit dem fertigen Prompt-Text, "
        "ohne Anführungszeichen oder Markdown-Codeblock.\n\n"
        f"Beschreibung des Nutzers: {req.description or '(keine)'}\n"
        f"Gewünschter Tonfall: {req.tone}\n"
        f"Antwortsprache: {req.language}\n"
        f"Regeln des Nutzers: {req.rules or '(keine)'}\n\n"
        "Aktueller Prompt-Entwurf:\n"
        f"{deterministic}"
    )

    try:
        service = LiteLLMService()
        result = await service.complete(
            messages=[{"role": "user", "content": instruction}],
            tools=None,
            model="main",
        )
    except Exception:  # noqa: BLE001
        return deterministic

    if not isinstance(result, dict) or not result.get("success"):
        return deterministic
    text = (result.get("content") or "").strip()
    if not text:
        return deterministic
    return text + ("\n" if not text.endswith("\n") else "")


@router.post(
    "/agent-templates/compose-prompt",
    response_model=ComposePromptResponse,
    summary="Compose a system prompt from wizard step 4 inputs",
)
async def compose_prompt(request: ComposePromptRequest) -> ComposePromptResponse:
    """Turn the user's tone/language/rules into a ready-to-use system prompt.

    With ``use_ai=false`` the response is deterministic (no LLM call). With
    ``use_ai=true`` the deterministic draft is sent to the LLM for one
    refinement pass; if the call fails the deterministic version is returned
    so the wizard never blocks on a missing API key.
    """
    deterministic = _deterministic_compose(request)
    if not request.use_ai:
        return ComposePromptResponse(system_prompt=deterministic, used_ai=False)

    refined = await _ai_compose(request, deterministic)
    used_ai = refined.strip() != deterministic.strip()
    return ComposePromptResponse(system_prompt=refined, used_ai=used_ai)
