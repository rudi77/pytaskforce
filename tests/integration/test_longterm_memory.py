"""Integration tests for unified long-term memory functionality."""

import asyncio
from pathlib import Path

import pytest
import yaml

from taskforce.application.factory import AgentFactory


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create temporary config directory with test configurations."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def memory_config(temp_config_dir: Path, tmp_path: Path) -> Path:
    """Create test configuration with unified memory tool."""
    memory_work_dir = tmp_path / ".taskforce_test"

    config = {
        "profile": "test_memory",
        "persistence": {"type": "file", "work_dir": str(memory_work_dir)},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "memory": {"type": "file", "store_dir": str(memory_work_dir / "memory")},
        "tools": ["memory"],
    }

    config_path = temp_config_dir / "test_memory.yaml"
    with open(config_path, "w") as handle:
        yaml.dump(config, handle)

    return config_path


def test_memory_directory_creation(
    temp_config_dir: Path, memory_config: Path, tmp_path: Path
) -> None:
    """Test that memory directory is automatically created."""

    async def _run_test() -> None:
        memory_work_dir = tmp_path / ".taskforce_test"
        expected_memory_dir = memory_work_dir / "memory"

        assert not expected_memory_dir.exists()

        factory = AgentFactory(config_dir=str(temp_config_dir))
        await factory.create_agent(config="test_memory")

        assert expected_memory_dir.exists()
        assert expected_memory_dir.is_dir()

    asyncio.run(_run_test())


def test_memory_tool_execution(
    temp_config_dir: Path, memory_config: Path
) -> None:
    """Test that memory tool can store and search records."""

    async def _run_test() -> None:
        factory = AgentFactory(config_dir=str(temp_config_dir))
        agent = await factory.create_agent(config="test_memory")

        memory_tool = agent.tools.get("memory")
        assert memory_tool is not None

        add_result = await memory_tool.execute(
            action="add",
            scope="profile",
            kind="long_term",
            tags=["decision"],
            content="Unified memory is file-backed.",
            metadata={"source": "test"},
        )
        assert add_result["success"] is True
        record_id = add_result["record"]["id"]

        search_result = await memory_tool.execute(
            action="search",
            scope="profile",
            kind="long_term",
            query="file-backed",
            limit=5,
        )
        assert search_result["success"] is True
        assert any(record["id"] == record_id for record in search_result["records"])

    asyncio.run(_run_test())


def test_memory_tool_update_and_delete(
    temp_config_dir: Path, memory_config: Path
) -> None:
    """Test memory record update and delete."""

    async def _run_test() -> None:
        factory = AgentFactory(config_dir=str(temp_config_dir))
        agent = await factory.create_agent(config="test_memory")

        memory_tool = agent.tools.get("memory")
        assert memory_tool is not None

        add_result = await memory_tool.execute(
            action="add",
            scope="profile",
            kind="long_term",
            content="Initial content",
        )
        record_id = add_result["record"]["id"]

        update_result = await memory_tool.execute(
            action="update",
            record_id=record_id,
            scope="profile",
            kind="long_term",
            content="Updated content",
        )
        assert update_result["success"] is True
        assert update_result["record"]["content"] == "Updated content"

        delete_result = await memory_tool.execute(action="delete", record_id=record_id)
        assert delete_result["success"] is True

    asyncio.run(_run_test())


def test_multiple_profiles_separate_memory(temp_config_dir: Path, tmp_path: Path) -> None:
    """Test that different profiles have separate memory storage."""

    async def _run_test() -> None:
        profile1_work_dir = tmp_path / ".taskforce_profile1"
        profile2_work_dir = tmp_path / ".taskforce_profile2"

        config1 = {
            "profile": "profile1",
            "persistence": {"type": "file", "work_dir": str(profile1_work_dir)},
            "llm": {"config_path": "configs/llm_config.yaml"},
            "memory": {"type": "file", "store_dir": str(profile1_work_dir / "memory")},
            "tools": ["memory"],
        }

        config2 = {
            "profile": "profile2",
            "persistence": {"type": "file", "work_dir": str(profile2_work_dir)},
            "llm": {"config_path": "configs/llm_config.yaml"},
            "memory": {"type": "file", "store_dir": str(profile2_work_dir / "memory")},
            "tools": ["memory"],
        }

        with open(temp_config_dir / "profile1.yaml", "w") as handle:
            yaml.dump(config1, handle)
        with open(temp_config_dir / "profile2.yaml", "w") as handle:
            yaml.dump(config2, handle)

        factory = AgentFactory(config_dir=str(temp_config_dir))
        await factory.create_agent(config="profile1")
        await factory.create_agent(config="profile2")

        assert (profile1_work_dir / "memory").exists()
        assert (profile2_work_dir / "memory").exists()
        assert profile1_work_dir / "memory" != profile2_work_dir / "memory"

    asyncio.run(_run_test())
