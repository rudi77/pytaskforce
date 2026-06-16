"""``taskforce serve`` — run the Taskforce REST API as a webservice.

Thin wrapper around uvicorn that boots ``taskforce.api.server:app``. Lets
host applications drop Taskforce in as a sidecar without having to know the
correct module path or Windows event-loop quirks.

Examples::

    taskforce serve
    taskforce serve --host 127.0.0.1 --port 9000
    taskforce serve --reload                          # dev hot-reload
    taskforce serve --workers 4                       # production
    taskforce serve --log-level debug
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Run Taskforce as a REST webservice.", invoke_without_command=True)

console = Console()


def _resolve_reload_dirs() -> list[str] | None:
    """Scope ``--reload`` to the Python source tree(s).

    uvicorn's fallback reloader (``StatReload``, used when ``watchfiles`` is
    absent) walks the entire CWD for ``*.py``. In a dev checkout that includes
    ``ui/node_modules``, whose pnpm symlink farm has phantom paths (e.g. a
    missing ``fsevents`` directory on Windows), the ``rglob`` raises
    ``FileNotFoundError`` and the reloader process dies — hot-reload silently
    stops working and edits never load. Restricting the watch to the editable
    package source dir(s) sidesteps ``node_modules`` entirely and makes reload
    faster. Returns ``None`` (leaving uvicorn's default behaviour intact) when
    no source dir can be located, e.g. an installed-wheel deployment.
    """
    dirs: list[str] = []
    # Watch the parent ``src`` dir of each editable package we can import, so a
    # monorepo checkout hot-reloads core, CLI, and enterprise code alike.
    for module_name in ("taskforce", "taskforce_cli", "taskforce_enterprise"):
        try:
            module = __import__(module_name)
        except Exception:  # noqa: BLE001 — best-effort discovery
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        src_dir = Path(module_file).resolve().parent.parent  # .../src/<pkg> -> .../src
        if src_dir.is_dir() and str(src_dir) not in dirs:
            dirs.append(str(src_dir))
    return dirs or None


@app.callback(invoke_without_command=True)
def serve(
    ctx: typer.Context,
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help=(
            "Bind address. Defaults to 127.0.0.1 so the server is not "
            "exposed to the network. Use 0.0.0.0 (or a specific interface) "
            "for container/k8s deployments where a reverse proxy or "
            "ingress fronts the service."
        ),
    ),
    port: int = typer.Option(
        8070,
        "--port",
        "-p",
        help="TCP port to listen on.",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload on code changes (development only).",
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        min=1,
        help="Number of worker processes. Ignored when --reload is set.",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        help="Uvicorn log level (critical|error|warning|info|debug|trace).",
    ),
    app_path: str = typer.Option(
        "taskforce.api.server:app",
        "--app",
        help="ASGI application path. Override to mount Taskforce inside a host app.",
    ),
) -> None:
    """Boot the Taskforce REST API.

    The default app exposes all built-in routers under ``/api/v1`` plus the
    OpenAPI docs at ``/docs``. Plugins discovered via entry points are
    auto-registered during startup.
    """
    # If a sub-command was invoked (none defined yet, but defensive), don't
    # double-run the server.
    if ctx.invoked_subcommand is not None:
        return

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - core dep
        console.print(
            "[bold red]uvicorn is not installed.[/bold red] "
            "Install Taskforce with REST API support."
        )
        raise typer.Exit(code=1) from exc

    console.print(
        f"[bold green]Taskforce[/bold green] serving on "
        f"[cyan]http://{host}:{port}[/cyan]  "
        f"([dim]docs: /docs · health: /health[/dim])"
    )

    # When --reload is set uvicorn requires the app as an import string and
    # ignores ``workers``. We pass the string form unconditionally so both
    # modes behave consistently. ``reload_dirs`` scopes the file watcher to the
    # source tree(s) so it never descends into ``ui/node_modules`` (whose pnpm
    # symlink farm crashes the fallback reloader on Windows).
    reload_dirs = _resolve_reload_dirs() if reload else None
    if reload and reload_dirs:
        console.print(f"[dim]watching for changes in: {', '.join(reload_dirs)}[/dim]")
    uvicorn.run(
        app_path,
        host=host,
        port=port,
        reload=reload,
        reload_dirs=reload_dirs,
        workers=workers if not reload else 1,
        log_level=log_level,
    )
