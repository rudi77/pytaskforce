"""
Context Builder

Deterministic builder for creating budgeted context packs from session state.
The builder selectively includes tool result previews and other context items
while respecting hard caps defined by ContextPolicy.

Key Features:
- Deterministic: Same state + policy → same context pack
- Budget-safe: Never exceeds policy limits
- No LLM dependency: Pure function-based construction
- Selector support: Extract specific parts of tool results (MVP: first_chars)
"""

import json
from typing import Any

from taskforce.core.domain.context_policy import ContextPolicy


class ContextBuilder:
    """
    Builder for creating budgeted context packs.

    The builder takes session state (including tool result handles) and
    constructs a context pack that fits within policy limits. The pack
    is injected into the system prompt before each LLM call.

    Design Principles:
    - Deterministic: No randomness, no LLM calls
    - Budget-first: Always respect policy caps
    - Latest-first: Prioritize recent tool results
    - Transparent: Clear headers for LLM interpretation
    """

    def __init__(self, policy: ContextPolicy):
        """
        Initialize builder with a policy.

        Args:
            policy: ContextPolicy defining budget constraints
        """
        self.policy = policy

    def build_context_pack(
        self,
        mission: str | None = None,
        state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Build a budgeted context pack from session state.

        The context pack includes:
        1. Mission summary (if available)
        2. Latest tool result previews (up to policy limit)
        3. Plan state summary (if available)

        All content is capped by policy limits to prevent token explosion.

        Args:
            mission: Optional mission description
            state: Optional session state dictionary
            messages: Optional message history (for extracting tool previews)

        Returns:
            Formatted context pack string ready for injection
        """
        state = state or {}
        messages = messages or []

        # Build sections
        sections: list[str] = []

        # Section 1: Mission summary (if available and short enough)
        if mission and len(mission) <= self.policy.max_chars_per_item:
            sections.append(f"**Mission:** {mission}")

        # Section 2: Latest tool result previews
        tool_previews = self._extract_tool_previews(messages)
        if tool_previews:
            preview_section = self._build_tool_preview_section(tool_previews)
            if preview_section:
                sections.append(preview_section)

        # Section 3: Plan state (if available)
        plan_state = state.get("planner_state")
        if plan_state:
            plan_summary = self._build_plan_summary(plan_state)
            if plan_summary:
                sections.append(plan_summary)

        # Combine sections with budget enforcement
        context_pack = self._combine_sections(sections)

        return context_pack

    def _extract_tool_previews(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Extract tool result previews from message history.

        Looks for tool messages with preview data (from Story 9.1).
        Returns the latest N previews based on policy.

        Args:
            messages: Message history

        Returns:
            List of preview dictionaries (latest first)
        """
        previews: list[dict[str, Any]] = []

        # Scan messages in reverse (latest first)
        for msg in reversed(messages):
            if msg.get("role") != "tool":
                continue

            # Check if message has preview data (Story 9.1 format)
            content = msg.get("content", "")
            if not content:
                continue

            # Try to parse as JSON (preview format)
            try:
                parsed = json.loads(content)
                if "handle" in parsed and "preview_text" in parsed:
                    # This is a preview message
                    handle_data = parsed["handle"]
                    tool_name = handle_data.get("tool", "unknown")

                    # Check if tool is allowed by policy
                    if not self.policy.is_tool_allowed(tool_name):
                        continue

                    previews.append({
                        "tool": tool_name,
                        "preview": parsed["preview_text"],
                        "truncated": parsed.get("truncated", False),
                        "size_chars": handle_data.get("size_chars", 0),
                    })

                    # Stop when we have enough
                    if len(previews) >= self.policy.include_latest_tool_previews_n:
                        break
            except (json.JSONDecodeError, KeyError):
                # Not a preview message, skip
                continue

        # Return in chronological order (oldest first)
        return list(reversed(previews))

    def _build_tool_preview_section(
        self, previews: list[dict[str, Any]]
    ) -> str | None:
        """
        Build tool preview section from extracted previews.

        Args:
            previews: List of preview dictionaries

        Returns:
            Formatted section string, or None if empty
        """
        if not previews:
            return None

        lines = ["**Recent Tool Results:**"]

        total_chars = 0
        items_added = 0

        for preview_data in previews:
            tool = preview_data["tool"]
            preview = preview_data["preview"]
            size_chars = preview_data["size_chars"]

            # Apply per-item cap
            if len(preview) > self.policy.max_chars_per_item:
                preview = preview[: self.policy.max_chars_per_item] + "..."

            # Check total budget
            if total_chars + len(preview) > self.policy.max_total_chars:
                # Would exceed budget, stop here
                break

            # Check item count
            if items_added >= self.policy.max_items:
                break

            # Add preview
            lines.append(f"- `{tool}` ({size_chars} chars): {preview}")
            total_chars += len(preview)
            items_added += 1

        if items_added == 0:
            return None

        return "\n".join(lines)

    def _build_plan_summary(self, plan_state: dict[str, Any]) -> str | None:
        """
        Build plan state summary.

        Args:
            plan_state: Planner state dictionary

        Returns:
            Formatted plan summary, or None if empty
        """
        # Extract plan data
        plan_data = plan_state.get("plan")
        if not plan_data:
            return None

        # Build summary
        steps = plan_data.get("steps", [])
        if not steps:
            return None

        # Count completed/pending steps
        completed = sum(1 for s in steps if s.get("status") == "completed")
        pending = sum(1 for s in steps if s.get("status") == "pending")

        summary = f"**Plan Status:** {completed}/{len(steps)} steps completed, {pending} pending"

        # Add current step if available
        current_step = next((s for s in steps if s.get("status") == "in_progress"), None)
        if current_step:
            step_desc = current_step.get("description", "")
            if len(step_desc) > self.policy.max_chars_per_item:
                step_desc = step_desc[: self.policy.max_chars_per_item] + "..."
            summary += f"\n- Current: {step_desc}"

        # Check budget
        if len(summary) > self.policy.max_chars_per_item:
            summary = summary[: self.policy.max_chars_per_item] + "..."

        return summary

    def _combine_sections(self, sections: list[str]) -> str:
        """
        Combine sections into final context pack with header.

        Args:
            sections: List of section strings

        Returns:
            Complete context pack with header
        """
        if not sections:
            return ""

        # Build pack with clear header
        pack_lines = [
            "## CONTEXT PACK (BUDGETED)",
            "The following context is provided to help you make informed decisions.",
            "",
        ]

        # Add sections
        for section in sections:
            pack_lines.append(section)
            pack_lines.append("")  # Blank line between sections

        # Combine
        pack = "\n".join(pack_lines)

        # Final budget check (should never exceed, but safety)
        if len(pack) > self.policy.max_total_chars:
            pack = pack[: self.policy.max_total_chars] + "\n\n[Context truncated to fit budget]"

        return pack

    def apply_selector(
        self, content: str, selector: str, max_chars: int | None = None
    ) -> str:
        """
        Apply a selector to extract part of content.

        MVP implementation supports:
        - "first_chars": Take first N characters
        - "last_chars": Take last N characters

        Future selectors could include:
        - "json_path": Extract JSON field
        - "lines": Extract specific line ranges
        - "regex": Extract regex matches

        Args:
            content: Full content string
            selector: Selector type
            max_chars: Optional character limit

        Returns:
            Extracted content
        """
        max_chars = max_chars or self.policy.max_chars_per_item

        if selector == "first_chars":
            return content[:max_chars]
        elif selector == "last_chars":
            return content[-max_chars:] if len(content) > max_chars else content
        else:
            # Unknown selector, default to first_chars
            return content[:max_chars]
