"""Generic exploratory-test harness for Taskforce agents.

Copy this file to your explorer dir, rename to ``_harness.py``, and
implement the ``make_fresh_env`` stub at the bottom for your agent.
Everything else is agent-agnostic and works for any profile that uses
the standard ``AgentFactory`` + ``AgentExecutor`` pipeline.

Primitives exposed to scenario runners:
  - :class:`TestEnv` — bag of paths for an isolated test workspace.
  - :func:`make_fresh_env` — provision a fresh workspace. **AGENT-SPECIFIC.**
  - :func:`send_message` — feed a text mission to the agent, return a
    dict with success / reply / tool_calls / event_count.
  - :func:`db_query` — thin sqlite3 helper returning list[dict].
  - :func:`run_scenario` — run a coroutine-factory from sync code.

The :func:`_install_auto_yes_ask_user` hook is applied automatically by
``send_message``; it monkey-patches ``_handle_ask_user`` so the agent's
``ask_user`` calls receive an immediate "ja" instead of pausing for a
human — tests would otherwise sit forever.
"""

from __future__ import annotations

import asyncio
import io
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Force UTF-8 stdio before structlog / reportlab / anything importing
# starts writing logs; otherwise cp1252 on Windows crashes the harness
# at the first non-ASCII log line and buries the real error.
if sys.platform == "win32" and isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Resolve the repo root so ``import taskforce`` works regardless of CWD.
# Adjust the ``parents[N]`` index if this file lives somewhere other
# than ``<repo>/examples/<agent>/tests/explorer/scenarios/_harness.py``.
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


@dataclass
class TestEnv:
    """Paths for an isolated test workspace.

    Agents with different state layouts should extend / rename this
    (e.g. a butler agent might add ``schedule_store_path``). Keep it
    a dataclass so scenarios can access fields by name.
    """

    slug: str
    work_dir: Path
    profile_path: Path
    env_file: Path | None = None
    db_path: Path | None = None


# ---------------------------------------------------------------------- #
# .env loading
# ---------------------------------------------------------------------- #

def _load_dotenv(env_file: Path) -> dict[str, str]:
    """Return a dict of KEY=VALUE pairs from an .env file (no shell expansion)."""
    out: dict[str, str] = {}
    if not env_file or not env_file.is_file():
        return out
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


# ---------------------------------------------------------------------- #
# Auto-yes ask_user monkey-patch
# ---------------------------------------------------------------------- #

def _install_auto_yes_ask_user() -> None:
    """Replace ``_handle_ask_user`` with one that auto-answers ``"ja"``.

    Taskforce special-cases ``ask_user`` in
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
        tool_result = {"success": True, "answer": answer, "question": question}

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
    env: TestEnv,
    text: str,
    *,
    session_id: str | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Send a text mission to the agent, return a result dict.

    Uses ``AgentFactory`` + ``AgentExecutor.execute_mission_streaming``
    directly — any channel (Telegram, CLI) is bypassed. The auto-yes
    ask_user patch is installed so the agent never stalls on human
    confirmation prompts.

    Returns:
        dict with keys: success, status, reply, error, event_count,
        tool_calls (list of brief event messages).
    """
    # Load the env-file into the current process so the agent picks up
    # provider API keys, TASKFORCE_WORK_DIR, agent-specific vars, etc.
    if env.env_file is not None:
        for key, value in _load_dotenv(env.env_file).items():
            os.environ[key] = value

    # Also import the repo's top-level .env if it has shared secrets
    # (e.g. AZURE_API_KEY) that aren't duplicated into the per-customer file.
    for key, value in _load_dotenv(_REPO_ROOT / ".env").items():
        os.environ.setdefault(key, value)

    _install_auto_yes_ask_user()

    from taskforce.application.factory import AgentFactory
    from taskforce.application.executor import AgentExecutor

    factory = AgentFactory()
    agent = await factory.create_agent(config=str(env.profile_path))

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
            event = {
                "event_type": getattr(update, "event_type", None),
                "message": getattr(update, "message", None),
            }
            events.append(event)

            details = getattr(update, "details", None) or {}
            is_complete = bool(details.get("complete"))
            if is_complete:
                final_message = str(details.get("final_message") or update.message or "")
                status = str(details.get("status", "completed"))
            if event["event_type"] == "error":
                err = details.get("error") or update.message
                if err:
                    error = str(err)

    try:
        await asyncio.wait_for(_consume(), timeout=timeout_s)
    except asyncio.TimeoutError:
        error = f"agent timed out after {timeout_s}s"

    success = status == "completed" and not error

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
        "env_dir": str(env.work_dir),
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
    """Convenience: row counts for a list of tables."""
    return {
        t: db_query(db_path, f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
        for t in tables
    }


# ---------------------------------------------------------------------- #
# Sync entry point for scenario scripts
# ---------------------------------------------------------------------- #

def run_scenario(coro_factory):
    """Accept a zero-arg callable returning a coroutine, run it, return result.

    Keeps the scenario scripts' boilerplate short::

        if __name__ == "__main__":
            print(json.dumps(run_scenario(_run), …))
    """
    return asyncio.run(coro_factory())


# ====================================================================== #
# AGENT-SPECIFIC — IMPLEMENT FOR YOUR AGENT
# ====================================================================== #

def make_fresh_env(slug: str, **kwargs: Any) -> TestEnv:
    """Provision a fresh, isolated test workspace for the agent.

    **This is the one function you must implement per agent.**

    Typical implementation:
      1. Create a temp directory (use ``tempfile.gettempdir()``).
      2. Render the agent's profile YAML into it with placeholders
         substituted (customer name, country, paths, credentials, …).
      3. Copy any skill / seed files the agent needs at startup.
      4. Return a :class:`TestEnv` pointing at the provisioned workspace.

    For an example implementation, see the AP-Ledger concrete harness:
    ``examples/ap_ledger_agent/tests/explorer/scenarios/_harness.py`` —
    its ``make_fresh_customer`` shells out to ``provision_customer.py``
    and returns a ``CustomerEnv`` that wraps :class:`TestEnv` with
    agent-specific paths (db, belege, reports).

    Args:
        slug: Short identifier used to namespace the test workspace.
            Auto-suffix with a uuid if you need multiple instances.
        **kwargs: Agent-specific parameters (name, country, profile
            flags, etc.) — customise the signature as needed.

    Returns:
        TestEnv with at least work_dir, profile_path set.
    """
    raise NotImplementedError(
        "make_fresh_env() must be implemented for each agent. "
        "See the ap_ledger_agent harness for a worked example: "
        "examples/ap_ledger_agent/tests/explorer/scenarios/_harness.py"
    )
