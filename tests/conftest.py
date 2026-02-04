"""Test configuration and shared fixtures."""

from __future__ import annotations

import sys
import types
from typing import Any


def _install_structlog_stub() -> None:
    """Install a minimal structlog stub when structlog isn't available."""
    try:
        import structlog  # noqa: F401
        import structlog.testing  # noqa: F401

        return
    except Exception:
        pass

    structlog_module = types.ModuleType("structlog")

    class _StubLogger:
        def bind(self, **kwargs: Any) -> "_StubLogger":
            return self

        def warning(self, *args: Any, **kwargs: Any) -> None:
            return None

        def info(self, *args: Any, **kwargs: Any) -> None:
            return None

        def error(self, *args: Any, **kwargs: Any) -> None:
            return None

        def debug(self, *args: Any, **kwargs: Any) -> None:
            return None

    def _get_logger(*args: Any, **kwargs: Any) -> _StubLogger:
        return _StubLogger()

    structlog_module.get_logger = _get_logger  # type: ignore[attr-defined]
    structlog_module.make_filtering_bound_logger = (  # type: ignore[attr-defined]
        lambda *args, **kwargs: _StubLogger
    )
    structlog_module.configure = lambda *args, **kwargs: None  # type: ignore[attr-defined]

    testing_module = types.ModuleType("structlog.testing")
    testing_module.LogCapture = object  # type: ignore[attr-defined]

    typing_module = types.ModuleType("structlog.typing")
    typing_module.FilteringBoundLogger = Any  # type: ignore[attr-defined]

    stdlib_module = types.ModuleType("structlog.stdlib")
    stdlib_module.BoundLogger = _StubLogger  # type: ignore[attr-defined]

    sys.modules.setdefault("structlog", structlog_module)
    sys.modules.setdefault("structlog.testing", testing_module)
    sys.modules.setdefault("structlog.typing", typing_module)
    sys.modules.setdefault("structlog.stdlib", stdlib_module)


_install_structlog_stub()


def _install_mcp_stub() -> None:
    """Install a minimal MCP stub when the mcp package isn't available."""
    try:
        import mcp  # noqa: F401

        return
    except Exception:
        pass

    mcp_module = types.ModuleType("mcp")
    client_module = types.ModuleType("mcp.client")
    client_sse_module = types.ModuleType("mcp.client.sse")
    client_stdio_module = types.ModuleType("mcp.client.stdio")

    class ClientSession:
        _validate_tool_result = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    class StdioServerParameters:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    async def _stub_stream_client(*args: Any, **kwargs: Any):
        raise RuntimeError("MCP stubbed; stream clients are unavailable in tests.")

    mcp_module.ClientSession = ClientSession  # type: ignore[attr-defined]
    mcp_module.StdioServerParameters = StdioServerParameters  # type: ignore[attr-defined]
    client_sse_module.sse_client = _stub_stream_client  # type: ignore[attr-defined]
    client_stdio_module.stdio_client = _stub_stream_client  # type: ignore[attr-defined]

    sys.modules.setdefault("mcp", mcp_module)
    sys.modules.setdefault("mcp.client", client_module)
    sys.modules.setdefault("mcp.client.sse", client_sse_module)
    sys.modules.setdefault("mcp.client.stdio", client_stdio_module)


_install_mcp_stub()


def _install_aiohttp_stub() -> None:
    """Install a minimal aiohttp stub when aiohttp isn't available."""
    try:
        import aiohttp  # noqa: F401

        return
    except Exception:
        pass

    aiohttp_module = types.ModuleType("aiohttp")

    class ClientSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    class ClientTimeout:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    aiohttp_module.ClientSession = ClientSession  # type: ignore[attr-defined]
    aiohttp_module.ClientTimeout = ClientTimeout  # type: ignore[attr-defined]

    sys.modules.setdefault("aiohttp", aiohttp_module)


_install_aiohttp_stub()


def _install_aiofiles_stub() -> None:
    """Install a minimal aiofiles stub when aiofiles isn't available."""
    try:
        import aiofiles  # noqa: F401

        return
    except Exception:
        pass

    aiofiles_module = types.ModuleType("aiofiles")

    async def _stub_open(*args: Any, **kwargs: Any):
        raise RuntimeError("aiofiles stubbed; file I/O is unavailable in tests.")

    aiofiles_module.open = _stub_open  # type: ignore[attr-defined]

    sys.modules.setdefault("aiofiles", aiofiles_module)


_install_aiofiles_stub()


def _install_litellm_stub() -> None:
    """Install a minimal litellm stub when litellm isn't available."""
    try:
        import litellm  # noqa: F401

        return
    except Exception:
        pass

    litellm_module = types.ModuleType("litellm")

    async def _stub_acompletion(*args: Any, **kwargs: Any):
        raise RuntimeError("litellm stubbed; completions are unavailable in tests.")

    litellm_module.set_verbose = False  # type: ignore[attr-defined]
    litellm_module.suppress_debug_info = True  # type: ignore[attr-defined]
    litellm_module.acompletion = _stub_acompletion  # type: ignore[attr-defined]

    sys.modules.setdefault("litellm", litellm_module)


_install_litellm_stub()
