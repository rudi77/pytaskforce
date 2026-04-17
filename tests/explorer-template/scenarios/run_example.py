"""Scenario runner template — pattern reference.

Rename to ``run_s01.py`` (or similar) for your first real scenario.
Each runner follows the same three-phase pattern:

  1. Arrange — provision a fresh env via ``make_fresh_env``.
  2. Act     — send the scenario's text mission(s) via ``send_message``.
  3. Assert  — inspect the resulting DB / files, return a dict for the
               Claude driver to compare against the plan's Expected
               section.

The runner prints a single JSON blob on stdout. The loop reads that
blob and turns it into the iteration-block in ``test_report.md``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the harness importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness import db_query, make_fresh_env, run_scenario, send_message


async def _run() -> dict:
    # ── 1. Arrange ─────────────────────────────────────────────────
    env = make_fresh_env("example")

    # ── 2. Act ─────────────────────────────────────────────────────
    result = await send_message(env, "<put the scenario's user message here>")

    # ── 3. Assert (return the inspectable state; Claude compares) ──
    # Replace with your agent's schema. Kept minimal here.
    tables: list[dict] = []
    if env.db_path and env.db_path.exists():
        tables = db_query(
            env.db_path,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        )

    return {
        "agent": {
            "success": result["success"],
            "reply_preview": (result.get("reply") or "")[:400],
            "error": result.get("error"),
            "tool_calls": result.get("tool_calls", [])[:10],
        },
        "db_tables": [t["name"] for t in tables],
        "env_dir": str(env.work_dir),
    }


if __name__ == "__main__":
    try:
        out = run_scenario(_run)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"harness_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise
