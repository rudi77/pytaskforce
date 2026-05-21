import pytest

from taskforce.core.domain.sub_agents import build_sub_agent_session_id


@pytest.mark.spec("sub-agents.session_id_is_hierarchical")
def test_build_sub_agent_session_id() -> None:
    session_id = build_sub_agent_session_id("parent", "planner", "abc123")

    assert session_id == "parent--sub_planner_abc123"
