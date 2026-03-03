"""
Unit tests for LLMConfigLoader — parameter matching and merging.

Tests cover:
- Exact alias match
- Exact resolved model match (full-prefix keys like "anthropic/claude-opus-4-6")
- Bare model match (Azure-style: key "gpt-5-mini" matches "azure/gpt-5-mini")
- Prefix match (key "gpt-5" matches "azure/gpt-5-turbo")
- Longest prefix wins ("gpt-5-mini" beats "gpt-5" for "gpt-5-mini-xyz")
- kwargs override model_params which override default_params
- _bare_model helper
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from taskforce.infrastructure.llm.llm_config_loader import LLMConfigLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, yaml_text: str) -> str:
    """Write a YAML config to a temp file and return its path."""
    config_file = tmp_path / "llm_config.yaml"
    config_file.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
    return str(config_file)


def _make_loader(tmp_path: Path, yaml_text: str) -> LLMConfigLoader:
    """Create an LLMConfigLoader from inline YAML text."""
    path = _write_config(tmp_path, yaml_text)
    return LLMConfigLoader(path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STANDARD_CONFIG = """\
    default_model: main

    models:
      main: "azure/gpt-4.1"
      fast: "azure/gpt-5-mini"
      powerful: "azure/gpt-5"
      claude: "anthropic/claude-opus-4-6"

    model_params:
      gpt-4.1:
        temperature: 0.2
        max_tokens: 2000

      gpt-5:
        reasoning_effort: "medium"
        max_tokens: 4000

      gpt-5-mini:
        reasoning_effort: "low"
        max_tokens: 10000

      anthropic/claude-opus-4-6:
        max_tokens: 16384
        temperature: 0.7

    default_params:
      temperature: 0.7
      max_tokens: 2000
"""


@pytest.fixture
def loader(tmp_path: Path) -> LLMConfigLoader:
    """Standard config loader for most tests."""
    return _make_loader(tmp_path, STANDARD_CONFIG)


# ---------------------------------------------------------------------------
# _bare_model
# ---------------------------------------------------------------------------


class TestBareModel:
    """Tests for the _bare_model static helper."""

    def test_strips_azure_prefix(self) -> None:
        assert LLMConfigLoader._bare_model("azure/gpt-5-mini") == "gpt-5-mini"

    def test_strips_anthropic_prefix(self) -> None:
        assert LLMConfigLoader._bare_model("anthropic/claude-opus-4-6") == "claude-opus-4-6"

    def test_no_prefix_unchanged(self) -> None:
        assert LLMConfigLoader._bare_model("gpt-4.1") == "gpt-4.1"

    def test_multiple_slashes_strips_first_only(self) -> None:
        assert LLMConfigLoader._bare_model("azure/deployments/gpt-5") == "deployments/gpt-5"


# ---------------------------------------------------------------------------
# get_params — exact matching
# ---------------------------------------------------------------------------


class TestGetParamsExactMatch:
    """Tests for exact alias / resolved / bare model matching."""

    def test_exact_alias_match(self, tmp_path: Path) -> None:
        """When the alias itself is a key in model_params, use it directly."""
        config = """\
            default_model: main
            models:
              main: "azure/gpt-4.1"
            model_params:
              main:
                temperature: 0.1
            default_params:
              temperature: 0.9
        """
        loader = _make_loader(tmp_path, config)
        params = loader.get_params("main")
        assert params["temperature"] == 0.1

    def test_exact_resolved_match(self, loader: LLMConfigLoader) -> None:
        """Anthropic-style full-prefix keys match the resolved model string."""
        params = loader.get_params("claude")
        assert params["max_tokens"] == 16384
        assert params["temperature"] == 0.7

    def test_bare_model_match_for_azure(self, loader: LLMConfigLoader) -> None:
        """Key 'gpt-5-mini' matches alias 'fast' which resolves to 'azure/gpt-5-mini'."""
        params = loader.get_params("fast")
        assert params["reasoning_effort"] == "low"
        assert params["max_tokens"] == 10000

    def test_bare_model_match_for_azure_gpt5(self, loader: LLMConfigLoader) -> None:
        """Key 'gpt-5' matches alias 'powerful' which resolves to 'azure/gpt-5'."""
        params = loader.get_params("powerful")
        assert params["reasoning_effort"] == "medium"
        assert params["max_tokens"] == 4000


# ---------------------------------------------------------------------------
# get_params — prefix matching
# ---------------------------------------------------------------------------


class TestGetParamsPrefixMatch:
    """Tests for prefix-based matching and longest-prefix-wins logic."""

    def test_prefix_match_on_bare_name(self, tmp_path: Path) -> None:
        """Key 'gpt-5' prefix-matches bare name 'gpt-5-turbo'."""
        config = """\
            default_model: main
            models:
              main: "azure/gpt-5-turbo"
            model_params:
              gpt-5:
                reasoning_effort: "high"
            default_params:
              temperature: 0.7
        """
        loader = _make_loader(tmp_path, config)
        params = loader.get_params("main")
        assert params["reasoning_effort"] == "high"

    def test_longest_prefix_wins(self, tmp_path: Path) -> None:
        """'gpt-5-mini' should beat 'gpt-5' for model 'azure/gpt-5-mini-turbo'."""
        config = """\
            default_model: main
            models:
              main: "azure/gpt-5-mini-turbo"
            model_params:
              gpt-5:
                reasoning_effort: "high"
                max_tokens: 4000
              gpt-5-mini:
                reasoning_effort: "low"
                max_tokens: 10000
            default_params:
              temperature: 0.7
        """
        loader = _make_loader(tmp_path, config)
        params = loader.get_params("main")
        assert params["reasoning_effort"] == "low"
        assert params["max_tokens"] == 10000

    def test_prefix_match_on_resolved_string(self, tmp_path: Path) -> None:
        """Prefix match against the full resolved string (with provider prefix)."""
        config = """\
            default_model: main
            models:
              main: "anthropic/claude-sonnet-4-6-20260301"
            model_params:
              anthropic/claude-sonnet-4-6:
                max_tokens: 8192
            default_params:
              max_tokens: 2000
        """
        loader = _make_loader(tmp_path, config)
        params = loader.get_params("main")
        assert params["max_tokens"] == 8192


# ---------------------------------------------------------------------------
# get_params — merge and override order
# ---------------------------------------------------------------------------


class TestGetParamsMergeOrder:
    """Tests for the three-level merge: defaults → model_params → kwargs."""

    def test_model_params_override_defaults(self, loader: LLMConfigLoader) -> None:
        """model_params values should override default_params."""
        params = loader.get_params("main")  # resolves to azure/gpt-4.1
        # default_params has temperature 0.7, model_params has 0.2
        assert params["temperature"] == 0.2
        assert params["max_tokens"] == 2000

    def test_kwargs_override_model_params(self, loader: LLMConfigLoader) -> None:
        """Explicit kwargs beat both defaults and model_params."""
        params = loader.get_params("main", temperature=0.0, max_tokens=500)
        assert params["temperature"] == 0.0
        assert params["max_tokens"] == 500

    def test_kwargs_override_defaults_when_no_model_match(
        self, tmp_path: Path
    ) -> None:
        """When no model_params match, kwargs still override default_params."""
        config = """\
            default_model: main
            models:
              main: "some-unknown-model"
            model_params: {}
            default_params:
              temperature: 0.7
        """
        loader = _make_loader(tmp_path, config)
        params = loader.get_params("main", temperature=0.3)
        assert params["temperature"] == 0.3

    def test_none_kwargs_ignored(self, loader: LLMConfigLoader) -> None:
        """kwargs with None values should not override existing params."""
        params = loader.get_params("main", temperature=None)
        assert params["temperature"] == 0.2  # from model_params, not None

    def test_fallback_to_defaults_when_no_match(self, tmp_path: Path) -> None:
        """When no model_params key matches, all defaults are returned."""
        config = """\
            default_model: main
            models:
              main: "some-unknown-model"
            model_params:
              totally-different:
                temperature: 0.1
            default_params:
              temperature: 0.7
              max_tokens: 2000
        """
        loader = _make_loader(tmp_path, config)
        params = loader.get_params("main")
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 2000


# ---------------------------------------------------------------------------
# get_params — direct model string (no alias)
# ---------------------------------------------------------------------------


class TestGetParamsDirectModel:
    """Tests when the caller passes a model string instead of an alias."""

    def test_direct_model_string_matches_bare(self, loader: LLMConfigLoader) -> None:
        """Passing 'azure/gpt-5-mini' directly (not an alias) should still match."""
        params = loader.get_params("azure/gpt-5-mini")
        assert params["reasoning_effort"] == "low"

    def test_direct_bare_model_string(self, loader: LLMConfigLoader) -> None:
        """Passing bare 'gpt-5-mini' directly matches model_params key."""
        params = loader.get_params("gpt-5-mini")
        assert params["reasoning_effort"] == "low"
