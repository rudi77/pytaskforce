"""
Unit tests for PlannerTool - dynamic plan management.
"""

import pytest

from taskforce.core.tools.planner_tool import PlannerTool


class TestPlannerToolCreatePlan:
    """Tests for create_plan action."""

    @pytest.mark.asyncio
    async def test_create_plan_success(self):
        """Creating a plan with valid tasks should succeed."""
        tool = PlannerTool()
        result = await tool.execute(action="create_plan", tasks=["Task 1", "Task 2", "Task 3"])

        assert result["success"] is True
        assert "3 tasks" in result["message"]
        assert "[ ] 1. Task 1" in result["output"]
        assert "[ ] 2. Task 2" in result["output"]
        assert "[ ] 3. Task 3" in result["output"]

    @pytest.mark.asyncio
    async def test_create_plan_empty_list_fails(self):
        """Creating a plan with empty list should fail."""
        tool = PlannerTool()
        result = await tool.execute(action="create_plan", tasks=[])

        assert result["success"] is False
        assert "non-empty" in result["error"]

    @pytest.mark.asyncio
    async def test_create_plan_none_fails(self):
        """Creating a plan with None should fail."""
        tool = PlannerTool()
        result = await tool.execute(action="create_plan", tasks=None)

        assert result["success"] is False
        assert "non-empty" in result["error"]

    @pytest.mark.asyncio
    async def test_create_plan_no_tasks_param_fails(self):
        """Creating a plan without tasks param should fail."""
        tool = PlannerTool()
        result = await tool.execute(action="create_plan")

        assert result["success"] is False
        assert "non-empty" in result["error"]

    @pytest.mark.asyncio
    async def test_create_plan_overwrites_existing(self):
        """Creating a new plan should overwrite existing plan."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Old Task"])
        result = await tool.execute(action="create_plan", tasks=["New Task 1", "New Task 2"])

        assert result["success"] is True
        assert "New Task 1" in result["output"]
        assert "New Task 2" in result["output"]
        assert "Old Task" not in result["output"]


class TestPlannerToolMarkDone:
    """Tests for mark_done action."""

    @pytest.mark.asyncio
    async def test_mark_done_success(self):
        """Marking a step done should update its status."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Task 1", "Task 2"])

        result = await tool.execute(action="mark_done", step_index=1)

        assert result["success"] is True
        assert "[x] 1. Task 1" in result["output"]
        assert "[ ] 2. Task 2" in result["output"]

    @pytest.mark.asyncio
    async def test_mark_done_out_of_bounds_fails(self):
        """Marking a step with invalid index should fail."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Task 1"])

        result = await tool.execute(action="mark_done", step_index=5)

        assert result["success"] is False
        assert "out of bounds" in result["error"]

    @pytest.mark.asyncio
    async def test_mark_done_zero_index_fails(self):
        """Marking with zero index should fail (1-based indexing)."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Task 1"])

        result = await tool.execute(action="mark_done", step_index=0)

        assert result["success"] is False
        assert "out of bounds" in result["error"]

    @pytest.mark.asyncio
    async def test_mark_done_negative_index_fails(self):
        """Marking with negative index should fail."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Task 1"])

        result = await tool.execute(action="mark_done", step_index=-1)

        assert result["success"] is False
        assert "out of bounds" in result["error"]

    @pytest.mark.asyncio
    async def test_mark_done_no_plan_fails(self):
        """Marking done with no plan should fail."""
        tool = PlannerTool()
        result = await tool.execute(action="mark_done", step_index=1)

        assert result["success"] is False
        assert "No active plan" in result["error"]

    @pytest.mark.asyncio
    async def test_mark_done_missing_index_fails(self):
        """Marking done without step_index should fail."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Task 1"])

        result = await tool.execute(action="mark_done")

        assert result["success"] is False
        assert "step_index is required" in result["error"]

    @pytest.mark.asyncio
    async def test_mark_done_one_based_indexing(self):
        """Verify 1-based indexing works correctly."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["First", "Second", "Third"])

        # Mark second task (index 2 in 1-based)
        result = await tool.execute(action="mark_done", step_index=2)

        assert result["success"] is True
        assert "[ ] 1. First" in result["output"]
        assert "[x] 2. Second" in result["output"]
        assert "[ ] 3. Third" in result["output"]


class TestPlannerToolReadPlan:
    """Tests for read_plan action."""

    @pytest.mark.asyncio
    async def test_read_plan_with_tasks(self):
        """Reading plan should return formatted Markdown."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Step A", "Step B"])

        result = await tool.execute(action="read_plan")

        assert result["success"] is True
        assert "[ ] 1. Step A" in result["output"]
        assert "[ ] 2. Step B" in result["output"]

    @pytest.mark.asyncio
    async def test_read_plan_empty(self):
        """Reading empty plan should return 'No active plan.'."""
        tool = PlannerTool()
        result = await tool.execute(action="read_plan")

        assert result["success"] is True
        assert result["output"] == "No active plan."

    @pytest.mark.asyncio
    async def test_read_plan_mixed_status(self):
        """Reading plan with mixed done/not-done should show correctly."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Done", "Pending", "Also Done"])
        await tool.execute(action="mark_done", step_index=1)
        await tool.execute(action="mark_done", step_index=3)

        result = await tool.execute(action="read_plan")

        assert "[x] 1. Done" in result["output"]
        assert "[ ] 2. Pending" in result["output"]
        assert "[x] 3. Also Done" in result["output"]

    @pytest.mark.asyncio
    async def test_read_plan_format_matches_story_example(self):
        """Verify output format matches story example."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Recherche starten", "Ergebnisse zusammenfassen"])
        await tool.execute(action="mark_done", step_index=1)

        result = await tool.execute(action="read_plan")

        assert "[x] 1. Recherche starten" in result["output"]
        assert "[ ] 2. Ergebnisse zusammenfassen" in result["output"]


class TestPlannerToolUpdatePlan:
    """Tests for update_plan action."""

    @pytest.mark.asyncio
    async def test_update_plan_add_steps(self):
        """Adding steps should append to plan."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Original"])

        result = await tool.execute(action="update_plan", add_steps=["New 1", "New 2"])

        assert result["success"] is True
        assert "Original" in result["output"]
        assert "New 1" in result["output"]
        assert "New 2" in result["output"]

    @pytest.mark.asyncio
    async def test_update_plan_remove_steps(self):
        """Removing steps by index should work."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Keep", "Remove", "Also Keep"])

        result = await tool.execute(action="update_plan", remove_indices=[2])

        assert result["success"] is True
        assert "Keep" in result["output"]
        assert "Remove" not in result["output"]
        assert "Also Keep" in result["output"]

    @pytest.mark.asyncio
    async def test_update_plan_add_and_remove(self):
        """Adding and removing in same call should work."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["A", "B", "C"])

        result = await tool.execute(
            action="update_plan",
            remove_indices=[2],
            add_steps=["D"],
        )

        assert result["success"] is True
        assert "A" in result["output"]
        assert "B" not in result["output"]
        assert "C" in result["output"]
        assert "D" in result["output"]

    @pytest.mark.asyncio
    async def test_update_plan_remove_invalid_index_ignored(self):
        """Removing invalid indices should be silently ignored."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["A", "B"])

        result = await tool.execute(action="update_plan", remove_indices=[99, -5])

        assert result["success"] is True
        assert "A" in result["output"]
        assert "B" in result["output"]

    @pytest.mark.asyncio
    async def test_update_plan_on_empty_plan(self):
        """Updating empty plan should work."""
        tool = PlannerTool()

        result = await tool.execute(action="update_plan", add_steps=["First"])

        assert result["success"] is True
        assert "First" in result["output"]

    @pytest.mark.asyncio
    async def test_update_plan_one_based_remove_indices(self):
        """Verify remove_indices uses 1-based indexing."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["First", "Second", "Third"])

        # Remove second task (index 2 in 1-based)
        result = await tool.execute(action="update_plan", remove_indices=[2])

        assert result["success"] is True
        assert "First" in result["output"]
        assert "Second" not in result["output"]
        assert "Third" in result["output"]


class TestPlannerToolStateSerialization:
    """Tests for state get/set methods."""

    def test_get_state_returns_copy(self):
        """get_state should return a copy of internal state."""
        tool = PlannerTool()
        state = tool.get_state()
        state["tasks"] = [{"description": "Injected", "status": "PENDING"}]

        # Internal state should be unchanged
        assert tool.get_state()["tasks"] == []

    def test_set_state_restores_tasks(self):
        """set_state should restore tasks correctly."""
        tool = PlannerTool()
        saved_state = {
            "tasks": [
                {"description": "Restored 1", "status": "DONE"},
                {"description": "Restored 2", "status": "PENDING"},
            ]
        }

        tool.set_state(saved_state)

        state = tool.get_state()
        assert len(state["tasks"]) == 2
        assert state["tasks"][0]["status"] == "DONE"

    def test_set_state_with_none_resets(self):
        """set_state with None should reset to empty."""
        tool = PlannerTool()
        tool._state["tasks"] = [{"description": "Existing", "status": "PENDING"}]

        tool.set_state(None)

        assert tool.get_state()["tasks"] == []

    def test_initial_state_constructor(self):
        """Constructor with initial_state should restore properly."""
        initial = {"tasks": [{"description": "From constructor", "status": "PENDING"}]}
        tool = PlannerTool(initial_state=initial)

        state = tool.get_state()
        assert len(state["tasks"]) == 1
        assert state["tasks"][0]["description"] == "From constructor"

    @pytest.mark.asyncio
    async def test_roundtrip_serialization(self):
        """State should survive get/set roundtrip."""
        tool1 = PlannerTool()
        await tool1.execute(action="create_plan", tasks=["A", "B", "C"])
        await tool1.execute(action="mark_done", step_index=2)

        saved_state = tool1.get_state()

        tool2 = PlannerTool()
        tool2.set_state(saved_state)

        result = await tool2.execute(action="read_plan")
        assert "[ ] 1. A" in result["output"]
        assert "[x] 2. B" in result["output"]
        assert "[ ] 3. C" in result["output"]


class TestPlannerToolUnknownAction:
    """Tests for unknown action handling."""

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self):
        """Unknown action should return error."""
        tool = PlannerTool()
        result = await tool.execute(action="invalid_action")

        assert result["success"] is False
        assert "Unknown action" in result["error"]
        assert "invalid_action" in result["error"]


class TestPlannerToolMetadata:
    """Tests for tool metadata properties."""

    def test_name_property(self):
        """Tool name should be 'planner'."""
        tool = PlannerTool()
        assert tool.name == "planner"

    def test_description_property(self):
        """Tool description should mention all actions."""
        tool = PlannerTool()
        desc = tool.description
        assert "create_plan" in desc
        assert "mark_done" in desc
        assert "read_plan" in desc
        assert "update_plan" in desc

    def test_parameters_schema_structure(self):
        """Parameter schema should define action enum."""
        tool = PlannerTool()
        schema = tool.parameters_schema

        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert schema["properties"]["action"]["enum"] == [
            "create_plan",
            "mark_done",
            "read_plan",
            "update_plan",
        ]
        assert "action" in schema["required"]

    def test_requires_approval_property(self):
        """Planner tool should not require approval."""
        tool = PlannerTool()
        assert tool.requires_approval is False

    def test_approval_risk_level_property(self):
        """Planner tool should have low risk level."""
        tool = PlannerTool()
        assert tool.approval_risk_level.value == "low"


class TestPlannerToolValidation:
    """Tests for parameter validation."""

    def test_validate_params_missing_action(self):
        """Validation should fail without action parameter."""
        tool = PlannerTool()
        valid, error = tool.validate_params()

        assert valid is False
        assert "action" in error.lower()

    def test_validate_params_invalid_action(self):
        """Validation should fail with invalid action."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="invalid")

        assert valid is False
        assert "invalid" in error.lower()

    def test_validate_params_create_plan_missing_tasks(self):
        """Validation should fail for create_plan without tasks."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="create_plan")

        assert valid is False
        assert "tasks" in error.lower()

    def test_validate_params_create_plan_empty_tasks(self):
        """Validation should fail for create_plan with empty tasks."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="create_plan", tasks=[])

        assert valid is False
        assert "non-empty" in error.lower()

    def test_validate_params_mark_done_missing_index(self):
        """Validation should fail for mark_done without step_index."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="mark_done")

        assert valid is False
        assert "step_index" in error.lower()

    def test_validate_params_mark_done_zero_index(self):
        """Validation should fail for mark_done with zero index."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="mark_done", step_index=0)

        assert valid is False
        assert ">= 1" in error

    def test_validate_params_valid_create_plan(self):
        """Validation should pass for valid create_plan."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="create_plan", tasks=["Task 1"])

        assert valid is True
        assert error is None

    def test_validate_params_valid_mark_done(self):
        """Validation should pass for valid mark_done."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="mark_done", step_index=1)

        assert valid is True
        assert error is None

    def test_validate_params_valid_read_plan(self):
        """Validation should pass for valid read_plan."""
        tool = PlannerTool()
        valid, error = tool.validate_params(action="read_plan")

        assert valid is True
        assert error is None


class TestPlannerToolAcceptanceCriteria:
    """Tests specifically for story acceptance criteria."""

    @pytest.mark.asyncio
    async def test_acceptance_criteria_plan_creation(self):
        """AC: create_plan(['A', 'B']) erzeugt internen State mit 2 offenen Tasks."""
        tool = PlannerTool()
        result = await tool.execute(action="create_plan", tasks=["A", "B"])

        assert result["success"] is True
        state = tool.get_state()
        assert len(state["tasks"]) == 2
        assert state["tasks"][0]["status"] == "PENDING"
        assert state["tasks"][1]["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_acceptance_criteria_mark_done(self):
        """AC: mark_done(1) setzt den ersten Task auf erledigt."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["A", "B"])

        result = await tool.execute(action="mark_done", step_index=1)

        assert result["success"] is True
        state = tool.get_state()
        assert state["tasks"][0]["status"] == "DONE"
        assert state["tasks"][1]["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_acceptance_criteria_read_output_format(self):
        """AC: read_plan() liefert sauber formatierten String (Markdown-Liste)."""
        tool = PlannerTool()
        await tool.execute(action="create_plan", tasks=["Recherche starten", "Ergebnisse zusammenfassen"])
        await tool.execute(action="mark_done", step_index=1)

        result = await tool.execute(action="read_plan")

        assert result["success"] is True
        assert "[x] 1. Recherche starten" in result["output"]
        assert "[ ] 2. Ergebnisse zusammenfassen" in result["output"]

    @pytest.mark.asyncio
    async def test_acceptance_criteria_empty_state(self):
        """AC: Wenn kein Plan existiert, liefert read_plan() entsprechende Meldung."""
        tool = PlannerTool()
        result = await tool.execute(action="read_plan")

        assert result["success"] is True
        assert result["output"] == "No active plan."

