"""
Core utilities module.

Provides shared utility functions used across all layers.
"""

from taskforce.core.utils.paths import get_base_path, get_project_root
from taskforce.core.utils.time import utc_now

__all__ = ["get_base_path", "get_project_root", "utc_now"]
