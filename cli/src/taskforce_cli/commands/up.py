"""``taskforce up`` — start Taskforce and open the web UI.

This is the one-command entry point for end users. It boots the REST API
(which also serves the bundled single-page web UI) and, once the server is
reachable, opens the browser. For headless servers pass ``--no-browser`` or
use the lower-level ``taskforce serve``.

Examples::

    taskforce up                       # start + open http://localhost:8070
    taskforce up --no-browser          # headless (servers, SSH sessions)
    taskforce up --host 0.0.0.0        # expose on the network (behind a proxy)
    taskforce up --port 9000
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

import typer
from rich.console import Console

app = typer.Typer(
    help="Start Taskforce and open the web UI (one command).",
    invoke_without_command=True,
)

console = Console()


def _open_browser_when_ready(url: str, health_url: str, timeout: float = 60.0) -> None:
    """Poll the health endpoint, then open the browser once the API answers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    break
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    else:
        return
    import webbrowser

    webbrowser.open(url)


@app.callback(invoke_without_command=True)
def up(
    ctx: typer.Context,
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help=(
            "Bind address. Defaults to 127.0.0.1 (local only). Use 0.0.0.0 "
            "to expose the service on the network — put a reverse proxy in front."
        ),
    ),
    port: int = typer.Option(8070, "--port", "-p", help="TCP port to listen on."),
    open_browser: bool = typer.Option(
        True,
        "--browser/--no-browser",
        help="Open the web UI in a browser once the server is ready.",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        help="Uvicorn log level (critical|error|warning|info|debug|trace).",
    ),
) -> None:
    """Boot the Taskforce API + web UI and open the browser."""
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

    display_host = "localhost" if host in {"127.0.0.1", "0.0.0.0"} else host
    url = f"http://{display_host}:{port}"
    console.print(
        f"[bold green]Taskforce[/bold green] starting on [cyan]{url}[/cyan]  "
        f"([dim]web UI + docs at /docs · Ctrl+C to stop[/dim])"
    )

    if open_browser:
        health_host = "127.0.0.1" if host == "0.0.0.0" else host
        threading.Thread(
            target=_open_browser_when_ready,
            args=(url, f"http://{health_host}:{port}/health"),
            daemon=True,
        ).start()

    uvicorn.run(
        "taskforce.api.server:app",
        host=host,
        port=port,
        log_level=log_level,
    )
