"""Tests for ContextPolicy model and its validation/factory methods."""

import pytest

from taskforce.core.domain.context_policy import ContextPolicy


class TestContextPolicyCreation:
    """Tests for ContextPolicy instantiation and defaults."""

    def test_defaults(self) -> None:
        policy = ContextPolicy()
        assert policy.max_items == 10
        assert policy.max_chars_per_item == 500
        assert policy.max_total_chars == 3000
        assert policy.include_latest_tool_previews_n == 5
        assert policy.allow_tools is None
        assert policy.allow_selectors == ["first_chars"]

    def test_custom_values(self) -> None:
        policy = ContextPolicy(
            max_items=20,
            max_chars_per_item=1000,
            max_total_chars=15000,
            include_latest_tool_previews_n=10,
            allow_tools=["python", "shell"],
            allow_selectors=["first_chars", "summary"],
        )
        assert policy.max_items == 20
        assert policy.max_chars_per_item == 1000
        assert policy.max_total_chars == 15000
        assert policy.include_latest_tool_previews_n == 10
        assert policy.allow_tools == ["python", "shell"]
        assert policy.allow_selectors == ["first_chars", "summary"]


class TestContextPolicyValidation:
    """Tests for ContextPolicy post-init validation."""

    def test_max_items_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_items must be positive"):
            ContextPolicy(max_items=0)

    def test_max_items_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_items must be positive"):
            ContextPolicy(max_items=-1)

    def test_max_chars_per_item_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_chars_per_item must be positive"):
            ContextPolicy(max_chars_per_item=0)

    def test_max_chars_per_item_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_chars_per_item must be positive"):
            ContextPolicy(max_chars_per_item=-10)

    def test_max_total_chars_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_total_chars must be positive"):
            ContextPolicy(max_total_chars=0)

    def test_max_total_chars_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_total_chars must be positive"):
            ContextPolicy(max_total_chars=-100)

    def test_include_latest_tool_previews_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="include_latest_tool_previews_n must be non-negative"):
            ContextPolicy(include_latest_tool_previews_n=-1)

    def test_include_latest_tool_previews_zero_allowed(self) -> None:
        policy = ContextPolicy(include_latest_tool_previews_n=0)
        assert policy.include_latest_tool_previews_n == 0

    def test_max_total_chars_adjusted_when_unachievable(self) -> None:
        """If max_total_chars > max_items * max_chars_per_item, it should be capped."""
        policy = ContextPolicy(
            max_items=2,
            max_chars_per_item=100,
            max_total_chars=500,  # 2 * 100 = 200, which is less than 500
        )
        assert policy.max_total_chars == 200

    def test_max_total_chars_not_adjusted_when_achievable(self) -> None:
        """If max_total_chars <= max_items * max_chars_per_item, it stays unchanged."""
        policy = ContextPolicy(
            max_items=10,
            max_chars_per_item=500,
            max_total_chars=3000,  # 10 * 500 = 5000 >= 3000
        )
        assert policy.max_total_chars == 3000

    def test_max_total_chars_equals_product(self) -> None:
        """Edge case: max_total_chars exactly equals product."""
        policy = ContextPolicy(
            max_items=5,
            max_chars_per_item=200,
            max_total_chars=1000,  # 5 * 200 = 1000, equal
        )
        assert policy.max_total_chars == 1000


class TestIsToolAllowed:
    """Tests for ContextPolicy.is_tool_allowed method."""

    def test_all_allowed_when_whitelist_is_none(self) -> None:
        policy = ContextPolicy(allow_tools=None)
        assert policy.is_tool_allowed("python") is True
        assert policy.is_tool_allowed("shell") is True
        assert policy.is_tool_allowed("any_tool") is True

    def test_only_whitelisted_tools_allowed(self) -> None:
        policy = ContextPolicy(allow_tools=["python", "file_read"])
        assert policy.is_tool_allowed("python") is True
        assert policy.is_tool_allowed("file_read") is True
        assert policy.is_tool_allowed("shell") is False
        assert policy.is_tool_allowed("web_search") is False

    def test_empty_whitelist_blocks_all(self) -> None:
        policy = ContextPolicy(allow_tools=[])
        assert policy.is_tool_allowed("python") is False
        assert policy.is_tool_allowed("anything") is False

    def test_empty_tool_name(self) -> None:
        policy = ContextPolicy(allow_tools=["python"])
        assert policy.is_tool_allowed("") is False

        policy_all = ContextPolicy(allow_tools=None)
        assert policy_all.is_tool_allowed("") is True


class TestConservativeDefault:
    """Tests for ContextPolicy.conservative_default factory."""

    def test_conservative_values(self) -> None:
        policy = ContextPolicy.conservative_default()
        assert policy.max_items == 5
        assert policy.max_chars_per_item == 300
        assert policy.max_total_chars == 1500
        assert policy.include_latest_tool_previews_n == 3
        assert policy.allow_tools is None
        assert policy.allow_selectors == ["first_chars"]

    def test_conservative_default_passes_validation(self) -> None:
        """Conservative default should not raise any validation errors."""
        policy = ContextPolicy.conservative_default()
        assert policy.max_items > 0
        assert policy.max_chars_per_item > 0
        assert policy.max_total_chars > 0

    def test_conservative_max_total_chars_is_achievable(self) -> None:
        policy = ContextPolicy.conservative_default()
        assert policy.max_items * policy.max_chars_per_item >= policy.max_total_chars


class TestFromDict:
    """Tests for ContextPolicy.from_dict factory."""

    def test_full_dict(self) -> None:
        data = {
            "max_items": 15,
            "max_chars_per_item": 800,
            "max_total_chars": 10000,
            "include_latest_tool_previews_n": 7,
            "allow_tools": ["python"],
            "allow_selectors": ["summary"],
        }
        policy = ContextPolicy.from_dict(data)
        assert policy.max_items == 15
        assert policy.max_chars_per_item == 800
        assert policy.max_total_chars == 10000
        assert policy.include_latest_tool_previews_n == 7
        assert policy.allow_tools == ["python"]
        assert policy.allow_selectors == ["summary"]

    def test_empty_dict_uses_defaults(self) -> None:
        policy = ContextPolicy.from_dict({})
        assert policy.max_items == 10
        assert policy.max_chars_per_item == 500
        assert policy.max_total_chars == 3000
        assert policy.include_latest_tool_previews_n == 5
        assert policy.allow_tools is None
        assert policy.allow_selectors == ["first_chars"]

    def test_partial_dict(self) -> None:
        policy = ContextPolicy.from_dict({"max_items": 20})
        assert policy.max_items == 20
        assert policy.max_chars_per_item == 500  # default

    def test_extra_keys_ignored(self) -> None:
        policy = ContextPolicy.from_dict({"max_items": 5, "unknown_key": "value"})
        assert policy.max_items == 5

    def test_allow_tools_none(self) -> None:
        policy = ContextPolicy.from_dict({"allow_tools": None})
        assert policy.allow_tools is None


class TestToDict:
    """Tests for ContextPolicy.to_dict serialization."""

    def test_default_policy(self) -> None:
        policy = ContextPolicy()
        d = policy.to_dict()
        assert d["max_items"] == 10
        assert d["max_chars_per_item"] == 500
        assert d["max_total_chars"] == 3000
        assert d["include_latest_tool_previews_n"] == 5
        assert d["allow_tools"] is None
        assert d["allow_selectors"] == ["first_chars"]

    def test_custom_policy(self) -> None:
        policy = ContextPolicy(
            max_items=3,
            max_chars_per_item=200,
            max_total_chars=600,
            allow_tools=["python"],
        )
        d = policy.to_dict()
        assert d["max_items"] == 3
        assert d["allow_tools"] == ["python"]

    def test_roundtrip(self) -> None:
        original = ContextPolicy(
            max_items=8,
            max_chars_per_item=400,
            max_total_chars=2500,
            include_latest_tool_previews_n=4,
            allow_tools=["file_read", "web_search"],
            allow_selectors=["first_chars", "last_chars"],
        )
        restored = ContextPolicy.from_dict(original.to_dict())
        assert restored.max_items == original.max_items
        assert restored.max_chars_per_item == original.max_chars_per_item
        assert restored.max_total_chars == original.max_total_chars
        assert restored.include_latest_tool_previews_n == original.include_latest_tool_previews_n
        assert restored.allow_tools == original.allow_tools
        assert restored.allow_selectors == original.allow_selectors

    def test_roundtrip_conservative_default(self) -> None:
        original = ContextPolicy.conservative_default()
        restored = ContextPolicy.from_dict(original.to_dict())
        assert restored.to_dict() == original.to_dict()
