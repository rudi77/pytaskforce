"""
Context Display Service
========================

Collects and structures the full LLM context (system prompt, messages,
tools, token budget) into a typed snapshot that CLI or API layers can
render to the user.

This enables the ``/context`` chat command which shows everything that
would be sent to the LLM on the next call, broken down by category with
estimated token counts — similar to the context display in Claude Code CLI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from taskforce.core.tools.tool_converter import tools_to_openai_format


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextSubsection:
    """A labelled subsection with its raw content and token estimate."""

    name: str
    content: str
    token_estimate: int


@dataclass(frozen=True)
class ContextSection:
    """A top-level section of the LLM context."""

    name: str
    content: str
    token_estimate: int
    subsections: list[ContextSubsection] = field(default_factory=list)


@dataclass(frozen=True)
class ContextSnapshot:
    """Complete snapshot of what would be sent to the LLM."""

    sections: list[ContextSection]
    total_tokens: int
    max_tokens: int
    utilization_pct: float
    model_alias: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4  # Same heuristic as TokenBudgeter


def _estimate_tokens(text: str) -> int:
    """Estimate tokens using the project-wide chars/4 heuristic."""
    return len(text) // CHARS_PER_TOKEN


def _extract_xml_section(text: str, tag: str) -> str | None:
    """Extract content between ``<Tag>…</Tag>`` markers (case-sensitive)."""
    pattern = rf"<{tag}>\s*(.*?)\s*</{tag}>"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ContextDisplayService:
    """Build a :class:`ContextSnapshot` from an agent and its session state.

    The service is intentionally **stateless** — it reads from the agent and
    the state manager each time ``build_snapshot`` is called so that the
    snapshot always reflects the *current* context.
    """

    async def build_snapshot(
        self,
        agent: Any,
        session_id: str,
    ) -> ContextSnapshot:
        """Collect every piece of context that would be sent to the LLM.

        Args:
            agent: An ``Agent`` (or ``LeanAgent``) instance.
            session_id: Active session identifier (used to load history).

        Returns:
            A fully populated :class:`ContextSnapshot`.
        """
        # -- Load conversation history from state --------------------------
        state = await agent.state_manager.load_state(session_id) or {}
        history: list[dict[str, Any]] = state.get("conversation_history", [])

        # -- Build the system prompt (exactly as the agent would) ----------
        system_prompt = agent._build_system_prompt(
            mission=None,
            state=state,
            messages=history,
        )

        # -- Sections ------------------------------------------------------
        sections: list[ContextSection] = []

        # 1. System Prompt
        system_section = self._build_system_prompt_section(system_prompt, agent)
        sections.append(system_section)

        # 2. Conversation History
        history_section = self._build_history_section(history)
        sections.append(history_section)

        # 3. Tool Definitions (OpenAI function-calling format)
        tool_section = self._build_tool_definitions_section(agent)
        sections.append(tool_section)

        # -- Totals --------------------------------------------------------
        total_tokens = sum(s.token_estimate for s in sections)
        max_tokens: int = getattr(
            agent.token_budgeter, "max_input_tokens", 100_000
        )
        utilization = (total_tokens / max_tokens * 100) if max_tokens else 0.0
        model_alias: str = getattr(agent, "model_alias", "main")

        return ContextSnapshot(
            sections=sections,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            utilization_pct=round(utilization, 1),
            model_alias=model_alias,
        )

    # -- Private helpers ---------------------------------------------------

    def _build_system_prompt_section(
        self,
        system_prompt: str,
        agent: Any,
    ) -> ContextSection:
        """Parse the system prompt into labelled subsections."""
        subsections: list[ContextSubsection] = []

        # Base / Kernel prompt (inside <Base>…</Base>)
        base_content = _extract_xml_section(system_prompt, "Base")
        if base_content:
            # Try to separate specialist / custom portion
            subsections.append(
                ContextSubsection(
                    name="Base Kernel Prompt",
                    content=base_content,
                    token_estimate=_estimate_tokens(base_content),
                )
            )

        # Tools description (inside <ToolsDescription>…</ToolsDescription>)
        tools_desc = _extract_xml_section(system_prompt, "ToolsDescription")
        if tools_desc:
            tool_count = tools_desc.count("Tool: ")
            label = f"Tool Descriptions ({tool_count} tools)" if tool_count else "Tool Descriptions"
            subsections.append(
                ContextSubsection(
                    name=label,
                    content=tools_desc,
                    token_estimate=_estimate_tokens(tools_desc),
                )
            )

        # Available skills metadata
        skills_meta = _extract_xml_section(system_prompt, "AvailableSkills")
        if skills_meta:
            subsections.append(
                ContextSubsection(
                    name="Available Skills",
                    content=skills_meta,
                    token_estimate=_estimate_tokens(skills_meta),
                )
            )

        # Active skill instructions
        active_skills = _extract_xml_section(system_prompt, "ActiveSkills")
        if active_skills:
            subsections.append(
                ContextSubsection(
                    name="Active Skills",
                    content=active_skills,
                    token_estimate=_estimate_tokens(active_skills),
                )
            )

        # Plan status (injected by LeanPromptBuilder)
        plan_match = re.search(
            r"## CURRENT PLAN STATUS\s*(.*?)(?=\n\n##|\n\n<|\Z)",
            system_prompt,
            re.DOTALL,
        )
        if plan_match:
            plan_text = plan_match.group(1).strip()
            subsections.append(
                ContextSubsection(
                    name="Plan Status",
                    content=plan_text,
                    token_estimate=_estimate_tokens(plan_text),
                )
            )

        # Context pack (injected by LeanPromptBuilder)
        ctx_match = re.search(
            r"## CONTEXT PACK \(BUDGETED\)\s*(.*?)(?=\n\n##|\n\n#\s|\Z)",
            system_prompt,
            re.DOTALL,
        )
        if ctx_match:
            ctx_text = ctx_match.group(1).strip()
            subsections.append(
                ContextSubsection(
                    name="Context Pack",
                    content=ctx_text,
                    token_estimate=_estimate_tokens(ctx_text),
                )
            )

        # Active Skill injected by Agent._build_system_prompt (outside XML)
        skill_header_match = re.search(
            r"# ACTIVE SKILL: (.+?)\n(.*)",
            system_prompt,
            re.DOTALL,
        )
        if skill_header_match:
            skill_name = skill_header_match.group(1).strip()
            skill_body = skill_header_match.group(2).strip()
            subsections.append(
                ContextSubsection(
                    name=f"Active Skill: {skill_name}",
                    content=skill_body,
                    token_estimate=_estimate_tokens(skill_body),
                )
            )

        total_tokens = _estimate_tokens(system_prompt)
        return ContextSection(
            name="System Prompt",
            content=system_prompt,
            token_estimate=total_tokens,
            subsections=subsections,
        )

    def _build_history_section(
        self,
        history: list[dict[str, Any]],
    ) -> ContextSection:
        """Build the conversation history section with per-message breakdown."""
        subsections: list[ContextSubsection] = []
        total_chars = 0

        for idx, msg in enumerate(history, start=1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content_str = content if isinstance(content, str) else json.dumps(content, default=str)
            tokens = _estimate_tokens(content_str)
            total_chars += len(content_str)

            # Build a short preview (first 80 chars)
            preview = content_str[:80].replace("\n", " ")
            if len(content_str) > 80:
                preview += "..."

            tool_name = msg.get("name", "")
            if role == "tool" and tool_name:
                label = f"tool:{tool_name} (msg {idx})"
            else:
                label = f"{role} (msg {idx})"

            subsections.append(
                ContextSubsection(
                    name=label,
                    content=preview,
                    token_estimate=tokens,
                )
            )

        total_tokens = total_chars // CHARS_PER_TOKEN
        msg_count = len(history)
        return ContextSection(
            name=f"Conversation History ({msg_count} messages)",
            content=f"{msg_count} messages",
            token_estimate=total_tokens,
            subsections=subsections,
        )

    def _build_tool_definitions_section(
        self,
        agent: Any,
    ) -> ContextSection:
        """Build the tool definitions section (OpenAI function schemas)."""
        openai_tools: list[dict[str, Any]] = getattr(agent, "_openai_tools", [])
        if not openai_tools:
            # Fallback: convert from agent.tools
            tools_dict = getattr(agent, "tools", {})
            if tools_dict:
                openai_tools = tools_to_openai_format(tools_dict)

        subsections: list[ContextSubsection] = []
        total_chars = 0

        for tool_def in openai_tools:
            func = tool_def.get("function", {})
            name = func.get("name", "unknown")
            schema_json = json.dumps(tool_def, ensure_ascii=False, default=str)
            tokens = _estimate_tokens(schema_json)
            total_chars += len(schema_json)
            subsections.append(
                ContextSubsection(
                    name=name,
                    content=func.get("description", "")[:120],
                    token_estimate=tokens,
                )
            )

        total_tokens = total_chars // CHARS_PER_TOKEN
        tool_count = len(openai_tools)
        return ContextSection(
            name=f"Tool Definitions ({tool_count} tools)",
            content=f"{tool_count} tool schemas",
            token_estimate=total_tokens,
            subsections=subsections,
        )
