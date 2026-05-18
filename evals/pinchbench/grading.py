"""Pinchbench grading: subprocess-isolated automated checks + LLM judge.

``run_automated_check`` writes the task's ``def grade(transcript, workspace_path)``
to a temp file, runs it in a child Python process with a timeout, and parses
the JSON it emits. This isolates user-supplied code from the parent process
and lets us enforce a wall-clock cap per task.

``run_llm_judge`` builds a rubric-anchored prompt, sends it through the
Taskforce LLM provider, and parses a ``{"score": float, "reasoning": str}``
JSON reply.

Security note: ``run_automated_check`` executes Python code authored
upstream in the pinchbench/skill repository. The subprocess inherits
the parent's environment and Python interpreter (so it has the same
filesystem and network reach as the eval harness). Pinchbench tasks
ship Stdlib-only graders today; if that ever changes, sandbox this
further (Docker, ``resource`` rlimits, restricted ``PYTHONHOME``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

_RUNNER_TEMPLATE = textwrap.dedent(
    '''
    import json
    import sys
    import traceback
    from pathlib import Path

    # ------------------------------------------------------------------
    # Task-supplied grade() function (extracted from pinchbench markdown)
    # ------------------------------------------------------------------
    {user_code}
    # ------------------------------------------------------------------

    payload = json.loads(sys.stdin.read())
    transcript = payload["transcript"]
    workspace_path = payload["workspace_path"]

    try:
        result = grade(transcript, workspace_path)
        if isinstance(result, dict):
            scores = {{k: float(v) for k, v in result.items()}}
        else:
            scores = {{"score": float(result)}}
        sys.stdout.write(json.dumps({{"ok": True, "scores": scores}}))
    except Exception as exc:  # noqa: BLE001
        sys.stdout.write(json.dumps({{
            "ok": False,
            "error": f"{{type(exc).__name__}}: {{exc}}",
            "traceback": traceback.format_exc(),
        }}))
    '''
).strip()


def run_automated_check(
    grade_function_source: str,
    transcript: list[dict[str, Any]],
    workspace_path: Path,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Execute the task's ``grade()`` function in an isolated subprocess.

    Returns:
        On success:  ``{"ok": True, "scores": {criterion: 0..1, ...}}``
        On failure:  ``{"ok": False, "error": str, "traceback": str?}``
    """
    if not grade_function_source.strip():
        return {"ok": False, "error": "no automated check defined for this task"}

    runner_src = _RUNNER_TEMPLATE.format(user_code=grade_function_source)
    payload = json.dumps(
        {"transcript": transcript, "workspace_path": str(workspace_path)}
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(runner_src)
        runner_path = Path(fh.name)

    # Force UTF-8 everywhere in the grader subprocess (#412 / QW8). On
    # Windows the stdlib default codec is cp1252, which crashes on the
    # smart-quotes / em-dashes that LLM-generated markdown reports
    # routinely contain (UnicodeDecodeError on byte 0x9d). Setting
    # PYTHONUTF8=1 makes every ``open()`` and stdio stream default to
    # UTF-8 in the child interpreter (Python 3.7+ UTF-8 mode).
    grader_env = os.environ.copy()
    grader_env["PYTHONUTF8"] = "1"
    grader_env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            [sys.executable, str(runner_path)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=grader_env,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"automated check exceeded {timeout_seconds}s wall clock",
        }
    finally:
        runner_path.unlink(missing_ok=True)

    stdout = proc.stdout.strip()
    if proc.returncode != 0 and not stdout:
        return {
            "ok": False,
            "error": f"runner exited with {proc.returncode}",
            "stderr": proc.stderr[:1000],
        }
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "non-JSON output from runner",
            "stdout": stdout[:1000],
            "stderr": proc.stderr[:1000],
        }


def aggregate_scores(scores: dict[str, float]) -> float:
    """Reduce a ``{criterion: 0..1}`` dict to a single mean score."""
    if not scores:
        return 0.0
    return sum(max(0.0, min(1.0, float(v))) for v in scores.values()) / len(scores)


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

_JSON_OBJ_RE = re.compile(r"\{[^{}]*\"score\"[^{}]*\}", re.DOTALL)


def _render_transcript_for_judge(transcript: list[dict[str, Any]], cap: int = 8000) -> str:
    """Flatten the structured transcript into a readable conversation snippet."""
    lines: list[str] = []
    for entry in transcript:
        if entry.get("type") != "message":
            continue
        msg = entry.get("message") or {}
        role = msg.get("role", "?")
        for item in msg.get("content", []) or []:
            kind = item.get("type")
            if kind == "text":
                lines.append(f"[{role}] {item.get('text', '')}")
            elif kind == "tool_use":
                name = item.get("name", "")
                args = json.dumps(item.get("input") or {})[:240]
                lines.append(f"[{role}] tool_call: {name}({args})")
            elif kind == "tool_result":
                content = str(item.get("content", ""))[:400]
                lines.append(f"[{role}] tool_result: {content}")
    text = "\n".join(lines)
    if len(text) <= cap:
        return text
    half = cap // 2
    return text[:half] + "\n... [truncated " + str(len(text) - cap) + " chars] ...\n" + text[-half:]


async def run_llm_judge(
    *,
    prompt: str,
    transcript: list[dict[str, Any]],
    rubric: str = "",
    expected_behavior: str = "",
    grading_criteria: str = "",
    judge_model: str = "main",
) -> dict[str, Any]:
    """Score a transcript with a Taskforce-spawned LLM judge.

    Returns ``{"ok": True, "score": 0..1, "reasoning": str}`` or
    ``{"ok": False, "error": str}``.
    """
    rubric_text = rubric.strip() or grading_criteria.strip() or (
        f"Score 1.0 if the agent met the expected behavior, "
        f"0.5 partial, 0.0 if not.\n\nEXPECTED BEHAVIOR:\n{expected_behavior}"
    )
    convo = _render_transcript_for_judge(transcript)

    judge_prompt = (
        "You are a strict, impartial grader for an agent benchmark.\n\n"
        "ORIGINAL TASK PROMPT:\n"
        f"{prompt}\n\n"
        "RUBRIC:\n"
        f"{rubric_text}\n\n"
        "AGENT TRANSCRIPT (may be truncated):\n"
        f"{convo}\n\n"
        "Score the agent's performance on a 0.0 to 1.0 scale according to the rubric. "
        "Reply with ONLY a single JSON object on one line: "
        '{"score": <number 0..1>, "reasoning": "<one short sentence>"}'
    )

    try:
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
    except ImportError as exc:
        return {"ok": False, "error": f"taskforce not importable: {exc}"}

    try:
        llm = InfrastructureBuilder().build_llm_provider({"llm": {}})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not build LLM provider: {exc}"}

    try:
        response = await llm.complete(
            messages=[{"role": "user", "content": judge_prompt}],
            model=judge_model,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"judge LLM call failed: {exc}"}

    if isinstance(response, dict) and response.get("success") is False:
        return {
            "ok": False,
            "error": f"LLM provider returned failure: {response.get('error', '')}",
            "error_type": response.get("error_type", ""),
        }

    text = (
        response.get("content", "")
        if isinstance(response, dict)
        else str(response)
    ).strip()

    match = _JSON_OBJ_RE.search(text)
    if not match:
        return {
            "ok": False,
            "error": "no score JSON in judge response",
            "raw": text[:500],
        }
    try:
        data = json.loads(match.group(0))
        score = max(0.0, min(1.0, float(data.get("score", 0.0))))
        return {"ok": True, "score": score, "reasoning": str(data.get("reasoning", ""))}
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"could not parse judge score: {exc}", "raw": text[:500]}
