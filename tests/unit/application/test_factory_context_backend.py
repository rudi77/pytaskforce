"""Tests for the context-manager backend switch (local | ctxman)."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from taskforce.application.infrastructure_builder import InfrastructureBuilder
from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_context_manager_factory_override,
)
from taskforce.infrastructure.context.ctxman_context_manager import (
    CtxmanContextManager,
)


@pytest.fixture(autouse=True)
def _clean_overrides():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


@pytest.fixture
def builder() -> InfrastructureBuilder:
    return InfrastructureBuilder()


def test_default_backend_returns_none(builder: InfrastructureBuilder) -> None:
    assert builder.build_context_manager_factory({}) is None
    assert (
        builder.build_context_manager_factory({"context_management": {"backend": "local"}}) is None
    )


def test_unknown_backend_raises_value_error(builder: InfrastructureBuilder) -> None:
    with pytest.raises(ValueError, match="Unknown context_management.backend"):
        builder.build_context_manager_factory({"context_management": {"backend": "redis"}})


def test_ctxman_backend_returns_adapter_factory(
    builder: InfrastructureBuilder,
) -> None:
    config = {
        "context_management": {
            "backend": "ctxman",
            "ctxman": {"base_url": "http://ctxman.test:5291", "provider": "openai"},
        }
    }
    factory = builder.build_context_manager_factory(config)
    assert factory is not None

    from taskforce.core.domain.token_budgeter import TokenBudgeter

    logger = Mock()
    adapter = factory(
        message_history_manager=Mock(),
        openai_tools=[],
        token_budgeter=TokenBudgeter(logger=logger, max_input_tokens=1000),
        logger=logger,
    )
    assert isinstance(adapter, CtxmanContextManager)
    assert adapter._client._base_url == "http://ctxman.test:5291"


def test_override_hook_wins(builder: InfrastructureBuilder) -> None:
    sentinel_factory = object()

    def override(config: dict[str, Any]) -> Any:
        return sentinel_factory

    set_context_manager_factory_override(override)
    result = builder.build_context_manager_factory({"context_management": {"backend": "local"}})
    assert result is sentinel_factory


def test_clear_overrides_resets_hook(builder: InfrastructureBuilder) -> None:
    set_context_manager_factory_override(lambda config: object())
    clear_infrastructure_overrides()
    assert builder.build_context_manager_factory({}) is None
