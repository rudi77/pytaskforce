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

import typer
from rich.console import Console

app = typer.Typer(help="Run Taskforce as a REST webservice.", invoke_without_command=True)

console = Console()


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
    # modes behave consistently.
    uvicorn.run(
        app_path,
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        log_level=log_level,
    )
