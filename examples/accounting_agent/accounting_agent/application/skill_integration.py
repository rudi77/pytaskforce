"""
Skill Integration for Accounting Agent

This module provides integration between the SkillActivator and the
agent execution loop. It handles:
- Injecting skill instructions into prompts
- Monitoring tool outputs for skill switch conditions
- Managing the skill lifecycle during execution

Usage:
    integration = SkillIntegration(skill_activator)

    # Before agent execution
    enhanced_prompt = integration.enhance_prompt(base_prompt, intent)

    # After each tool call
    integration.on_tool_result(tool_name, tool_output)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .skill_activator import AccountingSkillActivator, AccountingIntent


logger = logging.getLogger(__name__)


@dataclass
class SkillExecutionState:
    """
    Tracks the state of skill execution.

    Attributes:
        current_skill: Name of the currently active skill
        previous_skill: Name of the previously active skill (after switch)
        switch_count: Number of skill switches in this execution
        tool_calls: List of tool calls made during execution
        context_data: Data passed between skills during switch
    """

    current_skill: str | None = None
    previous_skill: str | None = None
    switch_count: int = 0
    tool_calls: list[str] = field(default_factory=list)
    context_data: dict[str, Any] = field(default_factory=dict)


class SkillIntegration:
    """
    Integrates skill activation with the agent execution loop.

    This class manages the interaction between the skill system and
    the agent, handling prompt enhancement, tool monitoring, and
    automatic skill switching.
    """

    # Tools that can trigger skill switches
    SWITCH_TRIGGER_TOOLS = {
        "confidence_evaluator",
    }

    def __init__(
        self,
        skill_activator: AccountingSkillActivator,
        on_skill_switch: Callable[[str, str], None] | None = None,
    ):
        """
        Initialize the skill integration.

        Args:
            skill_activator: The skill activator instance
            on_skill_switch: Optional callback when skill switches
                            (old_skill, new_skill) -> None
        """
        self.activator = skill_activator
        self.state = SkillExecutionState()
        self._on_skill_switch = on_skill_switch

    def enhance_prompt(
        self,
        base_prompt: str,
        intent: str | AccountingIntent | None = None,
    ) -> str:
        """
        Enhance the base prompt with skill-specific instructions.

        If an intent is provided, activates the appropriate skill first.

        Args:
            base_prompt: The base system prompt
            intent: Optional intent to activate skill for

        Returns:
            Enhanced prompt with skill instructions
        """
        # Activate skill by intent if provided
        if intent:
            skill = self.activator.activate_by_intent(intent)
            if skill:
                self.state.current_skill = skill.name

        # Get active skill instructions
        skill_instructions = self.activator.get_active_instructions()

        if not skill_instructions:
            return base_prompt

        # Combine base prompt with skill instructions
        enhanced = f"""{base_prompt}

# ACTIVE SKILL INSTRUCTIONS

{skill_instructions}
"""
        return enhanced

    def on_tool_result(
        self,
        tool_name: str,
        tool_output: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Process a tool result and check for skill switches.

        Called after each tool execution. If a skill switch is triggered,
        returns information about the switch.

        Args:
            tool_name: Name of the executed tool
            tool_output: Output from the tool

        Returns:
            Switch info dict if skill switched, None otherwise
        """
        # Track tool call
        self.state.tool_calls.append(tool_name)

        # Only check for switches on specific tools
        if tool_name not in self.SWITCH_TRIGGER_TOOLS:
            return None

        # Check if skill switch is needed
        old_skill = self.state.current_skill
        new_skill = self.activator.check_skill_switch(tool_output, tool_name)

        if new_skill:
            self.state.previous_skill = old_skill
            self.state.current_skill = new_skill.name
            self.state.switch_count += 1

            # Store context data for the new skill
            self._transfer_context(tool_output)

            # Notify callback
            if self._on_skill_switch:
                self._on_skill_switch(old_skill or "", new_skill.name)

            logger.info(
                f"Skill switched: {old_skill} → {new_skill.name} "
                f"(triggered by {tool_name})"
            )

            return {
                "switched": True,
                "from_skill": old_skill,
                "to_skill": new_skill.name,
                "trigger": tool_name,
                "new_instructions": new_skill.instructions,
            }

        return None

    def _transfer_context(self, tool_output: dict[str, Any]) -> None:
        """
        Transfer relevant context data when switching skills.

        Args:
            tool_output: Output from the triggering tool
        """
        # Store confidence result for HITL skill
        if "overall_confidence" in tool_output:
            self.state.context_data["confidence_result"] = {
                "overall_confidence": tool_output.get("overall_confidence"),
                "recommendation": tool_output.get("recommendation"),
                "triggered_hard_gates": tool_output.get("triggered_hard_gates", []),
                "signals": tool_output.get("signals", {}),
            }

        # Store booking proposal if available
        if "booking_proposal" in tool_output:
            self.state.context_data["booking_proposal"] = tool_output["booking_proposal"]

        # Store invoice data if available
        if "invoice_data" in tool_output:
            self.state.context_data["invoice_data"] = tool_output["invoice_data"]

    def get_context_for_skill(self) -> dict[str, Any]:
        """
        Get context data accumulated for the current skill.

        Returns:
            Dictionary of context data
        """
        return self.state.context_data.copy()

    def get_active_skill_instructions(self) -> str:
        """
        Get instructions for the currently active skill.

        Returns:
            Skill instructions or empty string
        """
        return self.activator.get_active_instructions()

    def get_skill_resource(self, path: str) -> str | None:
        """
        Read a resource from the active skill.

        Args:
            path: Relative path to the resource

        Returns:
            Resource content or None
        """
        return self.activator.get_skill_resource(path)

    def get_allowed_tools(self) -> list[str] | None:
        """
        Get allowed tools for the current skill.

        Returns:
            List of tool names, or None if no restrictions
        """
        return self.activator.get_allowed_tools()

    def reset(self) -> None:
        """Reset the integration state for a new execution."""
        self.state = SkillExecutionState()
        self.activator.reset()

    def get_execution_summary(self) -> dict[str, Any]:
        """
        Get a summary of the skill execution.

        Returns:
            Dictionary with execution statistics
        """
        return {
            "current_skill": self.state.current_skill,
            "previous_skill": self.state.previous_skill,
            "switch_count": self.state.switch_count,
            "tool_calls": len(self.state.tool_calls),
            "tools_used": list(set(self.state.tool_calls)),
        }


def create_skill_enhanced_prompt(
    base_system_prompt: str,
    intent: str,
    skill_directories: list[str],
) -> tuple[str, SkillIntegration]:
    """
    Create an enhanced prompt with skill instructions.

    Convenience function for creating a skill-enhanced prompt in one call.

    Args:
        base_system_prompt: The base system prompt
        intent: User intent (INVOICE_QUESTION or INVOICE_PROCESSING)
        skill_directories: Directories containing skills

    Returns:
        Tuple of (enhanced_prompt, skill_integration)
    """
    activator = AccountingSkillActivator(skill_directories=skill_directories)
    integration = SkillIntegration(activator)
    enhanced_prompt = integration.enhance_prompt(base_system_prompt, intent)

    return enhanced_prompt, integration
