"""Replanning module for intelligent failure recovery strategies.

This module provides data structures and logic for generating intelligent
recovery strategies when TodoItem execution fails. It uses LLM-based analysis
to recommend appropriate actions (retry with modified params, swap tools, 
decompose tasks, or skip).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import structlog


class StrategyType(str, Enum):
    """Enumeration of available replanning strategies."""
    
    RETRY_WITH_PARAMS = "retry_with_params"  # Same tool, different parameters
    SWAP_TOOL = "swap_tool"                   # Different tool, same goal
    DECOMPOSE_TASK = "decompose_task"         # Split into smaller steps
    SKIP = "skip"                             # Skip the current task


@dataclass
class ReplanStrategy:
    """Represents an intelligent recovery strategy for a failed TodoItem.
    
    Attributes:
        strategy_type: The type of recovery strategy to apply
        rationale: Human-readable explanation of why this strategy was chosen
        modifications: Strategy-specific changes (structure varies by strategy_type)
        confidence: Confidence score from 0.0 to 1.0
    """
    
    strategy_type: StrategyType
    rationale: str
    modifications: Dict[str, Any]
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy to a serializable dictionary."""
        return {
            "strategy_type": self.strategy_type.value if isinstance(self.strategy_type, StrategyType) else str(self.strategy_type),
            "rationale": self.rationale,
            "modifications": self.modifications,
            "confidence": self.confidence,
        }
    
    def to_json(self) -> str:
        """Serialize strategy to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ReplanStrategy:
        """Create ReplanStrategy from dictionary.
        
        Args:
            data: Dictionary with strategy_type, rationale, modifications, confidence
            
        Returns:
            ReplanStrategy instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            strategy_type = StrategyType(data["strategy_type"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid or missing strategy_type: {e}")
        
        return ReplanStrategy(
            strategy_type=strategy_type,
            rationale=data.get("rationale", ""),
            modifications=data.get("modifications", {}),
            confidence=float(data.get("confidence", 0.0)),
        )


# Confidence threshold for strategy execution (strategies below this are rejected)
MIN_CONFIDENCE_THRESHOLD = 0.6

# LLM timeout for strategy generation (seconds)
STRATEGY_GENERATION_TIMEOUT = 5.0


REPLAN_PROMPT_TEMPLATE = """You are analyzing a failed task execution to recommend a recovery strategy.

**Failed Task:**
- Description: {task_description}
- Acceptance Criteria: {acceptance_criteria}
- Tool Used: {tool_name}
- Parameters: {parameters}
- Error: {error_message}
- Error Type: {error_type}
- Previous Attempts: {attempt_count}

(Refer to the <ToolsDescription> section in the system prompt for available tools.)

**Strategy Options:**

1. **retry_with_params**: Adjust parameters and retry the same tool
   - Use when: Parameter values were incorrect, missing, or need refinement
   - Modifications format: {{"new_parameters": {{"param_name": "new_value", ...}}}}

2. **swap_tool**: Use a different tool to achieve the same goal
   - Use when: The chosen tool is fundamentally unsuitable for the task
   - Modifications format: {{"new_tool": "tool_name", "new_parameters": {{...}}}}

3. **decompose_task**: Split the task into smaller, more manageable subtasks
   - Use when: Task is too complex or requires multiple sequential steps
   - Modifications format: {{"subtasks": [{{"description": "...", "acceptance_criteria": "...", "suggested_tool": "..."}}]}}

4. **skip**: Skip the current task
   - Use when: The task is impossible to complete, irrelevant, or blocking progress without a viable workaround
   - Modifications format: {{}}

**Instructions:**
Analyze the failure context above and determine the SINGLE BEST recovery strategy. Consider:
- Root cause of the failure (wrong params vs wrong tool vs task complexity)
- Whether the error is retryable or requires a different approach
- Available alternative tools that could accomplish the goal
- Whether breaking down the task would increase success likelihood
- Whether skipping is the only viable option

Respond with ONLY a JSON object (no markdown, no explanation outside JSON):
{{
  "strategy_type": "retry_with_params" | "swap_tool" | "decompose_task" | "skip",
  "rationale": "2-3 sentence explanation of why this strategy is best",
  "modifications": {{...strategy-specific structure as defined above...}},
  "confidence": 0.0-1.0
}}

**Confidence Scoring Guidelines:**
- 0.8-1.0: Very confident - clear root cause, obvious solution
- 0.6-0.8: Moderately confident - good understanding, reasonable solution
- 0.4-0.6: Low confidence - uncertain root cause or solution viability
- 0.0-0.4: Very low confidence - insufficient info or no clear path forward

Only strategies with confidence >= 0.6 will be executed.
"""


def validate_strategy(strategy: ReplanStrategy, logger: Optional[Any] = None) -> bool:
    """Validate that a ReplanStrategy is well-formed and actionable.
    
    Args:
        strategy: The strategy to validate
        logger: Optional logger for validation failure details
        
    Returns:
        True if strategy is valid, False otherwise
    """
    log = logger or structlog.get_logger()
    
    # Check confidence threshold
    if strategy.confidence < MIN_CONFIDENCE_THRESHOLD:
        log.warning(
            "strategy_confidence_too_low",
            confidence=strategy.confidence,
            threshold=MIN_CONFIDENCE_THRESHOLD
        )
        return False
    
    # Check strategy type is valid
    if not isinstance(strategy.strategy_type, StrategyType):
        log.warning("invalid_strategy_type", strategy_type=type(strategy.strategy_type))
        return False
    
    # Validate modifications structure based on strategy type
    mods = strategy.modifications
    
    if strategy.strategy_type == StrategyType.RETRY_WITH_PARAMS:
        if "new_parameters" not in mods or not isinstance(mods["new_parameters"], dict):
            log.warning(
                "invalid_retry_modifications",
                modifications=mods,
                expected_key="new_parameters"
            )
            return False
    
    elif strategy.strategy_type == StrategyType.SWAP_TOOL:
        if "new_tool" not in mods or not isinstance(mods.get("new_tool"), str):
            log.warning(
                "invalid_swap_modifications",
                modifications=mods,
                expected_keys=["new_tool", "new_parameters"]
            )
            return False
        # new_parameters is optional for SWAP_TOOL
    
    elif strategy.strategy_type == StrategyType.DECOMPOSE_TASK:
        if "subtasks" not in mods or not isinstance(mods["subtasks"], list):
            log.warning(
                "invalid_decompose_modifications",
                modifications=mods,
                expected_key="subtasks"
            )
            return False
        
        # Validate each subtask has required fields
        for idx, subtask in enumerate(mods["subtasks"]):
            if not isinstance(subtask, dict):
                log.warning("subtask_not_dict", index=idx, subtask=subtask)
                return False
            
            required_fields = ["description", "acceptance_criteria"]
            for field_name in required_fields:
                if field_name not in subtask or not subtask[field_name]:
                    log.warning(
                        "subtask_missing_field",
                        index=idx,
                        missing_field=field_name,
                        subtask=subtask
                    )
                    return False
                    
    elif strategy.strategy_type == StrategyType.SKIP:
        # No specific modifications required for skip
        pass
    
    log.info(
        "strategy_validated",
        strategy_type=strategy.strategy_type.value,
        confidence=strategy.confidence
    )
    return True


def extract_failure_context(
    failed_item: Any,  # TodoItem
    error_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Extract structured failure context from a failed TodoItem.
    
    Args:
        failed_item: The TodoItem that failed execution
        error_context: Optional additional error context (traceback, etc.)
        
    Returns:
        Dictionary with structured failure information for LLM analysis
    """
    # Extract core task info
    context = {
        "task_description": failed_item.description,
        "acceptance_criteria": failed_item.acceptance_criteria,
        "tool_name": failed_item.chosen_tool or "unknown",
        "parameters": json.dumps(failed_item.tool_input or {}, indent=2),
        "attempt_count": failed_item.attempts,
    }
    
    # Extract error details from execution_result
    exec_result = failed_item.execution_result or {}
    context["error_message"] = exec_result.get("error", "No error message available")
    context["error_type"] = exec_result.get("error_type", "unknown")
    
    # Include stdout/stderr if available for additional context
    if "stdout" in exec_result:
        context["stdout"] = exec_result["stdout"]
    if "stderr" in exec_result:
        context["stderr"] = exec_result["stderr"]
    
    # Merge in any additional error context
    if error_context:
        context.update(error_context)
    
    return context

