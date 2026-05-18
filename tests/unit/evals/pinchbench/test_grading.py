"""Unit tests for evals.pinchbench.grading.run_automated_check + aggregate_scores."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from evals.pinchbench.grading import aggregate_scores, run_automated_check


SANITY_GRADER = dedent(
    """\
    def grade(transcript: list, workspace_path: str) -> dict:
        for entry in transcript:
            if entry.get("type") == "message":
                msg = entry.get("message", {})
                if msg.get("role") == "assistant":
                    content = msg.get("content", [])
                    if content:
                        return {"agent_responded": 1.0}
        return {"agent_responded": 0.0}
    """
)


def _fake_assistant_transcript() -> list[dict]:
    return [
        {
            "type": "message",
            "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        },
        {
            "type": "message",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello!"}]},
        },
    ]


def test_aggregate_scores_means_per_criterion() -> None:
    assert aggregate_scores({"a": 1.0, "b": 0.0}) == 0.5
    assert aggregate_scores({"a": 0.8, "b": 0.2, "c": 0.5}) == pytest.approx(0.5)


def test_aggregate_scores_empty_is_zero() -> None:
    assert aggregate_scores({}) == 0.0


def test_aggregate_scores_clamps_to_unit_interval() -> None:
    assert aggregate_scores({"a": 2.5, "b": -1.0}) == 0.5


def test_run_automated_check_passes_with_valid_transcript(tmp_path: Path) -> None:
    result = run_automated_check(SANITY_GRADER, _fake_assistant_transcript(), tmp_path)
    assert result == {"ok": True, "scores": {"agent_responded": 1.0}}


def test_run_automated_check_fails_with_empty_transcript(tmp_path: Path) -> None:
    result = run_automated_check(SANITY_GRADER, [], tmp_path)
    assert result == {"ok": True, "scores": {"agent_responded": 0.0}}


def test_run_automated_check_returns_error_on_missing_grader(tmp_path: Path) -> None:
    result = run_automated_check("", [], tmp_path)
    assert result["ok"] is False
    assert "no automated check" in result["error"]


def test_run_automated_check_captures_runtime_error(tmp_path: Path) -> None:
    broken = "def grade(transcript, workspace_path):\n    raise ValueError('boom')\n"
    result = run_automated_check(broken, [], tmp_path)
    assert result["ok"] is False
    assert "ValueError" in result["error"]
    assert "boom" in result["error"]


def test_run_automated_check_enforces_timeout(tmp_path: Path) -> None:
    slow = "def grade(t, w):\n    import time; time.sleep(5)\n    return {}\n"
    result = run_automated_check(slow, [], tmp_path, timeout_seconds=1)
    assert result["ok"] is False
    assert "exceeded" in result["error"]


def test_run_automated_check_accepts_numeric_return(tmp_path: Path) -> None:
    grader = "def grade(transcript, workspace_path):\n    return 0.75\n"
    result = run_automated_check(grader, [], tmp_path)
    assert result == {"ok": True, "scores": {"score": 0.75}}


def test_grader_handles_utf8_files_on_windows_default_codec(tmp_path: Path) -> None:
    """#412 / QW8: smart quotes (0x9d in cp1252) must not crash the grader.

    Repros the Windows-cp1252 UnicodeDecodeError that silently zeroed
    auto-component scores for 6 meeting/research samples in the full
    PinchBench run.
    """
    # File contains an en-dash (U+2013 = UTF-8 bytes E2 80 93) and a
    # right-double-quotation-mark (U+201D = UTF-8 bytes E2 80 9D — the
    # 0x9D byte is undefined in cp1252 and raises UnicodeDecodeError
    # when the grader's open() falls back to that codec.
    target = tmp_path / "report.md"
    target.write_text("Sales – “Q3” results\n", encoding="utf-8")

    grader = dedent(
        """\
        def grade(transcript, workspace_path):
            from pathlib import Path
            text = (Path(workspace_path) / "report.md").read_text()
            return {"has_text": 1.0 if "Q3" in text else 0.0}
        """
    )
    result = run_automated_check(grader, [], tmp_path)
    assert result["ok"] is True, result
    assert result["scores"] == {"has_text": 1.0}
