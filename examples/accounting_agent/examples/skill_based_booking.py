#!/usr/bin/env python3
"""
Example: Skill-Based Smart Booking Workflow

This example demonstrates how to use the skill-based booking workflow
for the accounting agent. It shows:
1. Intent detection and skill activation
2. Automatic skill switching based on tool outputs
3. Token savings through progressive skill loading

Usage:
    python examples/skill_based_booking.py
"""

import asyncio
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from accounting_agent.application import (
    AccountingIntent,
    AccountingSkillActivator,
    SkillIntegration,
    create_accounting_skill_activator,
)


def demonstrate_intent_detection():
    """Demonstrate intent-based skill activation."""
    print("\n" + "=" * 60)
    print("DEMO 1: Intent-Based Skill Activation")
    print("=" * 60)

    # Create skill activator
    plugin_path = Path(__file__).parent.parent
    activator = create_accounting_skill_activator(plugin_path)

    print(f"\nAvailable skills: {activator.list_available_skills()}")

    # Test INVOICE_QUESTION intent
    print("\n--- Intent: INVOICE_QUESTION ---")
    skill = activator.activate_by_intent(AccountingIntent.INVOICE_QUESTION)
    if skill:
        print(f"Activated: {skill.name}")
        print(f"Description: {skill.description[:100]}...")
        print(f"Allowed tools: {skill.allowed_tools or 'None (explanation only)'}")
        print(f"Instructions preview: {skill.instructions[:200]}...")

    # Test INVOICE_PROCESSING intent
    print("\n--- Intent: INVOICE_PROCESSING ---")
    skill = activator.activate_by_intent(AccountingIntent.INVOICE_PROCESSING)
    if skill:
        print(f"Activated: {skill.name}")
        print(f"Description: {skill.description[:100]}...")
        print(f"Allowed tools: {skill.allowed_tools}")


def demonstrate_skill_switching():
    """Demonstrate automatic skill switching based on tool output."""
    print("\n" + "=" * 60)
    print("DEMO 2: Automatic Skill Switching")
    print("=" * 60)

    plugin_path = Path(__file__).parent.parent
    activator = create_accounting_skill_activator(plugin_path)
    integration = SkillIntegration(activator)

    # Start with INVOICE_PROCESSING
    print("\n--- Starting with INVOICE_PROCESSING ---")
    base_prompt = "You are BENNU, an accounting assistant."
    enhanced_prompt = integration.enhance_prompt(
        base_prompt, AccountingIntent.INVOICE_PROCESSING
    )
    print(f"Active skill: {activator.active_skill_name}")
    print(f"Enhanced prompt length: {len(enhanced_prompt)} chars")

    # Simulate confidence_evaluator output with high confidence
    print("\n--- Simulating HIGH confidence (97%) ---")
    tool_output_high = {
        "overall_confidence": 0.97,
        "recommendation": "auto_book",
        "triggered_hard_gates": [],
    }
    switch_result = integration.on_tool_result("confidence_evaluator", tool_output_high)
    print(f"Switch triggered: {switch_result is not None}")
    print(f"Active skill: {activator.active_skill_name}")

    # Reset and test with low confidence
    integration.reset()
    integration.enhance_prompt(base_prompt, AccountingIntent.INVOICE_PROCESSING)

    print("\n--- Simulating LOW confidence (72%) ---")
    tool_output_low = {
        "overall_confidence": 0.72,
        "recommendation": "hitl_review",
        "triggered_hard_gates": [],
    }
    switch_result = integration.on_tool_result("confidence_evaluator", tool_output_low)
    print(f"Switch triggered: {switch_result is not None}")
    if switch_result:
        print(f"Switched from: {switch_result['from_skill']}")
        print(f"Switched to: {switch_result['to_skill']}")
    print(f"Active skill: {activator.active_skill_name}")

    # Reset and test with hard gate
    integration.reset()
    integration.enhance_prompt(base_prompt, AccountingIntent.INVOICE_PROCESSING)

    print("\n--- Simulating HARD GATE (new_vendor) ---")
    tool_output_gate = {
        "overall_confidence": 0.95,
        "recommendation": "hitl_review",
        "triggered_hard_gates": ["new_vendor"],
    }
    switch_result = integration.on_tool_result("confidence_evaluator", tool_output_gate)
    print(f"Switch triggered: {switch_result is not None}")
    if switch_result:
        print(f"Switched to: {switch_result['to_skill']}")
    print(f"Active skill: {activator.active_skill_name}")


def demonstrate_token_savings():
    """Demonstrate token savings with skill-based approach."""
    print("\n" + "=" * 60)
    print("DEMO 3: Token Savings Comparison")
    print("=" * 60)

    plugin_path = Path(__file__).parent.parent
    activator = create_accounting_skill_activator(plugin_path)

    # Load each skill and measure size
    skills_data = {}
    for skill_name in activator.list_available_skills():
        skill = activator.skill_registry.get_skill(skill_name)
        if skill:
            skills_data[skill_name] = {
                "instructions_chars": len(skill.instructions),
                "description_chars": len(skill.description),
            }

    print("\nSkill Sizes:")
    print("-" * 40)
    for name, data in skills_data.items():
        print(f"  {name}: {data['instructions_chars']} chars")

    # Simulate old approach (all in system prompt)
    old_approach_chars = sum(d["instructions_chars"] for d in skills_data.values())

    print(f"\nOld Approach (all in prompt): {old_approach_chars} chars")

    # Simulate new approach for different scenarios
    scenarios = [
        ("Simple question (invoice-explanation)", ["invoice-explanation"]),
        ("Auto-booking (smart-booking-auto)", ["smart-booking-auto"]),
        ("HITL review (both booking skills)", ["smart-booking-auto", "smart-booking-hitl"]),
    ]

    print("\nNew Approach (skill-based):")
    print("-" * 40)
    for scenario_name, skills_used in scenarios:
        chars_used = sum(skills_data[s]["instructions_chars"] for s in skills_used)
        savings = ((old_approach_chars - chars_used) / old_approach_chars) * 100
        print(f"  {scenario_name}:")
        print(f"    Chars: {chars_used} (savings: {savings:.1f}%)")


def demonstrate_resource_access():
    """Demonstrate accessing skill resources."""
    print("\n" + "=" * 60)
    print("DEMO 4: Skill Resource Access")
    print("=" * 60)

    plugin_path = Path(__file__).parent.parent
    activator = create_accounting_skill_activator(plugin_path)

    # Activate smart-booking-auto
    skill = activator.activate_skill("smart-booking-auto")
    if not skill:
        print("Skill not found!")
        return

    print(f"\nActive skill: {skill.name}")
    print(f"Resources available: {list(skill.get_resources().keys())}")

    # Read a resource
    kontierung_rules = activator.get_skill_resource("resources/kontierung_rules.yaml")
    if kontierung_rules:
        print(f"\nKontierung rules preview ({len(kontierung_rules)} chars):")
        print(kontierung_rules[:500] + "...")


def main():
    """Run all demonstrations."""
    print("=" * 60)
    print("ACCOUNTING AGENT - SKILL-BASED BOOKING DEMO")
    print("=" * 60)

    demonstrate_intent_detection()
    demonstrate_skill_switching()
    demonstrate_token_savings()
    demonstrate_resource_access()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
