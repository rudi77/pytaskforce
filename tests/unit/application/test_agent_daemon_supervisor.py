"""Tests for the AgentDaemonSupervisor (issue #156, ADR-027).

The supervisor wraps the bare daemon with watchdog, auto-restart,
structured crash logging and graceful signal handling so the butler
can run unattended for days. These tests exercise each of the four
hardening primitives in isolation against a fake daemon to keep the
suite hermetic.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import timedelta

import pytest
from taskforce.application.daemon_supervisor import AgentDaemonSupervisor, DaemonStalled

from taskforce.core.utils.time import utc_now


class _FakeDaemon:
    """Daemon stand-in that exposes the surface the supervisor reads."""

    def __init__(
        self,
        *,
        crash_on_start: Exception | None = None,
        idle_seconds: float = 60.0,
        last_heartbeat_offset_seconds: float = 0.0,
    ) -> None:
        self.crash_on_start = crash_on_start
        self.idle_seconds = idle_seconds
        self.last_heartbeat_offset_seconds = last_heartbeat_offset_seconds
        self.is_running = False
        self.start_calls = 0
        self.stop_calls = 0
        self.last_heartbeat = utc_now()

    async def start(self) -> None:
        self.start_calls += 1
        if self.crash_on_start is not None:
            # Mimic a real daemon: mark running briefly so the watchdog
            # can observe a stalled heartbeat in tests that exercise
            # that path.
            self.is_running = True
            raise self.crash_on_start
        self.is_running = True
        # Pretend the main loop has run by setting last_heartbeat to a
        # configurable offset in the past. A big offset triggers the
        # watchdog stall path.
        self.last_heartbeat = utc_now() - timedelta(seconds=self.last_heartbeat_offset_seconds)

    async def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False


@pytest.mark.asyncio
async def test_supervisor_catches_crash_logs_restarts_with_backoff() -> None:
    """A synthetic exception during start() must not bring the process down.

    The supervisor must:
    - log the crash via ``logger.exception`` with structured context,
    - sleep for the configured backoff,
    - retry by building a fresh daemon from the factory.
    """
    crash = RuntimeError("boom")
    daemons: list[_FakeDaemon] = []

    def factory() -> _FakeDaemon:
        # Crash on the first 2 attempts, then succeed on the 3rd.
        if len(daemons) < 2:
            d = _FakeDaemon(crash_on_start=crash)
        else:
            d = _FakeDaemon()
        daemons.append(d)
        return d

    supervisor = AgentDaemonSupervisor(
        daemon_factory=factory,
        watchdog_interval_seconds=10.0,
        stall_threshold_seconds=60.0,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
        backoff_factor=2.0,
    )

    async def stopper() -> None:
        # Wait for the third (successful) daemon to be running, then
        # request shutdown so the supervisor exits.
        for _ in range(200):
            if len(daemons) >= 3 and daemons[-1].is_running:
                break
            await asyncio.sleep(0.01)
        supervisor.request_shutdown()

    await asyncio.gather(supervisor.run(), stopper())

    assert len(daemons) >= 3, "Supervisor must rebuild the daemon after each crash"
    assert supervisor.restart_count >= 2
    # The successful daemon should have been stopped on shutdown.
    assert daemons[-1].stop_calls == 1


@pytest.mark.asyncio
async def test_supervisor_does_not_restart_on_cancelled_error() -> None:
    """``asyncio.CancelledError`` must propagate, not trigger a restart."""

    class _CancellingDaemon(_FakeDaemon):
        async def start(self) -> None:  # type: ignore[override]
            await super().start()
            raise asyncio.CancelledError()

    built: list[_FakeDaemon] = []

    def factory() -> _FakeDaemon:
        d = _CancellingDaemon()
        built.append(d)
        return d

    supervisor = AgentDaemonSupervisor(
        daemon_factory=factory,
        initial_backoff_seconds=0.0,
    )
    await supervisor.run()
    # CancelledError → graceful shutdown, not restart loop.
    assert supervisor.restart_count == 0
    assert len(built) == 1


@pytest.mark.asyncio
async def test_supervisor_signal_handler_triggers_graceful_shutdown() -> None:
    """Invoking the signal handler must flip the shutdown event and stop the daemon."""
    daemon = _FakeDaemon(idle_seconds=3600.0)

    supervisor = AgentDaemonSupervisor(
        daemon_factory=lambda: daemon,
        watchdog_interval_seconds=60.0,
        stall_threshold_seconds=3600.0,
    )

    async def trigger_signal() -> None:
        # Wait until the daemon is actually running, then deliver a
        # synthetic SIGINT directly to the supervisor's handler. This
        # avoids platform-specific os.kill semantics in CI.
        for _ in range(200):
            if daemon.is_running:
                break
            await asyncio.sleep(0.01)
        supervisor._handle_signal(signal.SIGINT)

    await asyncio.gather(supervisor.run(), trigger_signal())

    assert daemon.stop_calls == 1
    assert supervisor.restart_count == 0


@pytest.mark.asyncio
async def test_watchdog_detects_stalled_heartbeat_and_restarts() -> None:
    """If ``last_heartbeat`` falls behind the threshold, the watchdog must restart the daemon."""
    daemons: list[_FakeDaemon] = []

    def factory() -> _FakeDaemon:
        if not daemons:
            # First daemon ships with a heartbeat 5s in the past, which
            # exceeds our 0.5s stall threshold immediately.
            d = _FakeDaemon(last_heartbeat_offset_seconds=5.0)
        else:
            # Healthy daemon — fresh heartbeat.
            d = _FakeDaemon(last_heartbeat_offset_seconds=0.0)
        daemons.append(d)
        return d

    supervisor = AgentDaemonSupervisor(
        daemon_factory=factory,
        watchdog_interval_seconds=0.05,
        stall_threshold_seconds=0.5,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
    )

    async def stopper() -> None:
        for _ in range(400):
            if len(daemons) >= 2 and daemons[-1].is_running:
                break
            await asyncio.sleep(0.01)
        supervisor.request_shutdown()

    await asyncio.gather(supervisor.run(), stopper())

    # The watchdog should have raised DaemonStalled on the first daemon
    # and the supervisor should have built a second one.
    assert len(daemons) >= 2
    assert supervisor.restart_count >= 1
    # Stop must have been called on the stalled daemon.
    assert daemons[0].stop_calls >= 1


@pytest.mark.asyncio
async def test_watchdog_raises_daemonstalled_directly() -> None:
    """Sanity check: the watchdog raises ``DaemonStalled`` for stale heartbeats."""
    daemon = _FakeDaemon(last_heartbeat_offset_seconds=10.0)
    daemon.is_running = True

    supervisor = AgentDaemonSupervisor(
        daemon_factory=lambda: daemon,
        watchdog_interval_seconds=0.01,
        stall_threshold_seconds=0.05,
    )
    supervisor._daemon = daemon

    with pytest.raises(DaemonStalled):
        # Bound the wait so a regression doesn't hang the suite.
        await asyncio.wait_for(supervisor._watchdog_loop(), timeout=2.0)


@pytest.mark.asyncio
async def test_supervisor_install_signal_handlers_is_safe() -> None:
    """``install_signal_handlers`` must succeed on the platform's main loop.

    On Windows ProactorEventLoop ``add_signal_handler`` raises
    ``NotImplementedError`` and the supervisor falls back to
    ``signal.signal``. Either path is acceptable as long as no exception
    leaks back to the caller.
    """
    daemon = _FakeDaemon()
    supervisor = AgentDaemonSupervisor(daemon_factory=lambda: daemon)
    supervisor.install_signal_handlers()
    assert supervisor._installed_signals, "At least SIGINT should be installed"
    # SIGINT is universally available.
    assert signal.SIGINT in supervisor._installed_signals
    if sys.platform != "win32":
        # POSIX: SIGTERM must also be installed.
        assert signal.SIGTERM in supervisor._installed_signals


@pytest.mark.skipif(sys.platform != "win32", reason="ProactorEventLoop is Windows-only")
def test_install_signal_handlers_under_proactor_event_loop() -> None:
    """Issue #191 sub-item (b): the Windows ProactorEventLoop fallback
    path (``signal.signal`` instead of ``loop.add_signal_handler``)
    must be exercised end-to-end, not just smoke-tested for absence
    of exceptions.

    The existing ``test_supervisor_install_signal_handlers_is_safe``
    relies on whatever event loop pytest-asyncio happens to provide,
    which on Windows is often the Selector loop. This test pins the
    real ProactorEventLoop path so a future refactor that breaks the
    fallback would actually fail the suite.
    """
    daemon = _FakeDaemon()
    supervisor = AgentDaemonSupervisor(daemon_factory=lambda: daemon)

    loop = asyncio.ProactorEventLoop()  # type: ignore[attr-defined]
    try:

        async def _install() -> None:
            supervisor.install_signal_handlers()

        loop.run_until_complete(_install())
    finally:
        loop.close()

    # The fallback path stores the same signals; assert it actually
    # registered something rather than silently dropping them.
    assert signal.SIGINT in supervisor._installed_signals
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        assert sigbreak in supervisor._installed_signals


def test_install_signal_handlers_without_running_loop_uses_signal_signal() -> None:
    """When called from sync context with no running loop and no
    explicit ``loop=`` argument, ``install_signal_handlers`` must fall
    back to ``signal.signal`` instead of crashing on the deprecated
    ``get_event_loop`` path.

    This pins the behaviour the issue #191 sub-item (b) cleanup
    introduced: no implicit loop creation, no DeprecationWarning, no
    silent skip on platforms where the fallback IS available.
    """
    daemon = _FakeDaemon()
    supervisor = AgentDaemonSupervisor(daemon_factory=lambda: daemon)
    # No asyncio.run / event loop — pure sync call.
    supervisor.install_signal_handlers()
    assert signal.SIGINT in supervisor._installed_signals
