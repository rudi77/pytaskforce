"""ctxman context-management adapter package.

Infrastructure adapter that implements ``ContextManagerProtocol`` on top
of the external ctxman REST service, switchable via profile config
(``context_management.backend: ctxman``).
"""

from taskforce.infrastructure.context.ctxman_client import (
    CtxmanBudgetExceededError,
    CtxmanClient,
    CtxmanConflictError,
    CtxmanError,
    CtxmanIncompleteUnitError,
    CtxmanPayloadTooLargeError,
    CtxmanUnavailableError,
    RenderResult,
)
from taskforce.infrastructure.context.ctxman_context_manager import (
    CtxmanConfig,
    CtxmanContextManager,
)
from taskforce.infrastructure.context.expand_context_ref_tool import (
    ExpandContextRefTool,
)
from taskforce.infrastructure.context.frame_binding import (
    FrameBinding,
    get_frame_binding,
    set_frame_binding,
)

__all__ = [
    "CtxmanBudgetExceededError",
    "CtxmanClient",
    "CtxmanConfig",
    "CtxmanConflictError",
    "CtxmanContextManager",
    "CtxmanError",
    "CtxmanIncompleteUnitError",
    "CtxmanPayloadTooLargeError",
    "CtxmanUnavailableError",
    "ExpandContextRefTool",
    "FrameBinding",
    "RenderResult",
    "get_frame_binding",
    "set_frame_binding",
]
