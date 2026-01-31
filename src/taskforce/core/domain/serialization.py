"""
Serialization Utilities
========================

Helper functions to reduce boilerplate in dataclass serialization.

Usage:
    from taskforce.core.domain.serialization import (
        parse_timestamp,
        to_dict_optional,
    )

    @dataclass
    class MyModel:
        required_field: str
        optional_field: str = ""
        timestamp: datetime | None = None

        def to_dict(self) -> dict[str, Any]:
            result = {"required_field": self.required_field}
            to_dict_optional(result, "optional_field", self.optional_field)
            to_dict_optional(result, "timestamp", self.timestamp)
            return result

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "MyModel":
            return cls(
                required_field=data["required_field"],
                optional_field=data.get("optional_field", ""),
                timestamp=parse_timestamp(data.get("timestamp")),
            )
"""

from datetime import datetime
from enum import Enum
from typing import Any


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    """
    Parse a timestamp from string or datetime.

    Args:
        value: ISO format string, datetime object, or None

    Returns:
        datetime object or None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def to_dict_optional(
    result: dict[str, Any],
    key: str,
    value: Any,
    default: Any = None,
    *,
    skip_empty: bool = True,
) -> None:
    """
    Add a key to result dict only if value differs from default.

    This reduces boilerplate in to_dict methods by handling the common
    pattern of conditionally including optional fields.

    Args:
        result: Dictionary to add the key to (modified in place)
        key: Key name to add
        value: Value to add
        default: Default value to compare against (skip if equal)
        skip_empty: If True, also skip empty strings, lists, and dicts
    """
    if value == default:
        return

    if skip_empty:
        if value == "" or value == [] or value == {}:
            return

    # Handle special types
    if isinstance(value, datetime):
        result[key] = value.isoformat()
    elif isinstance(value, Enum):
        result[key] = value.value
    elif hasattr(value, "to_dict"):
        result[key] = value.to_dict()
    elif isinstance(value, list) and value and hasattr(value[0], "to_dict"):
        result[key] = [item.to_dict() for item in value]
    else:
        result[key] = value


def parse_enum(value: str | Enum | None, enum_class: type[Enum], default: Enum) -> Enum:
    """
    Parse an enum value from string or enum.

    Args:
        value: String value, enum instance, or None
        enum_class: The Enum class to parse into
        default: Default value if None

    Returns:
        Enum instance
    """
    if value is None:
        return default
    if isinstance(value, enum_class):
        return value
    return enum_class(value)
