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

def _make_auto_yes_ask_user_class():
    """Build and return a BaseTool subclass that always answers 'ja'."""
    from taskforce.infrastructure.tools.base_tool import BaseTool

    class AutoYesAskUserTool(BaseTool):
        tool_name = "ask_user"
        tool_description = "Ask the user (test mode — always answers 'ja')"
        tool_parameters_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to ask."},
            },
            "required": ["question"],
        }
        tool_requires_approval = False
        tool_supports_parallelism = False

        async def _execute(self, question: str = "", **kwargs: Any) -> dict[str, Any]:
            return {"success": True, "answer": "ja", "question": question}

    return AutoYesAskUserTool


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

    from taskforce.application.factory import AgentFactory
    from taskforce.application.executor import AgentExecutor

    factory = AgentFactory()
    agent = await factory.create_agent(config=str(customer.profile_path))

    # Swap ask_user with auto-yes BEFORE the agent runs.
    auto_yes_cls = _make_auto_yes_ask_user_class()
    if hasattr(agent, "tools") and isinstance(agent.tools, dict):
        agent.tools["ask_user"] = auto_yes_cls()
    # Rebuild the LLM-facing tool-schema list if the agent caches one.
    if hasattr(agent, "_openai_tools"):
        try:
            from taskforce.core.tools.tool_converter import tools_to_openai_schema
            agent._openai_tools = tools_to_openai_schema(list(agent.tools.values()))
        except Exception:
            pass  # If conversion isn't available, the live agent will re-derive.

    executor = AgentExecutor()
    sid = session_id or f"explorer-{uuid.uuid4().hex[:8]}"

    try:
        result = await asyncio.wait_for(
            executor.execute_mission(
                mission=text,
                agent=agent,
                session_id=sid,
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        return {
            "success": False,
            "reply": None,
            "error": f"agent timed out after {timeout_s}s",
            "customer_dir": str(customer.customer_dir),
        }

    reply = getattr(result, "reply", None) or getattr(result, "final", None) or str(result)
    success = bool(getattr(result, "success", False))
    error = getattr(result, "error", None)
    history = getattr(result, "history", []) or []

    # Best-effort cleanup of the agent's resources.
    try:
        close = getattr(agent, "close", None)
        if close is not None:
            await close()
    except Exception:
        pass

    return {
        "success": success,
        "reply": reply,
        "error": error,
        "history_length": len(history),
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
