"""
Performance tests for plan module.

Verifies that dependency validation meets performance requirements.
"""

import time
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.plan import PlanGenerator, TodoItem, TodoList
from taskforce.core.interfaces.llm import LLMProviderProtocol


class TestPlanPerformance:
    """Performance tests for plan validation."""

    @pytest.fixture
    def plan_generator(self):
        """Create PlanGenerator with mocked LLM."""
        mock_llm = AsyncMock(spec=LLMProviderProtocol)
        return PlanGenerator(llm_provider=mock_llm)

    def test_validate_dependencies_performance_20_tasks(self, plan_generator):
        """Test dependency validation completes in <100ms for 20-task plan."""
        # Create a plan with 20 tasks and complex dependencies
        items = []
        for i in range(1, 21):
            # Each task depends on previous 2 tasks (except first two)
            deps = []
            if i > 1:
                deps.append(i - 1)
            if i > 2:
                deps.append(i - 2)

            items.append(
                TodoItem(
                    position=i,
                    description=f"Task {i}",
                    acceptance_criteria=f"Task {i} complete",
                    dependencies=deps,
                )
            )

        plan = TodoList(mission="Performance test", items=items)

        # Measure validation time
        start_time = time.perf_counter()
        result = plan_generator.validate_dependencies(plan)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000

        # Verify it passed and was fast enough
        assert result is True
        assert elapsed_ms < 100, f"Validation took {elapsed_ms:.2f}ms, expected <100ms"

    def test_validate_dependencies_performance_50_tasks(self, plan_generator):
        """Test dependency validation scales reasonably to 50 tasks."""
        # Create a plan with 50 tasks
        items = []
        for i in range(1, 51):
            deps = []
            if i > 1:
                deps.append(i - 1)

            items.append(
                TodoItem(
                    position=i,
                    description=f"Task {i}",
                    acceptance_criteria=f"Task {i} complete",
                    dependencies=deps,
                )
            )

        plan = TodoList(mission="Scaling test", items=items)

        # Measure validation time
        start_time = time.perf_counter()
        result = plan_generator.validate_dependencies(plan)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000

        # Verify it passed and was reasonably fast
        assert result is True
        assert elapsed_ms < 500, f"Validation took {elapsed_ms:.2f}ms, expected <500ms"

    def test_validate_dependencies_performance_circular_detection(self, plan_generator):
        """Test circular dependency detection is fast even with complex graph."""
        # Create a plan with potential circular dependencies
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done", dependencies=[5]),
            TodoItem(position=2, description="Task 2", acceptance_criteria="Done", dependencies=[1]),
            TodoItem(position=3, description="Task 3", acceptance_criteria="Done", dependencies=[2]),
            TodoItem(position=4, description="Task 4", acceptance_criteria="Done", dependencies=[3]),
            TodoItem(position=5, description="Task 5", acceptance_criteria="Done", dependencies=[4]),
        ]

        plan = TodoList(mission="Circular test", items=items)

        # Measure validation time
        start_time = time.perf_counter()
        result = plan_generator.validate_dependencies(plan)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000

        # Verify it detected the cycle quickly
        assert result is False  # Should detect circular dependency
        assert elapsed_ms < 50, f"Circular detection took {elapsed_ms:.2f}ms, expected <50ms"

