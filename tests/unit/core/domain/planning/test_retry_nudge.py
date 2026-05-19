from taskforce.core.domain.planning.utils import _build_retry_nudge


def test_tool_unavailable_retry_nudge_forbids_repeating_tool() -> None:
    nudge = _build_retry_nudge(
        ["browser"],
        error_kinds={"browser": "tool_unavailable"},
    )

    content = nudge["content"]
    assert "browser is unavailable" in content
    assert "Do NOT call it again" in content
    assert "setup command" in content
