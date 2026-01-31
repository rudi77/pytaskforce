"""
Accounting Agent Application Layer

This module provides application-level services for the accounting agent,
including skill activation and integration.
"""

from .skill_activator import (
    AccountingIntent,
    AccountingSkillActivator,
    SkillSwitchCondition,
    create_accounting_skill_activator,
)
from .skill_integration import (
    SkillExecutionState,
    SkillIntegration,
    create_skill_enhanced_prompt,
)


__all__ = [
    "AccountingIntent",
    "AccountingSkillActivator",
    "SkillSwitchCondition",
    "create_accounting_skill_activator",
    "SkillExecutionState",
    "SkillIntegration",
    "create_skill_enhanced_prompt",
]
