"""Supervisor for unattended agent daemon operation (issue #156).

The supervisor wraps the bare ``AgentDaemon`` lifecycle with the four
runtime-hardening primitives required for 24/7 use on a developer
machine:

1. **Watchdog** — emits a heartbeat every supervisor tick and detects
   when the main loop's heartbeat has stalled past
   ``stall_threshold_seconds``. A stalled loop is logged with
   ``event="butler.daemon.stall_detected"`` and the daemon is
   restarted.
2. **Auto-restart on crash** — wraps :py:meth:`AgentDaemon.start` in a
   loop that catches *unexpected* exceptions, logs them with full
   structured context, sleeps for an exponentially-growing backoff
   (capped at ``max_backoff_seconds``), and resumes. Cancellation and
   ``KeyboardInterrupt``/``SystemExit`` propagate so graceful shutdown
   still works.
3. **Structured crash logs** — every uncaught exception is logged via
   ``logger.exception(...)`` with ``event="butler.daemon.crash"`` plus
   ``iteration_count``, ``backoff_seconds`` and the wall-clock
   timestamp. No bare ``except: pass`` paths.
4. **Graceful shutdown on signals** — a single helper installs handlers
   for the platform-appropriate set of signals (``SIGINT`` + ``SIGTERM``
   on POSIX, ``SIGINT`` + ``SIGBREAK`` on Windows) that flip an
   :py:class:`asyncio.Event` so the supervisor can stop the inner
   daemon, drain in-flight work, and exit cleanly.

The supervisor is intentionally minimal: it does not own daemon
construction, it only manages restart + watchdog policy. ``AgentDaemon``
remains responsible for component wiring; it just exposes a
``last_heartbeat`` timestamp the supervisor can poll.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable
from typing import Any

import structlog

from taskforce.core.utils.time import utc_now

logger = structlog.get_logger(__name__)


# Defaults chosen so that a *misbehaving* main loop is detected within a
# minute on a developer laptop while leaving plenty of slack for normal
# polling cycles (the proactive heartbeat alone runs every 15 minutes).
_DEFAULT_WATCHDOG_INTERVAL = 30.0
_DEFAULT_STALL_THRESHOLD = 120.0
_DEFAULT_INITIAL_BACKOFF = 1.0
_DEFAULT_MAX_BACKOFF = 60.0
_DEFAULT_BACKOFF_FACTOR = 2.0


class AgentDaemonSupervisor:
    """Supervises a :class:`AgentDaemon` instance for unattended operation.

    The supervisor takes a ``daemon_factory`` (zero-arg callable) so it
    can build a fresh daemon for every restart cycle — this avoids
    leaking task references between restarts and matches the way Linux
    init systems treat services.

    Args:
        daemon_factory: Zero-arg callable returning a fresh ``AgentDaemon``.
        watchdog_interval_seconds: How often the watchdog wakes up.
        stall_threshold_seconds: Heartbeat-age threshold past which the
            main loop is considered stalled.
        initial_backoff_seconds: Initial sleep after a crash.
        max_backoff_seconds: Upper bound on the exponential backoff.
        backoff_factor: Multiplier used for the exponential backoff.
    """

    def __init__(
        self,
        daemon_factory: Callable[[], Any],
        *,
        watchdog_interval_seconds: float = _DEFAULT_WATCHDOG_INTERVAL,
        stall_threshold_seconds: float = _DEFAULT_STALL_THRESHOLD,
        initial_backoff_seconds: float = _DEFAULT_INITIAL_BACKOFF,
        max_backoff_seconds: float = _DEFAULT_MAX_BACKOFF,
        backoff_factor: float = _DEFAULT_BACKOFF_FACTOR,
    ) -> None:
        self._daemon_factory = daemon_factory
        # Floor at 0.01s to prevent accidental busy-waiting from a
        # caller passing 0; tests intentionally use sub-second values.
        self._watchdog_interval = max(0.01, watchdog_interval_seconds)
        self._stall_threshold = max(self._watchdog_interval * 2, stall_threshold_seconds)
        self._initial_backoff = max(0.0, initial_backoff_seconds)
        self._max_backoff = max(self._initial_backoff, max_backoff_seconds)
        self._backoff_factor = max(1.0, backoff_factor)

        self._shutdown = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._daemon: Any = None
        self._iteration_count = 0
        self._restart_count = 0
        self._installed_signals: list[Any] = []

    @property
    def daemon(self) -> Any:
        """Return the currently active daemon instance, if any."""
        return self._daemon

    @property
    def restart_count(self) -> int:
        """Number of restart cycles completed so far."""
        return self._restart_count

    @property
    def iteration_count(self) -> int:
        """Number of ``run`` iterations attempted (start + restarts)."""
        return self._iteration_count

    def request_shutdown(self) -> None:
        """Trigger graceful shutdown from outside the event loop."""
        self._shutdown.set()

    def request_restart(self) -> None:
        """Trigger a forced restart of the inner daemon."""
        self._restart_event.set()

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Install platform-appropriate signal handlers.

        On POSIX we install ``SIGINT`` + ``SIGTERM`` via
        ``loop.add_signal_handler`` (the recommended asyncio path). On
        Windows the asyncio ProactorEventLoop does not implement
        ``add_signal_handler`` so we fall back to ``signal.signal`` with
        ``SIGINT`` and the Windows-specific ``SIGBREAK`` (Ctrl+Break,
        also raised by ``taskkill`` without ``/F`` when the target is a
        console-attached process). ``SIGTERM`` is intentionally not
        handled on Windows: native termination paths (``taskkill /F`` →
        ``TerminateProcess``, WM_CLOSE) bypass Python signal handlers
        entirely, so installing one would be a no-op except for the
        narrow case where someone calls ``os.kill(pid, signal.SIGTERM)``
        from another Python process. Operators relying on Windows
        Service / NSSM stop semantics should use Ctrl+Break instead.
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — caller is in a sync context. Fall
                # straight through to the signal.signal fallback path
                # below by leaving ``loop`` None and relying on the
                # except branch to skip ``loop.add_signal_handler``.
                loop = None
        signals_to_install: list[Any] = [signal.SIGINT]

        if sys.platform != "win32":
            signals_to_install.append(signal.SIGTERM)
        else:
            sigbreak = getattr(signal, "SIGBREAK", None)
            if sigbreak is not None:
                signals_to_install.append(sigbreak)

        for sig in signals_to_install:
            try:
                if loop is None:
                    # No running loop — go straight to signal.signal.
                    raise NotImplementedError
                loop.add_signal_handler(sig, self._handle_signal, sig)
                self._installed_signals.append(sig)
            except (NotImplementedError, RuntimeError):
                # Windows ProactorEventLoop or non-main thread — fall
                # back to the synchronous signal API. Note: this only
                # works on the main thread.
                try:
                    signal.signal(sig, self._signal_signal_handler)
                    self._installed_signals.append(sig)
                except (ValueError, OSError):
                    # Not the main thread — skip silently. The CLI
                    # already runs the daemon on the main thread so
                    # this only fires inside test harnesses.
                    logger.debug(
                        "butler.daemon.signal_handler_skipped",
                        signal=getattr(sig, "name", str(sig)),
                    )

    def _handle_signal(self, sig: Any) -> None:
        """asyncio-side signal handler: log + flip the shutdown event."""
        logger.info(
            "butler.daemon.signal_received",
            signal=getattr(sig, "name", str(sig)),
            iteration_count=self._iteration_count,
        )
        self._shutdown.set()

    def _signal_signal_handler(self, signum: int, frame: Any) -> None:
        """`signal.signal` fallback used on Windows ProactorEventLoop."""
        try:
            sig = signal.Signals(signum)
            sig_name = sig.name
        except ValueError:
            sig_name = str(signum)
        logger.info(
            "butler.daemon.signal_received",
            signal=sig_name,
            iteration_count=self._iteration_count,
        )
        # Best-effort: schedule the event flip on the running loop.
        # ``get_running_loop`` raises RuntimeError when called outside
        # async context, which is exactly the fall-through condition we
        # want here. (``get_event_loop`` emits a DeprecationWarning on
        # Python 3.12+ in this case.)
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._shutdown.set)
        except RuntimeError:
            # No running loop — fall back to direct set. On the main
            # thread this is safe because asyncio.Event.set() does not
            # block.
            self._shutdown.set()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the supervisor until shutdown is requested.

        The supervisor wraps the daemon's ``start()`` + idle loop in an
        outer restart loop. Each iteration:

        1. Builds a fresh daemon via the factory.
        2. Calls ``daemon.start()``.
        3. Spawns a watchdog task that monitors the daemon's
           ``last_heartbeat`` attribute.
        4. Waits for either the shutdown event, a restart request, or a
           crash from the inner ``_run_daemon_loop``.
        5. On crash, logs, sleeps for an exponential backoff, and loops.

        Cancellation, ``KeyboardInterrupt`` and ``SystemExit`` all skip
        the restart path so the harness can shut down cleanly.
        """
        backoff = self._initial_backoff
        while not self._shutdown.is_set():
            self._iteration_count += 1
            self._restart_event.clear()
            try:
                await self._start_and_wait()
            except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                # Propagate to the outer caller (typically asyncio.run).
                logger.info(
                    "butler.daemon.shutdown_requested",
                    iteration_count=self._iteration_count,
                )
                self._shutdown.set()
                break
            except Exception as exc:  # noqa: BLE001 — supervisor catches all
                self._restart_count += 1
                logger.exception(
                    "butler.daemon.crash",
                    iteration_count=self._iteration_count,
                    restart_count=self._restart_count,
                    backoff_seconds=backoff,
                    error_type=type(exc).__name__,
                    error=str(exc)[:300],
                    timestamp=utc_now().isoformat(),
                )
                # Always attempt to stop the (possibly half-started) daemon
                # before sleeping so resources are released.
                await self._safe_stop_daemon()
                if self._shutdown.is_set():
                    break
                await self._sleep_with_shutdown(backoff)
                backoff = min(self._max_backoff, backoff * self._backoff_factor)
                continue
            else:
                # Clean exit from _start_and_wait: either shutdown
                # requested or an explicit restart. Reset backoff on
                # success so a long-running daemon doesn't carry stale
                # backoff state into a future crash.
                backoff = self._initial_backoff
                if not self._shutdown.is_set() and self._restart_event.is_set():
                    self._restart_count += 1
                    logger.info(
                        "butler.daemon.restart_requested",
                        iteration_count=self._iteration_count,
                        restart_count=self._restart_count,
                    )
                    await self._safe_stop_daemon()
                    continue
                # Shutdown path: stop the daemon and exit the loop.
                await self._safe_stop_daemon()
                break

        logger.info(
            "butler.daemon.supervisor_exited",
            iteration_count=self._iteration_count,
            restart_count=self._restart_count,
        )

    async def _start_and_wait(self) -> None:
        """Start a fresh daemon and wait until shutdown/restart/crash."""
        self._daemon = self._daemon_factory()
        await self._daemon.start()

        watchdog = asyncio.create_task(
            self._watchdog_loop(),
            name="butler-supervisor-watchdog",
        )
        shutdown_wait = asyncio.create_task(
            self._shutdown.wait(),
            name="butler-supervisor-shutdown",
        )
        restart_wait = asyncio.create_task(
            self._restart_event.wait(),
            name="butler-supervisor-restart",
        )

        try:
            done, _ = await asyncio.wait(
                {watchdog, shutdown_wait, restart_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Surface watchdog exceptions (stall detected) so the outer
            # ``run`` loop treats them as crashes and applies backoff.
            for task in done:
                if task is watchdog and task.exception() is not None:
                    raise task.exception()  # type: ignore[misc]
        finally:
            for task in (watchdog, shutdown_wait, restart_wait):
                if not task.done():
                    task.cancel()
            for task in (watchdog, shutdown_wait, restart_wait):
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    # Already handled / cancellation expected.
                    pass

    async def _watchdog_loop(self) -> None:
        """Detect stalled main loops by polling ``daemon.last_heartbeat``."""
        while not self._shutdown.is_set():
            await asyncio.sleep(self._watchdog_interval)
            if self._daemon is None or not getattr(self._daemon, "is_running", False):
                continue
            last = getattr(self._daemon, "last_heartbeat", None)
            if last is None:
                continue
            age = (utc_now() - last).total_seconds()
            if age > self._stall_threshold:
                logger.error(
                    "butler.daemon.stall_detected",
                    last_heartbeat=last.isoformat(),
                    heartbeat_age_seconds=age,
                    stall_threshold_seconds=self._stall_threshold,
                    iteration_count=self._iteration_count,
                )
                raise DaemonStalled(
                    f"Heartbeat stalled for {age:.1f}s " f"(threshold {self._stall_threshold:.1f}s)"
                )

    async def _safe_stop_daemon(self) -> None:
        """Stop the daemon, swallowing errors to keep the supervisor alive."""
        if self._daemon is None:
            return
        try:
            await self._daemon.stop()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "butler.daemon.stop_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
        finally:
            self._daemon = None

    async def _sleep_with_shutdown(self, seconds: float) -> None:
        """Sleep for ``seconds`` but wake early if shutdown is requested."""
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=seconds)
        except TimeoutError:
            return


class DaemonStalled(RuntimeError):
    """Raised by the watchdog when the main loop's heartbeat is stale."""
