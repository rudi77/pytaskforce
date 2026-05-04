"""Framework-default sandboxed executor (ADR-022 §5).

Ships an in-process implementation that preserves today's behaviour
for self-hosted single-tenant builds. A multi-tenant deployment is
expected to install a container-backed executor through
:func:`taskforce.application.infrastructure_overrides.set_sandboxed_executor`.
"""

from taskforce.infrastructure.sandbox.in_process import InProcessSandboxedExecutor

__all__ = ["InProcessSandboxedExecutor"]
