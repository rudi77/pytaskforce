"""Tests for the memory management CLI commands.

Covers the ``consolidate``, ``experiences``, and ``stats`` commands
with mocked services to avoid I/O and LLM calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from taskforce.api.cli.commands.memory import app
from taskforce.core.domain.experience import (
    ConsolidationResult,
    SessionExperience,
    ToolCallExperience,
)

runner = CliRunner()

# Patch targets: the imports happen lazily inside async functions, so we
# patch the source modules rather than the CLI module namespace.
_PROFILE_LOADER = "taskforce.application.profile_loader.ProfileLoader"
_INFRA_BUILDER = "taskforce.application.infrastructure_builder.InfrastructureBuilder"
_BUILD_COMPONENTS = "taskforce.application.consolidation_service.build_consolidation_components"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_experience(
    session_id: str = "sess-001",
    profile: str = "dev",
    mission: str = "Test mission",
    processed: bool = False,
) -> SessionExperience:
    """Create a minimal SessionExperience for testing."""
    return SessionExperience(
        session_id=session_id,
        profile=profile,
        mission=mission,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        total_steps=3,
        tool_calls=[
            ToolCallExperience(tool_name="file_read", arguments={"path": "x.py"}),
            ToolCallExperience(tool_name="python", arguments={"code": "1+1"}),
        ],
        processed_by=["consol-1"] if processed else [],
    )


def _make_consolidation_result(**overrides) -> ConsolidationResult:
    """Create a ConsolidationResult for testing."""
    defaults = dict(
        consolidation_id="abc123def456",
        strategy="batch",
        sessions_processed=2,
        memories_created=5,
        memories_updated=1,
        memories_retired=0,
        contradictions_resolved=1,
        quality_score=0.85,
        total_tokens=1200,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return ConsolidationResult(**defaults)


def _mock_profile_loader(config: dict | None = None):
    """Return a patched ProfileLoader that returns the given config."""
    if config is None:
        config = {
            "consolidation": {
                "enabled": True,
                "work_dir": ".taskforce/experiences",
                "model_alias": "main",
            },
            "persistence": {"work_dir": ".taskforce"},
        }
    loader = MagicMock()
    loader.load_profile.return_value = config
    return loader


# ---------------------------------------------------------------------------
# consolidate command
# ---------------------------------------------------------------------------


class TestConsolidateCommand:
    """Tests for ``taskforce memory consolidate``."""

    def test_consolidate_dry_run(self) -> None:
        """Dry run lists unprocessed experiences without running consolidation."""
        exp = _make_experience()
        mock_store = AsyncMock()
        mock_store.list_experiences = AsyncMock(return_value=[exp])

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_experience_store.return_value = mock_store

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
        ):
            result = runner.invoke(app, ["consolidate", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "1 unprocessed" in result.output
        assert "sess-001" in result.output

    def test_consolidate_not_enabled(self) -> None:
        """Shows warning when consolidation is not enabled in profile."""
        config = {"consolidation": {"enabled": False}, "persistence": {"work_dir": ".taskforce"}}
        mock_loader = _mock_profile_loader(config)
        mock_ib = MagicMock()
        mock_ib.build_llm_provider.return_value = MagicMock()

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
            patch(_BUILD_COMPONENTS, return_value=(None, None)),
        ):
            result = runner.invoke(app, ["consolidate"])

        assert result.exit_code == 0
        assert "not enabled" in result.output

    def test_consolidate_runs_successfully(self) -> None:
        """Runs consolidation and displays result table."""
        consol_result = _make_consolidation_result()
        mock_service = AsyncMock()
        mock_service.trigger_consolidation = AsyncMock(return_value=consol_result)

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_llm_provider.return_value = MagicMock()

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
            patch(_BUILD_COMPONENTS, return_value=(MagicMock(), mock_service)),
        ):
            result = runner.invoke(app, ["consolidate", "--strategy", "batch"])

        assert result.exit_code == 0
        assert "Consolidation Result" in result.output
        assert "5" in result.output  # memories_created
        assert "0.85" in result.output  # quality_score

    def test_consolidate_with_sessions_option(self) -> None:
        """--sessions passes session IDs to trigger_consolidation."""
        consol_result = _make_consolidation_result(sessions_processed=1)
        mock_service = AsyncMock()
        mock_service.trigger_consolidation = AsyncMock(return_value=consol_result)

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_llm_provider.return_value = MagicMock()

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
            patch(_BUILD_COMPONENTS, return_value=(MagicMock(), mock_service)),
        ):
            result = runner.invoke(
                app, ["consolidate", "--sessions", "sess-a,sess-b"]
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.trigger_consolidation.call_args.kwargs
        assert call_kwargs["session_ids"] == ["sess-a", "sess-b"]


# ---------------------------------------------------------------------------
# experiences command
# ---------------------------------------------------------------------------


class TestExperiencesCommand:
    """Tests for ``taskforce memory experiences``."""

    def test_experiences_empty(self) -> None:
        """Shows message when no experiences exist."""
        mock_store = AsyncMock()
        mock_store.list_experiences = AsyncMock(return_value=[])

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_experience_store.return_value = mock_store

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
        ):
            result = runner.invoke(app, ["experiences"])

        assert result.exit_code == 0
        assert "No experiences found" in result.output

    def test_experiences_lists_entries(self) -> None:
        """Lists experiences in a table."""
        exps = [
            _make_experience("sess-001", mission="First mission"),
            _make_experience("sess-002", mission="Second mission", processed=True),
        ]
        mock_store = AsyncMock()
        mock_store.list_experiences = AsyncMock(return_value=exps)

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_experience_store.return_value = mock_store

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
        ):
            result = runner.invoke(app, ["experiences", "--limit", "10"])

        assert result.exit_code == 0
        assert "Session Experiences" in result.output
        assert "sess-001" in result.output
        assert "sess-002" in result.output

    def test_experiences_unprocessed_filter(self) -> None:
        """Passes unprocessed_only flag to store."""
        mock_store = AsyncMock()
        mock_store.list_experiences = AsyncMock(return_value=[])

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_experience_store.return_value = mock_store

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
        ):
            runner.invoke(app, ["experiences", "--unprocessed"])

        mock_store.list_experiences.assert_awaited_once_with(
            limit=20, unprocessed_only=True
        )


# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------


class TestStatsCommand:
    """Tests for ``taskforce memory stats``."""

    def test_stats_displays_table(self) -> None:
        """Shows statistics table with all metrics."""
        exps = [
            _make_experience("sess-001"),
            _make_experience("sess-002", processed=True),
        ]
        consol = [_make_consolidation_result()]

        mock_exp_store = AsyncMock()
        mock_exp_store.list_experiences = AsyncMock(return_value=exps)
        mock_exp_store.list_consolidations = AsyncMock(return_value=consol)

        mock_mem_store = AsyncMock()
        mock_mem_store.list = AsyncMock(return_value=[])

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_experience_store.return_value = mock_exp_store
        mock_ib.build_memory_store.return_value = mock_mem_store

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
        ):
            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "Memory Statistics" in result.output
        assert "Total experiences" in result.output
        assert "Latest consolidation" in result.output

    def test_stats_no_consolidations(self) -> None:
        """Handles case where no consolidation runs exist."""
        mock_exp_store = AsyncMock()
        mock_exp_store.list_experiences = AsyncMock(return_value=[])
        mock_exp_store.list_consolidations = AsyncMock(return_value=[])

        mock_mem_store = AsyncMock()
        mock_mem_store.list = AsyncMock(return_value=[])

        mock_loader = _mock_profile_loader()
        mock_ib = MagicMock()
        mock_ib.build_experience_store.return_value = mock_exp_store
        mock_ib.build_memory_store.return_value = mock_mem_store

        with (
            patch(_PROFILE_LOADER, return_value=mock_loader),
            patch(_INFRA_BUILDER, return_value=mock_ib),
        ):
            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "Memory Statistics" in result.output
        assert "Latest consolidation" not in result.output
