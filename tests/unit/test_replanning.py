import pytest
from typing import Dict, Any
from taskforce.core.domain.replanning import (
    ReplanStrategy,
    StrategyType,
    validate_strategy,
    extract_failure_context,
    MIN_CONFIDENCE_THRESHOLD
)
from taskforce.core.interfaces.todolist import TodoItem, TaskStatus

class TestReplanning:
    
    def test_strategy_validation_retry(self):
        """Test validation for RETRY_WITH_PARAMS strategy."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.RETRY_WITH_PARAMS,
            rationale="Test rationale",
            modifications={"new_parameters": {"key": "value"}},
            confidence=0.9
        )
        assert validate_strategy(strategy) is True

    def test_strategy_validation_retry_invalid(self):
        """Test invalid validation for RETRY_WITH_PARAMS strategy."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.RETRY_WITH_PARAMS,
            rationale="Test rationale",
            modifications={"wrong_key": "value"},
            confidence=0.9
        )
        assert validate_strategy(strategy) is False

    def test_strategy_validation_swap(self):
        """Test validation for SWAP_TOOL strategy."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.SWAP_TOOL,
            rationale="Test rationale",
            modifications={"new_tool": "new_tool_name", "new_parameters": {}},
            confidence=0.8
        )
        assert validate_strategy(strategy) is True

    def test_strategy_validation_swap_invalid(self):
        """Test invalid validation for SWAP_TOOL strategy."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.SWAP_TOOL,
            rationale="Test rationale",
            modifications={"missing_tool": "value"},
            confidence=0.8
        )
        assert validate_strategy(strategy) is False

    def test_strategy_validation_decompose(self):
        """Test validation for DECOMPOSE_TASK strategy."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.DECOMPOSE_TASK,
            rationale="Test rationale",
            modifications={
                "subtasks": [
                    {"description": "Subtask 1", "acceptance_criteria": "Criteria 1"},
                    {"description": "Subtask 2", "acceptance_criteria": "Criteria 2"}
                ]
            },
            confidence=0.8
        )
        assert validate_strategy(strategy) is True

    def test_strategy_validation_decompose_invalid(self):
        """Test invalid validation for DECOMPOSE_TASK strategy."""
        # Missing subtasks key
        strategy1 = ReplanStrategy(
            strategy_type=StrategyType.DECOMPOSE_TASK,
            rationale="Test rationale",
            modifications={"wrong_key": []},
            confidence=0.8
        )
        assert validate_strategy(strategy1) is False
        
        # Missing fields in subtask
        strategy2 = ReplanStrategy(
            strategy_type=StrategyType.DECOMPOSE_TASK,
            rationale="Test rationale",
            modifications={
                "subtasks": [
                    {"description": "Subtask 1"} # Missing acceptance_criteria
                ]
            },
            confidence=0.8
        )
        assert validate_strategy(strategy2) is False

    def test_strategy_validation_skip(self):
        """Test validation for SKIP strategy."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.SKIP,
            rationale="Test rationale",
            modifications={},
            confidence=0.8
        )
        assert validate_strategy(strategy) is True

    def test_strategy_validation_confidence(self):
        """Test validation check for confidence threshold."""
        strategy = ReplanStrategy(
            strategy_type=StrategyType.SKIP,
            rationale="Test rationale",
            modifications={},
            confidence=MIN_CONFIDENCE_THRESHOLD - 0.1
        )
        assert validate_strategy(strategy) is False

    def test_extract_failure_context(self):
        """Test failure context extraction from TodoItem."""
        item = TodoItem(
            position=1,
            description="Test task",
            acceptance_criteria="Test criteria",
            dependencies=[],
            status=TaskStatus.FAILED
        )
        item.chosen_tool = "test_tool"
        item.tool_input = {"param": "value"}
        item.execution_result = {
            "error": "Test error",
            "error_type": "ValueError",
            "stdout": "log output",
            "stderr": "error output"
        }
        item.attempts = 2
        
        context = extract_failure_context(item)
        
        assert context["task_description"] == "Test task"
        assert context["acceptance_criteria"] == "Test criteria"
        assert context["tool_name"] == "test_tool"
        assert "param" in context["parameters"]
        assert context["error_message"] == "Test error"
        assert context["error_type"] == "ValueError"
        assert context["attempt_count"] == 2
        assert context["stdout"] == "log output"
        assert context["stderr"] == "error output"

    def test_extract_failure_context_with_extra(self):
        """Test failure context extraction with additional context."""
        item = TodoItem(
            position=1,
            description="Test task",
            acceptance_criteria="Test criteria",
            dependencies=[],
            status=TaskStatus.FAILED
        )
        
        extra_context = {"extra_info": "value"}
        context = extract_failure_context(item, extra_context)
        
        assert context["extra_info"] == "value"
