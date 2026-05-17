"""Unit tests for evals.pinchbench.loader (no upstream clone required)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from evals.pinchbench import loader


SAMPLE_TASK = dedent(
    """\
    ---
    id: task_demo
    name: Demo Task
    category: coding
    grading_type: hybrid
    timeout_seconds: 120
    workspace_files:
      - fixtures/input.csv
    ---

    ## Prompt

    Sort the CSV at workspace/input.csv by score descending.

    ## Expected Behavior

    The agent reads the CSV, sorts, writes back.

    ## Grading Criteria

    - [ ] Output file is sorted
    - [ ] No data lost

    ## Automated Checks

    ```python
    def grade(transcript: list, workspace_path: str) -> dict:
        return {"placeholder": 1.0}
    ```

    ## LLM Judge Rubric

    Score 1.0 if perfectly sorted.
    """
)


def test_parse_task_extracts_frontmatter_and_sections(tmp_path: Path) -> None:
    path = tmp_path / "task_demo.md"
    path.write_text(SAMPLE_TASK, encoding="utf-8")

    task = loader.parse_task(path)

    assert task.id == "task_demo"
    assert task.category == "coding"
    assert task.grading_type == "hybrid"
    assert task.timeout_seconds == 120
    assert task.workspace_files == ["fixtures/input.csv"]
    assert "Sort the CSV" in task.prompt
    assert "sorts" in task.expected_behavior.lower()
    assert "def grade" in task.grade_function
    assert task.grade_function.strip().endswith('return {"placeholder": 1.0}')
    assert "Score 1.0" in task.llm_judge_rubric


def test_parse_task_rejects_files_without_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "task_bad.md"
    path.write_text("# No frontmatter here", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter"):
        loader.parse_task(path)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, []),
        ([], []),
        (["task_a", "task_b"], ["task_a", "task_b"]),
        ("task_solo", ["task_solo"]),
        (["task_ok", 42, None], ["task_ok"]),  # non-strings dropped
        ({"unexpected": "shape"}, []),
    ],
)
def test_str_list_handles_manifest_variants(value: object, expected: list[str]) -> None:
    assert loader._str_list(value) == expected


def test_load_tasks_core_uses_manifest_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Build a fake skill checkout
    skill = tmp_path / "skill"
    tasks_dir = skill / "tasks"
    tasks_dir.mkdir(parents=True)
    for tid in ("task_a", "task_b", "task_c"):
        (tasks_dir / f"{tid}.md").write_text(
            SAMPLE_TASK.replace("task_demo", tid).replace("category: coding", "category: x"),
            encoding="utf-8",
        )
    (tasks_dir / "manifest.yaml").write_text(
        "run_first:\n  - task_b\ncore:\n  - task_c\n  - task_a\n",
        encoding="utf-8",
    )

    # Redirect SKILL_DIR + skip the clone
    monkeypatch.setattr(loader, "SKILL_DIR", skill)
    monkeypatch.setattr(loader, "ensure_skill_checkout", lambda update=False: skill)

    tasks = loader.load_tasks("core")

    # Order: run_first first, then core, deduped
    assert [t.id for t in tasks] == ["task_b", "task_c", "task_a"]


def test_load_tasks_category_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = tmp_path / "skill"
    tasks_dir = skill / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "task_one.md").write_text(
        SAMPLE_TASK.replace("task_demo", "task_one").replace("category: coding", "category: writing"),
        encoding="utf-8",
    )
    (tasks_dir / "task_two.md").write_text(
        SAMPLE_TASK.replace("task_demo", "task_two"),
        encoding="utf-8",
    )

    monkeypatch.setattr(loader, "SKILL_DIR", skill)
    monkeypatch.setattr(loader, "ensure_skill_checkout", lambda update=False: skill)

    writing = loader.load_tasks("writing")
    assert [t.id for t in writing] == ["task_one"]

    coding = loader.load_tasks("coding")
    assert [t.id for t in coding] == ["task_two"]
