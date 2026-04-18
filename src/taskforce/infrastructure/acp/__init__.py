"""ACP (Agent Communication Protocol) infrastructure.

This package provides a thin, protocol-driven layer over the ``acp-sdk``
package. All public entry points are importable without ``acp-sdk``
installed; the SDK is imported lazily so the optional dependency only
becomes required once the runtime is actually started.
"""

from taskforce.infrastructure.acp.peer_registry import (
    EnvPeerRegistry,
    FilePeerRegistry,
    InMemoryPeerRegistry,
)
from taskforce.infrastructure.acp.runtime import AcpRuntime

__all__ = [
    "AcpRuntime",
    "EnvPeerRegistry",
    "FilePeerRegistry",
    "InMemoryPeerRegistry",
]
