"""Test-harness utilities for the AP-Ledger exploratory test loop.

Provides three primitives that each scenario script uses:
  - ``make_fresh_customer(slug, name, country)`` — provisions a new
    customer instance in a temp directory, returns its path.
  - ``send_message(customer_dir, text)`` — spins up the agent against
    the customer's profile, replaces ask_user with an auto-yes stub,
    feeds the mission, and returns a result dict.
  - ``db_query(db_path, sql, params)`` — synchronous SQLite helper.

The harness talks to the agent directly via AgentFactory +
AgentExecutor — Telegram is bypassed entirely. This keeps iterations
fast and reproducible, but means Telegram-specific bugs (upload size,
polling drift) aren't surfaced by this suite.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Force UTF-8 stdio before anything structlog-aware imports; otherwise
# cp1252 on Windows crashes the harness at the first non-ASCII log line
# and swallows the real error underneath.
if sys.platform == "win32" and isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Resolve the repo root so we can import taskforce regardless of the
# test-script's CWD.
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

# The ap_ledger_agent plugin package (for the SQLiteStore import in
# follow-up inspection). Added here so callers can also use the typed
# store if they want to.
_AP_LEDGER_PKG = _REPO_ROOT / "examples" / "ap_ledger_agent"
if str(_AP_LEDGER_PKG) not in sys.path:
    sys.path.insert(0, str(_AP_LEDGER_PKG))

_PROVISION_SCRIPT = _REPO_ROOT / "examples" / "ap_ledger_agent" / "deploy" / "provision_customer.py"


@dataclass
class CustomerEnv:
    """Paths for a provisioned customer under test."""

    slug: str
    name: str
    country: str
    customer_dir: Path
    profile_path: Path
    db_path: Path
    belege_dir: Path
    reports_dir: Path
    env_file: Path


def _load_dotenv(env_file: Path) -> dict[str, str]:
    """Return a dict of KEY=VALUE pairs from an .env file (no shell expansion)."""
    out: dict[str, str] = {}
    if not env_file.is_file():
        return out
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def make_fresh_customer(
    slug: str,
    name: str,
    country: str = "AT",
    *,
    blubot_root: Path | None = None,
) -> CustomerEnv:
    """Provision a fresh customer directory via provision_customer.py.

    The slug is auto-suffixed with a short uuid to keep scenarios
    idempotent — callers don't need to clean up between runs.
    """
    unique_slug = f"{slug}-{uuid.uuid4().hex[:6]}"
    if blubot_root is None:
        blubot_root = Path(tempfile.gettempdir()) / "blubot-explorer"
    blubot_root.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            str(_PROVISION_SCRIPT),
            "--slug", unique_slug,
            "--name", name,
            "--country", country,
            "--blubot-root", str(blubot_root),
            "--bot-token", "UNUSED_IN_TESTS",
            "--chat-id", "0",
            "--force",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"provision_customer.py failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    customer_dir = blubot_root / "customers" / unique_slug
    return CustomerEnv(
        slug=unique_slug,
        name=name,
        country=country,
        customer_dir=customer_dir,
        profile_path=customer_dir / "ap_ledger_agent.yaml",
        db_path=customer_dir / "db" / "ap-ledger.db",
        belege_dir=customer_dir / "belege",
        reports_dir=customer_dir / "reports",
        env_file=customer_dir / ".env",
    )


# ---------------------------------------------------------------------- #
# Auto-yes ask_user replacement
# ---------------------------------------------------------------------- #

def _install_auto_yes_ask_user() -> None:
    """Monkey-patch the ``_handle_ask_user`` helper so ask_user never pauses.

    The framework special-cases ``ask_user`` in
    ``core/domain/planning/tool_execution.py``: when the agent calls it,
    the framework saves state, emits an ``ASK_USER`` StreamEvent and
    waits for the frontend (CLI, Telegram gateway) to feed an answer on
    the next turn. In tests there is no frontend to answer — the agent
    would sit paused forever.

    This patch replaces the helper with one that instead emits a normal
    ``TOOL_RESULT`` event carrying the string ``"ja"`` and appends a
    matching tool-result message to the agent's context. The ReAct loop
    then proceeds as if the user confirmed.

    Idempotent — safe to call multiple times.
    """
    import taskforce.core.domain.planning.tool_execution as _mod

    if getattr(_mod, "_explorer_auto_yes_installed", False):
        return

    from taskforce.core.domain.enums import EventType
    from taskforce.core.domain.models import StreamEvent

    async def _auto_yes_handle_ask_user(
        agent: Any,
        args: dict[str, Any],
        session_id: str,
        state: dict[str, Any],
        logger: Any,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        step: int,
        plan: list[str] | None = None,
        plan_step_idx: int | None = None,
        plan_iteration: int | None = None,
        paused_phase: str | None = None,
    ):
        answer = "ja"
        question = str(args.get("question", ""))
        tool_result = {
            "success": True,
            "answer": answer,
            "question": question,
        }

        yield StreamEvent(
            event_type=EventType.TOOL_RESULT,
            data={
                "tool": "ask_user",
                "id": tool_call_id,
                "success": True,
                "output": answer,
                "args": args,
            },
        )

        agent.context.append_message(
            await agent.tool_result_message_factory.build_message(
                tool_call_id=tool_call_id,
                tool_name="ask_user",
                tool_result=tool_result,
                session_id=session_id,
                step=step,
            )
        )
        logger.info(
            "auto_yes_ask_user",
            session_id=session_id,
            question=question[:80],
        )

    _mod._handle_ask_user = _auto_yes_handle_ask_user  # type: ignore[assignment]
    _mod._explorer_auto_yes_installed = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------- #
# Agent invocation
# ---------------------------------------------------------------------- #

async def send_message(
    customer: CustomerEnv,
    text: str,
    *,
    session_id: str | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Send a text mission to the agent, return a result dict.

    Replaces the live AskUserTool with an auto-yes stub so the flow
    doesn't block waiting for human input.

    Returns:
        dict with keys: success, reply, error, history_length, customer_dir.
    """
    # Load the customer's .env into the current process so the agent
    # picks up AZURE_API_KEY, AP_LEDGER_ROOT, etc.
    env_values = _load_dotenv(customer.env_file)
    for key, value in env_values.items():
        os.environ[key] = value

    # Also inject the framework secrets the main .env might have (Azure
    # keys etc.) — if the customer .env doesn't already set them.
    main_env = _load_dotenv(_REPO_ROOT / ".env")
    for key, value in main_env.items():
        os.environ.setdefault(key, value)

    # Install the auto-yes monkey-patch BEFORE the agent runs. Idempotent.
    _install_auto_yes_ask_user()

    from taskforce.application.factory import AgentFactory
    from taskforce.application.executor import AgentExecutor

    factory = AgentFactory()
    agent = await factory.create_agent(config=str(customer.profile_path))

    executor = AgentExecutor()
    sid = session_id or f"explorer-{uuid.uuid4().hex[:8]}"

    events: list[dict[str, Any]] = []
    final_message = ""
    status: str = "unknown"
    error: str | None = None

    async def _consume() -> None:
        nonlocal final_message, status, error
        async for update in executor.execute_mission_streaming(
            mission=text,
            agent=agent,
            session_id=sid,
        ):
            # event_type can be an enum OR a string upstream — normalise.
            raw_type = getattr(update, "event_type", None)
            event_type_str = getattr(raw_type, "value", raw_type)
            event_type_str = str(event_type_str) if event_type_str is not None else ""

            event = {
                "event_type": event_type_str,
                "message": getattr(update, "message", None),
            }
            events.append(event)

            details = getattr(update, "details", None) or {}
            if event_type_str == "complete":
                final_message = str(details.get("final_message") or update.message or "")
                status = str(details.get("status", "completed"))
            elif event_type_str == "error":
                err = details.get("error") or update.message
                if err:
                    error = str(err)

    try:
        await asyncio.wait_for(_consume(), timeout=timeout_s)
    except asyncio.TimeoutError:
        error = f"agent timed out after {timeout_s}s"

    success = status == "completed" and not error

    # Best-effort cleanup of the agent's resources.
    try:
        close = getattr(agent, "close", None)
        if close is not None:
            await close()
    except Exception:
        pass

    return {
        "success": success,
        "status": status,
        "reply": final_message,
        "error": error,
        "event_count": len(events),
        "tool_calls": [
            e["message"] for e in events if e["event_type"] == "tool_call"
        ],
        "customer_dir": str(customer.customer_dir),
    }


# ---------------------------------------------------------------------- #
# DB inspection
# ---------------------------------------------------------------------- #

def db_query(
    db_path: Path,
    sql: str,
    params: tuple | dict = (),
) -> list[dict[str, Any]]:
    """Run a read query and return rows as dicts."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_table_counts(db_path: Path, tables: list[str]) -> dict[str, int]:
    """Return row counts for a list of tables (helper for smoke assertions)."""
    return {
        t: db_query(db_path, f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
        for t in tables
    }


# ---------------------------------------------------------------------- #
# Convenience: run a one-shot async scenario from sync context
# ---------------------------------------------------------------------- #

def run_scenario(coro_factory):
    """Accept a zero-arg callable returning a coroutine, run it, return result.

    Keeps iteration-script boilerplate short.
    """
    return asyncio.run(coro_factory())
