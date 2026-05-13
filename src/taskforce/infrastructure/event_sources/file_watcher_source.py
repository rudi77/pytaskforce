"""File-system event source backed by ``watchdog``.

Watches one or more paths for ``created`` / ``modified`` / ``deleted``
events and publishes them as ``AgentEvent(event_type=FILE_CHANGED)``.

``watchdog`` runs its observer on a background thread, so we bridge to
asyncio with ``asyncio.run_coroutine_threadsafe``: the watchdog handler
schedules the (async) ``event_callback`` onto the loop captured at
``start`` time. This keeps the public surface identical to other
``EventSourceProtocol`` implementations — the daemon does not have to
know that a thread exists.

``watchdog`` ships as a core dependency. The factory still raises
:class:`ModuleNotFoundError` with a helpful hint if the package is
missing (broken venv) so the misconfiguration shows up at daemon start
instead of at first inotify event.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType

logger = structlog.get_logger(__name__)

EventCallback = Callable[[AgentEvent], Awaitable[None]]


class FileWatcherEventSource:
    """Watch one or more directories/files and emit ``FILE_CHANGED`` events."""

    def __init__(
        self,
        paths: list[str],
        *,
        event_callback: EventCallback | None = None,
        recursive: bool = True,
        source_name: str = "file_watcher",
        change_types: tuple[str, ...] = ("created", "modified", "deleted"),
    ) -> None:
        if not paths:
            raise ValueError("FileWatcherEventSource requires at least one path")
        self._paths = list(paths)
        self._event_callback = event_callback
        self._recursive = recursive
        self._source_name = source_name
        self._change_types = tuple(change_types)
        self._observer: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ModuleNotFoundError as exc:  # pragma: no cover — surfaced by daemon
            raise ModuleNotFoundError(
                "FileWatcherEventSource requires the 'watchdog' package, "
                "which ships in the core install. Run 'uv sync' to repair the venv."
            ) from exc

        self._loop = asyncio.get_running_loop()
        self._observer = Observer()

        handler = _make_handler(
            self._dispatch,
            FileSystemEventHandler,
            change_types=self._change_types,
        )
        for path in self._paths:
            self._observer.schedule(handler, path, recursive=self._recursive)

        self._observer.start()
        self._running = True
        logger.info(
            "file_watcher_source.started",
            paths=self._paths,
            recursive=self._recursive,
            change_types=list(self._change_types),
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:  # pragma: no cover — best-effort
                pass
            self._observer = None
        logger.info("file_watcher_source.stopped")

    def _dispatch(self, change_type: str, src_path: str, is_directory: bool) -> None:
        """Threadsafe handler — bridges watchdog to the asyncio callback."""
        with self._lock:
            loop = self._loop
            cb = self._event_callback
        if loop is None or cb is None or not self._running:
            return

        event = AgentEvent(
            source=self._source_name,
            event_type=AgentEventType.FILE_CHANGED,
            payload={
                "path": src_path,
                "change_type": change_type,
                "is_directory": is_directory,
            },
            metadata={"watch_paths": list(self._paths)},
        )

        try:
            asyncio.run_coroutine_threadsafe(cb(event), loop)
        except RuntimeError:  # pragma: no cover — loop closing during shutdown
            pass

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        event_callback: EventCallback | None = None,
    ) -> FileWatcherEventSource:
        """Factory used by ``EventSourceRegistry``.

        Required key: ``paths`` (list of strings).
        Optional keys: ``recursive`` (bool, default True), ``source_name``,
        ``change_types`` (subset of created/modified/deleted/moved).
        """
        paths = config.get("paths") or []
        if isinstance(paths, str):  # tolerate scalar
            paths = [paths]
        return cls(
            paths=paths,
            event_callback=event_callback,
            recursive=bool(config.get("recursive", True)),
            source_name=config.get("source_name", "file_watcher"),
            change_types=tuple(
                config.get("change_types", ("created", "modified", "deleted"))
            ),
        )


def _make_handler(
    dispatch: Callable[[str, str, bool], None],
    base_cls: type,
    *,
    change_types: tuple[str, ...],
) -> Any:
    """Build a watchdog ``FileSystemEventHandler`` subclass that calls
    ``dispatch(change_type, src_path, is_directory)`` for whitelisted
    event types.

    Defined as a closure so the handler captures the running source's
    dispatch method without circular imports.
    """

    allowed = set(change_types)

    class _Handler(base_cls):  # type: ignore[misc, valid-type]
        def on_created(self, event: Any) -> None:
            if "created" in allowed:
                dispatch("created", event.src_path, bool(event.is_directory))

        def on_modified(self, event: Any) -> None:
            if "modified" in allowed:
                dispatch("modified", event.src_path, bool(event.is_directory))

        def on_deleted(self, event: Any) -> None:
            if "deleted" in allowed:
                dispatch("deleted", event.src_path, bool(event.is_directory))

        def on_moved(self, event: Any) -> None:
            if "moved" in allowed:
                dispatch("moved", event.dest_path, bool(event.is_directory))

    return _Handler()
