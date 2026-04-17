"""Backwards-compat shim.

The canonical SendNotificationTool lives in
``taskforce.infrastructure.tools.native.send_notification_tool`` and is
registered under the ``send_notification`` short name. This shim re-exports
it so existing imports of ``taskforce_butler.infrastructure.tools.send_notification_tool``
keep working.
"""

from __future__ import annotations

from taskforce.infrastructure.tools.native.send_notification_tool import (
    SendNotificationTool,
)

__all__ = ["SendNotificationTool"]
